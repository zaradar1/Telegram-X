"""Download manager: priority queue for single files, bulk per-channel
download, and the auto batch-forward pipeline (moved from the monolith)."""

import asyncio
import heapq
import itertools
import os
import time
from typing import Any, Callable, Dict, List, Optional, cast

import database
import duplicate
from ratelimit import FloodWaitGate
from settings import BATCH_CACHE_DIR, BATCH_SIZE, MAX_WORKERS
from utils import ensure_dir


class DownloadQueue:
    """Priority queue of individual file downloads with bounded concurrency.

    Lower `priority` numbers run first. Pausing stops new downloads from
    starting; in-flight downloads finish (Telethon's high-level API doesn't
    expose byte-range resume, so true mid-file pause isn't possible — files
    that already exist on disk are skipped on a later retry instead).
    """

    def __init__(self, client, max_concurrent: int = 4,
                 db_path: str = database.DB_FILE,
                 flood_gate: Optional[FloodWaitGate] = None) -> None:
        self.client = client
        self.max_concurrent = max_concurrent
        self.db_path = db_path
        self.flood_gate = flood_gate or FloodWaitGate()
        self._heap: List[tuple] = []
        self._counter = itertools.count()
        self._sem = asyncio.Semaphore(max_concurrent)
        self._paused = False
        self._cancelled: set = set()
        self.on_progress: Optional[Callable[[str, int, int], None]] = None

    def add(self, msg, channel_id: int, dest_dir: str, priority: int = 5) -> str:
        task_id = f"{channel_id}:{msg.id}"
        fname = getattr(getattr(msg, "file", None), "name", None) or f"msg_{msg.id}"
        dest_path = os.path.join(dest_dir, fname)
        database.upsert_download(msg.id, channel_id, fname, dest_path,
                                  status="pending", priority=priority,
                                  db_path=self.db_path)
        heapq.heappush(self._heap, (priority, next(self._counter), task_id,
                                     msg, channel_id, dest_dir, fname, dest_path))
        return task_id

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def cancel(self, task_id: str) -> None:
        self._cancelled.add(task_id)

    async def _download_one(self, task_id, msg, channel_id, dest_dir, fname, dest_path) -> None:
        async with self._sem:
            if task_id in self._cancelled:
                database.update_download_progress(msg.id, channel_id, 0, status="failed",
                                                   db_path=self.db_path)
                return
            ensure_dir(dest_dir)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                database.update_download_progress(msg.id, channel_id,
                                                    os.path.getsize(dest_path),
                                                    status="done", db_path=self.db_path)
                if self.on_progress:
                    self.on_progress(task_id, 1, 1)
                return

            database.update_download_progress(msg.id, channel_id, 0, status="downloading",
                                                db_path=self.db_path)

            def _progress(current, total):
                database.update_download_progress(msg.id, channel_id, current, db_path=self.db_path)
                if self.on_progress:
                    self.on_progress(task_id, current, total)

            from telethon import errors
            try:
                for attempt in range(3):
                    await self.flood_gate.wait_if_tripped()
                    try:
                        await self.client.download_media(msg, file=dest_path,
                                                           progress_callback=_progress)
                        break
                    except errors.FloodWaitError as e:
                        await self.flood_gate.trip(e.seconds + 1)
                    except errors.FileReferenceExpiredError:
                        try:
                            chat = await msg.get_input_chat()
                            fresh = await self.client.get_messages(chat, ids=msg.id)
                            if fresh is not None and fresh.media:
                                msg = fresh
                        except Exception:
                            pass
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2)
                size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                database.update_download_progress(msg.id, channel_id, size, status="done",
                                                    db_path=self.db_path)
                if size:
                    duplicate.register_file(dest_path, channel_id, msg.id, db_path=self.db_path)
            except Exception:
                database.update_download_progress(msg.id, channel_id, 0, status="failed",
                                                    db_path=self.db_path)

    async def run(self) -> None:
        """Drain the queue, respecting pause() and max_concurrent."""
        pending: set = set()
        while self._heap or pending:
            while self._heap and not self._paused and len(pending) < self.max_concurrent * 2:
                _, _, task_id, msg, channel_id, dest_dir, fname, dest_path = heapq.heappop(self._heap)
                task = asyncio.create_task(
                    self._download_one(task_id, msg, channel_id, dest_dir, fname, dest_path))
                pending.add(task)
                task.add_done_callback(pending.discard)
            if not pending:
                if self._paused:
                    await asyncio.sleep(0.2)
                    continue
                break
            done, _ = await asyncio.wait(pending, timeout=0.2,
                                          return_when=asyncio.FIRST_COMPLETED)


# ── Bulk per-channel download (Browser tab "Download Media" button) ──

async def download_channel_media(client, entity, channel_id: int, dl_dir: str,
                                  max_concurrent: int,
                                  status_cb: Optional[Callable[[str], None]] = None,
                                  db_path: str = database.DB_FILE,
                                  flood_gate: Optional[FloodWaitGate] = None) -> int:
    from telethon import errors

    gate = flood_gate or FloodWaitGate()
    sem = asyncio.Semaphore(max_concurrent)
    downloaded = 0
    failed = 0
    pending: set = set()

    async def _dl_one(msg) -> None:
        nonlocal downloaded, failed
        async with sem:
            fname = f"msg_{msg.id}"
            if msg.file and msg.file.name:
                fname = msg.file.name
            path = os.path.join(dl_dir, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                downloaded += 1
                if status_cb:
                    status_cb(f"Skipped (exists): {fname}  [{downloaded} done]")
                return
            try:
                for attempt in range(3):
                    await gate.wait_if_tripped()
                    try:
                        await client.download_media(msg, file=path)
                        downloaded += 1
                        if status_cb:
                            status_cb(f"Downloaded: {fname}  [{downloaded} done]")
                        if os.path.exists(path):
                            duplicate.register_file(path, channel_id, msg.id, db_path=db_path)
                        return
                    except errors.FloodWaitError as e:
                        await gate.trip(e.seconds + 1)
                    except errors.FileReferenceExpiredError:
                        try:
                            chat = await msg.get_input_chat()
                            fresh = await client.get_messages(chat, ids=msg.id)
                            if fresh is not None and fresh.media:
                                msg = fresh
                        except Exception:
                            pass
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2)
            except Exception as e:
                failed += 1
                if status_cb:
                    status_cb(f"Failed: {fname} — {e}")

    async for msg in client.iter_messages(entity, limit=None):
        if not msg.media:
            continue
        task = asyncio.create_task(_dl_one(msg))
        pending.add(task)
        task.add_done_callback(pending.discard)
        while len(pending) >= max_concurrent * 2:
            await asyncio.sleep(0.1)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return downloaded


# ── Combined download: Telegram media + external links in message text ──

async def download_channel_all(client, entity, channel_id: int, dl_dir: str,
                                 max_concurrent: int,
                                 status_cb: Optional[Callable[[str], None]] = None,
                                 db_path: str = database.DB_FILE,
                                 flood_gate: Optional[FloodWaitGate] = None) -> Dict[str, int]:
    """Scan every message in a channel and download both Telegram-attached
    media and any plain URLs found in the message text (best-effort — see
    linkdownloader.download_url for what's actually fetchable)."""
    import linkdownloader
    from telethon import errors

    gate = flood_gate or FloodWaitGate()
    sem = asyncio.Semaphore(max_concurrent)
    loop = asyncio.get_event_loop()
    counts = {"media": 0, "links": 0, "skipped_links": 0, "failed": 0}
    pending: set = set()

    async def _dl_media(msg) -> None:
        async with sem:
            fname = f"msg_{msg.id}"
            if msg.file and msg.file.name:
                fname = msg.file.name
            path = os.path.join(dl_dir, fname)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                counts["media"] += 1
                if status_cb:
                    status_cb(f"Skipped (exists): {fname}  [{counts['media']} files]")
                return
            try:
                for attempt in range(3):
                    await gate.wait_if_tripped()
                    try:
                        await client.download_media(msg, file=path)
                        counts["media"] += 1
                        if status_cb:
                            status_cb(f"Downloaded: {fname}  [{counts['media']} files]")
                        if os.path.exists(path):
                            duplicate.register_file(path, channel_id, msg.id, db_path=db_path)
                        return
                    except errors.FloodWaitError as e:
                        await gate.trip(e.seconds + 1)
                    except errors.FileReferenceExpiredError:
                        try:
                            chat = await msg.get_input_chat()
                            fresh = await client.get_messages(chat, ids=msg.id)
                            if fresh is not None and fresh.media:
                                msg = fresh
                        except Exception:
                            pass
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2)
            except Exception as e:
                counts["failed"] += 1
                if status_cb:
                    status_cb(f"Failed: {fname} — {e}")

    async def _dl_link(url: str, msg_id: int) -> None:
        async with sem:
            try:
                path = await loop.run_in_executor(None, linkdownloader.download_url, url, dl_dir)
                if path:
                    counts["links"] += 1
                    if status_cb:
                        status_cb(f"Downloaded link: {os.path.basename(path)}  [{counts['links']} links]")
                    duplicate.register_file(path, channel_id, msg_id, db_path=db_path)
                else:
                    counts["skipped_links"] += 1
                    if status_cb:
                        status_cb(f"Skipped link (not a direct file): {url}")
            except Exception as e:
                counts["failed"] += 1
                if status_cb:
                    status_cb(f"Link failed: {url} — {e}")

    async for msg in client.iter_messages(entity, limit=None):
        if msg.media:
            task = asyncio.create_task(_dl_media(msg))
            pending.add(task)
            task.add_done_callback(pending.discard)

        text = getattr(msg, "message", "") or ""
        for url in linkdownloader.extract_links(text):
            task = asyncio.create_task(_dl_link(url, msg.id))
            pending.add(task)
            task.add_done_callback(pending.discard)

        while len(pending) >= max_concurrent * 2:
            await asyncio.sleep(0.1)

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return counts


# ── Auto batch-forward pipeline (moved from monolith, unchanged logic) ──

async def auto_batch_forward(
    client, src: str, dst: str,
    fwd_photo: bool, fwd_video: bool, fwd_audio: bool, fwd_doc: bool,
    cap_mode: str,
    log_cb: Callable[[str, str], None],
    progress_cb: Callable[[int, int], None],
    stop_flag: Callable[[], bool],
    db_path: str = database.DB_FILE,
    flood_gate: Optional[FloodWaitGate] = None,
    batch_size: int = BATCH_SIZE,
    max_workers: int = MAX_WORKERS,
) -> None:
    from telethon.tl import types as tl_types
    from telethon import errors

    gate = flood_gate or FloodWaitGate()
    bid = f"batch_{int(time.time())}"
    cnt = {"sent": 0, "failed": 0, "skipped": 0, "total": 0, "bnum": 0}

    async def _resolve(identifier: str) -> Any:
        from telethon.tl.types import InputChannel
        from telethon.tl.functions.channels import GetChannelsRequest
        s = identifier.strip()
        if not s.lstrip("-").isdigit():
            return await client.get_entity(s.lstrip("@"))
        num = int(s)
        ss = str(num)
        cid = int(ss[4:]) if ss.startswith("-100") else abs(num)
        try:
            r = await client(GetChannelsRequest([InputChannel(cid, 0)]))
            chats = getattr(r, "chats", None)
            if chats:
                return chats[0]
        except Exception:
            pass
        async for d in client.iter_dialogs():
            if hasattr(d.entity, "id") and d.entity.id == cid:
                return d.entity
        return await client.get_entity(num)

    try:
        src_e = await _resolve(src)
        dst_e = await _resolve(dst)
        src_t = getattr(src_e, "title", None) or str(src)
    except Exception as e:
        log_cb(f"❌ Cannot resolve channels: {e}", "err")
        return

    existing = database.batch_load_existing(src, dst, db_path=db_path)
    resume_id = 0
    if existing:
        resume_id = existing["last_msg_id"]
        cnt["sent"] = existing["sent"]
        cnt["bnum"] = existing["batch_num"]
        bid = existing["batch_id"]
        log_cb(f"🔄 Resuming batch {bid} from Msg ID {resume_id} "
               f"(already sent {cnt['sent']})", "info")

    ensure_dir(BATCH_CACHE_DIR)

    log_cb(f"🔍 Scanning {src_t} A→Z…", "head")
    all_media: list = []
    async for msg in client.iter_messages(src_e, min_id=resume_id, reverse=True):
        if stop_flag():
            log_cb("⏹ Stopped during scan.", "err")
            return
        if not msg.media:
            continue
        if database.is_processed(src, msg.id, db_path=db_path):
            cnt["skipped"] += 1
            continue

        mtype = fname = None
        fsize = 0
        if fwd_photo and isinstance(msg.media, tl_types.MessageMediaPhoto):
            mtype = "photo"
            fname = f"photo_{msg.id}.jpg"
        elif isinstance(msg.media, tl_types.MessageMediaDocument):
            doc = msg.media.document
            mime = getattr(doc, "mime_type", "") or ""
            fsize = getattr(doc, "size", 0) or 0
            for attr in getattr(doc, "attributes", []):
                if isinstance(attr, tl_types.DocumentAttributeFilename):
                    fname = getattr(attr, "file_name", None)
                    break
            if fwd_video and mime.startswith("video/"):
                mtype = "video"
                fname = fname or f"video_{msg.id}.mp4"
            elif fwd_audio and mime.startswith("audio/"):
                mtype = "audio"
                fname = fname or f"audio_{msg.id}.mp3"
            elif fwd_doc:
                mtype = "document"
                fname = fname or f"doc_{msg.id}.bin"
        if not mtype:
            continue

        all_media.append({"id": msg.id, "filename": fname, "size": fsize,
                           "mtype": mtype, "msg": msg})
        database.batch_file_record(bid, msg.id, fname or "", fsize, mtype, "pending",
                                    db_path=db_path)

        if len(all_media) % 100 == 0:
            log_cb(f"  …found {len(all_media)} files so far…", "")

    cnt["total"] = len(all_media)
    database.batch_upsert(bid, src, dst, cnt["total"], db_path=db_path)

    if not all_media:
        log_cb("✅ No new media — everything already forwarded!", "ok")
        return

    total_batches = (cnt["total"] + batch_size - 1) // batch_size
    log_cb(f"✅ Found {cnt['total']} files  |  {total_batches} batches of {batch_size}", "ok")
    progress_cb(0, cnt["total"])

    sem = asyncio.Semaphore(max_workers)
    pending: set = set()

    async def _fwd_one(item: dict) -> None:
        async with sem:
            msg = item["msg"]
            mtype = item["mtype"]
            fname = item["filename"] or f"file_{msg.id}"
            dpath = os.path.join(BATCH_CACHE_DIR, f"{msg.id}_{fname}")
            path = None
            try:
                for att in range(3):
                    await gate.wait_if_tripped()
                    try:
                        path = await client.download_media(msg, file=dpath)
                        break
                    except errors.FloodWaitError as e:
                        await gate.trip(e.seconds + 1)
                    except errors.FileReferenceExpiredError:
                        # The scan phase can run long before this download
                        # actually happens, and Telegram's file_reference
                        # tokens expire — re-fetch the message for a fresh
                        # one instead of retrying the same stale reference.
                        log_cb(f"  🔄 Refreshing expired file reference: {fname}", "info")
                        try:
                            fresh = await client.get_messages(src_e, ids=msg.id)
                            if fresh is not None and fresh.media:
                                msg = fresh
                                item["msg"] = fresh
                        except Exception:
                            pass
                        await asyncio.sleep(1)
                    except Exception:
                        await asyncio.sleep(2)
                if not path or not os.path.exists(path):
                    cnt["failed"] += 1
                    database.batch_file_record(bid, msg.id, fname, item["size"], mtype,
                                                "dl_failed", db_path=db_path)
                    log_cb(f"  ❌ DL failed: {fname}", "err")
                    return

                oc = msg.message or ""
                caption = ("" if cap_mode == "clear" else oc if cap_mode == "keep" else "")

                try:
                    fsz = os.path.getsize(str(path))
                    pkb = min(512, (max(512, int(fsz / (3000 * 1024)) + 1) + 511) // 512 * 512)
                except Exception:
                    pkb = 512

                dur = w = h = perf = ttag = None
                if isinstance(msg.media, tl_types.MessageMediaDocument):
                    for a in getattr(msg.media.document, "attributes", []):
                        if isinstance(a, tl_types.DocumentAttributeVideo):
                            dur, w, h = a.duration, a.w, a.h
                        elif isinstance(a, tl_types.DocumentAttributeAudio):
                            dur, perf, ttag = a.duration, a.performer, a.title

                for att in range(3):
                    await gate.wait_if_tripped()
                    try:
                        if mtype == "photo":
                            await client.send_file(
                                cast(Any, dst_e), path, caption=caption,
                                allow_cache=False, part_size_kb=pkb,
                            )
                        elif mtype == "video":
                            await client.send_file(
                                cast(Any, dst_e), path, caption=caption,
                                allow_cache=False, part_size_kb=pkb,
                                attributes=[tl_types.DocumentAttributeVideo(
                                    duration=int(dur or 0), w=int(w or 0), h=int(h or 0),
                                    supports_streaming=True)],
                                force_document=False,
                            )
                        elif mtype == "audio":
                            await client.send_file(
                                cast(Any, dst_e), path, caption=caption,
                                allow_cache=False, part_size_kb=pkb,
                                attributes=[tl_types.DocumentAttributeAudio(
                                    duration=int(dur or 0), performer=perf or "", title=ttag or "")],
                            )
                        else:
                            await client.send_file(
                                cast(Any, dst_e), path, caption=caption,
                                allow_cache=False, part_size_kb=pkb,
                                attributes=[tl_types.DocumentAttributeFilename(fname)],
                            )
                        cnt["sent"] += 1
                        database.batch_file_record(bid, msg.id, fname, item["size"], mtype,
                                                    "done", db_path=db_path)
                        break
                    except errors.FloodWaitError as e:
                        await gate.trip(e.seconds + 1)
                    except Exception:
                        if att == 2:
                            cnt["failed"] += 1
                            database.batch_file_record(bid, msg.id, fname, item["size"], mtype,
                                                        "ul_failed", db_path=db_path)
                            log_cb(f"  ❌ UL failed: {fname}", "err")
                        await asyncio.sleep(3)
            finally:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
            progress_cb(cnt["sent"], cnt["total"])

    for batch_start in range(0, cnt["total"], batch_size):
        if stop_flag():
            database.batch_progress(bid, cnt["sent"], cnt["failed"], cnt["bnum"], 0,
                                     "paused", db_path=db_path)
            log_cb(f"⏹ Stopped. Sent {cnt['sent']}/{cnt['total']}. "
                   "Restart app and click Start to resume.", "err")
            return

        batch_items = all_media[batch_start:batch_start + batch_size]
        cnt["bnum"] += 1
        total_batches = (cnt["total"] + batch_size - 1) // batch_size
        pct = cnt["sent"] * 100 // max(cnt["total"], 1)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)

        log_cb(f"📦 Batch {cnt['bnum']}/{total_batches}  "
               f"[{batch_start+1}–{min(batch_start+batch_size, cnt['total'])}]  "
               f"sent={cnt['sent']}  failed={cnt['failed']}  {pct}% [{bar}]", "head")

        for item in batch_items:
            if stop_flag():
                # Wait for pending tasks to complete gracefully
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                    pending.clear()
                database.batch_progress(bid, cnt["sent"], cnt["failed"], cnt["bnum"], 0,
                                         "paused", db_path=db_path)
                log_cb(f"⏹ Stopped. Sent {cnt['sent']}/{cnt['total']}. "
                       "Restart app and click Start to resume.", "err")
                return
            task = asyncio.create_task(_fwd_one(item))
            pending.add(task)
            task.add_done_callback(pending.discard)
            while len(pending) >= max_workers * 2:
                await asyncio.sleep(0.1)

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            pending.clear()

        last_id = batch_items[-1]["id"] if batch_items else 0
        database.batch_progress(bid, cnt["sent"], cnt["failed"], cnt["bnum"], last_id,
                                 db_path=db_path)
        if batch_start + batch_size < cnt["total"]:
            await asyncio.sleep(2)

    database.batch_progress(bid, cnt["sent"], cnt["failed"], cnt["bnum"], 0, "done",
                             db_path=db_path)
    progress_cb(cnt["sent"], cnt["total"])
    log_cb(f"🏁 DONE!  Total={cnt['total']}  Sent={cnt['sent']}  "
           f"Failed={cnt['failed']}  Skipped={cnt['skipped']}  Batches={cnt['bnum']}", "ok")
