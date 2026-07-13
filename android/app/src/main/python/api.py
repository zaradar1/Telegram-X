import auth
import database
from downloader import DownloadQueue

database.init_db()
_queue = DownloadQueue()


def send_code(phone, api_id, api_hash):
    return auth.send_code(phone, api_id, api_hash)


def verify_code(phone, code):
    return auth.verify_code(phone, code)


def verify_2fa(phone, password):
    return auth.verify_2fa(phone, password)


def is_logged_in(phone):
    return auth.is_logged_in(phone)


def logout(phone):
    auth.logout(phone)


def list_accounts():
    return auth.list_accounts()


def list_chats(phone):
    account = auth.get_account(phone)
    if not account:
        return []

    async def _list():
        client = auth._client_for(account["api_id"], account["api_hash"], account["session_string"])
        await client.connect()
        chats = []
        try:
            async for dialog in client.iter_dialogs():
                chats.append({
                    "id": dialog.id,
                    "name": dialog.name or "",
                    "is_group": bool(dialog.is_group),
                    "is_channel": bool(dialog.is_channel),
                    "is_user": bool(dialog.is_user),
                    "unread": dialog.unread_count,
                })
        finally:
            await client.disconnect()
        return chats

    return auth._run(_list())


def start_bulk_download(phone, chat_id, limit):
    account = auth.get_account(phone)
    if not account:
        return {"ok": False, "error": "Not logged in"}
    job_id = _queue.start_download(account, int(chat_id), int(limit))
    return {"ok": True, "job_id": job_id}


def job_status(job_id):
    return _queue.status(job_id)


def list_jobs():
    return _queue.list_jobs()


def pause_job(job_id):
    _queue.pause(job_id)


def resume_job(job_id):
    _queue.resume(job_id)


def stop_job(job_id):
    _queue.stop(job_id)


def search_messages(query, limit=50):
    return database.search_messages(query, limit)


def list_duplicates():
    return database.list_duplicates()
