"""Unified synchronous API layer for Android Kotlin UI to call."""

import asyncio
import os
import json
from typing import Optional

# Import backend modules
import auth
import database
import downloader
import export
import duplicate
import search
import sync
import archive
import translator
import password
import linkdownloader

import threading

_loop = asyncio.new_event_loop()

def _start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_loop, args=(_loop,), daemon=True)
_thread.start()

def _run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()

# AUTH & DB
def request_otp_sync(api_id: int, api_hash: str, phone: str):
    return _run_async(auth.request_otp_sync(api_id, api_hash, phone))

def sign_in_sync(code: str, pwd: str):
    return _run_async(auth.sign_in_sync(code, pwd))

def init_db():
    database.init_db()
    return "Database Initialized"

def get_accounts_sync():
    return json.dumps(database.get_accounts())

# DOWNLOADER
def start_download_channel_sync(channel_id: int, dl_dir: str, max_concurrent: int = 4):
    client_info = _run_async(auth.start_client({})) 
    client = client_info.get("client")
    if not client: return "Not authenticated."
    
    def log_status(msg):
        print(msg) 
        
    async def task():
        entity = await client.get_entity(channel_id)
        downloaded = await downloader.download_channel_media(
            client=client, 
            entity=entity,
            channel_id=channel_id,
            dl_dir=dl_dir,
            max_concurrent=max_concurrent,
            status_cb=log_status
        )
        await client.disconnect()
        return downloaded

    return _run_async(task())

def auto_batch_forward_sync(src: str, dst: str, fwd_photo: bool, fwd_video: bool, fwd_audio: bool, fwd_doc: bool, cap_mode: str):
    client_info = _run_async(auth.start_client({}))
    client = client_info.get("client")
    if not client: return "Not authenticated."
    
    def log_cb(msg, lvl): print(f"[{lvl}] {msg}")
    def prog_cb(cur, tot): print(f"Progress: {cur}/{tot}")
    def stop_cb(): return False

    async def task():
        await downloader.auto_batch_forward(
            client, src, dst, fwd_photo, fwd_video, fwd_audio, fwd_doc,
            cap_mode, log_cb, prog_cb, stop_cb
        )
        await client.disconnect()
    
    _run_async(task())
    return "Batch forward complete."

# SYNC
def start_sync_sync(interval_minutes: int):
    # Usually APScheduler jobs are run in their own loop, we will just call the module
    sync.start()
    return f"Started Sync daemon with interval: {interval_minutes}m."

def stop_sync_sync():
    sync.stop()
    return "Sync stopped."

# DATA (DUPLICATES, EXPORT, SEARCH)
def find_duplicates_sync(channel_id: int) -> str:
    groups = duplicate.get_channel_duplicate_groups(channel_id)
    return json.dumps(groups)

def delete_duplicates_sync(channel_id: int, msg_ids: list):
    database.delete_messages_and_related(channel_id, msg_ids, remove_files=True)
    return f"Deleted {len(msg_ids)} duplicates."

def export_data_sync(channel_id: int, fmt: str, dest_file: str):
    rows = database.get_messages(channel_id)
    if not rows: return "No data found for export."
    export.export(rows, dest_file, fmt)
    return f"Exported {len(rows)} messages to {dest_file}"

def search_messages_sync(query: str, channel_id: int) -> str:
    results = search.search_messages(query, channel_id)
    return json.dumps([dict(r) for r in results]) if results else "[]"

# TOOLS (TRANSLATOR, PASSWORD, ARCHIVE)
def translate_text_sync(text: str, target_lang: str) -> str:
    return translator.translate_one(text, target_lang)

def generate_password_sync(length: int) -> str:
    import string, random
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

def create_archive_sync(dest_zip: str, source_files: list):
    import zipfile
    with zipfile.ZipFile(dest_zip, 'w') as zf:
        for f in source_files:
            if os.path.exists(f):
                zf.write(f, os.path.basename(f))
    return f"Archived {len(source_files)} files."

def extract_archive_sync(zip_path: str, dest_dir: str):
    return archive.extract_all(zip_path, dest_dir)

def extract_password_sync(text: str) -> str:
    pwd = password.extract_password(text)
    return pwd if pwd else "No password found."
