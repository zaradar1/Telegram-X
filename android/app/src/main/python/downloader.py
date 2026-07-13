import asyncio
import hashlib
import os
import threading
import time
import uuid

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

import database
from settings import DOWNLOAD_DIR


class FloodWaitGate:
    """Shared cooldown so all workers back off together after a FloodWaitError."""

    def __init__(self):
        self._until = 0.0
        self._lock = threading.Lock()

    def trip(self, seconds: float):
        with self._lock:
            self._until = max(self._until, time.monotonic() + seconds)

    async def wait(self):
        while True:
            with self._lock:
                remaining = self._until - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 5))


class DownloadJob:
    def __init__(self, job_id, account, chat_id, limit):
        self.job_id = job_id
        self.account = account
        self.chat_id = chat_id
        self.limit = limit
        self.status = "pending"
        self.total = 0
        self.completed = 0
        self.failed = 0

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "chat_id": self.chat_id,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
        }


def _hash_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


class DownloadQueue:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()
        self._gate = FloodWaitGate()

    def start_download(self, account, chat_id, limit):
        job_id = uuid.uuid4().hex[:8]
        job = DownloadJob(job_id, account, chat_id, limit)
        with self._lock:
            self._jobs[job_id] = job
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()
        return job_id

    def _run_job(self, job: DownloadJob):
        job.status = "running"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._download(job))
        except Exception as e:
            job.status = f"error: {e}"
        finally:
            loop.close()

    async def _download(self, job: DownloadJob):
        client = TelegramClient(
            StringSession(job.account["session_string"]),
            int(job.account["api_id"]),
            job.account["api_hash"],
        )
        await client.connect()
        try:
            save_dir = os.path.join(DOWNLOAD_DIR, str(job.chat_id))
            os.makedirs(save_dir, exist_ok=True)

            async for msg in client.iter_messages(job.chat_id, limit=job.limit):
                if job.status == "stopped":
                    break
                while job.status == "paused":
                    await asyncio.sleep(1)

                if not msg.media:
                    continue
                if database.is_downloaded(job.account["id"], job.chat_id, msg.id):
                    continue

                job.total += 1
                await self._gate.wait()
                try:
                    path = await client.download_media(msg, file=save_dir + os.sep)
                    if path:
                        file_hash = _hash_file(path)
                        database.record_download(job.account["id"], job.chat_id, msg.id, path, file_hash)
                        job.completed += 1
                    else:
                        job.failed += 1
                except errors.FloodWaitError as e:
                    self._gate.trip(e.seconds)
                    await asyncio.sleep(e.seconds)
                    job.failed += 1
                except Exception:
                    job.failed += 1

            if job.status != "stopped":
                job.status = "finished"
        finally:
            await client.disconnect()

    def status(self, job_id):
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def list_jobs(self):
        return [j.to_dict() for j in self._jobs.values()]

    def pause(self, job_id):
        job = self._jobs.get(job_id)
        if job and job.status == "running":
            job.status = "paused"

    def resume(self, job_id):
        job = self._jobs.get(job_id)
        if job and job.status == "paused":
            job.status = "running"

    def stop(self, job_id):
        job = self._jobs.get(job_id)
        if job:
            job.status = "stopped"
