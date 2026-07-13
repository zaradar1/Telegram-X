import asyncio
import threading

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from database import get_db, init_db

init_db()

_loop = None
_loop_thread = None
_pending = {}  # phone -> {"session": str, "phone_code_hash": str, "api_id": int, "api_hash": str}


def _ensure_loop():
    global _loop, _loop_thread
    if _loop is None:
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop


def _run(coro):
    loop = _ensure_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def _client_for(api_id, api_hash, session_string=""):
    return TelegramClient(StringSession(session_string or ""), int(api_id), api_hash)


def save_account(phone, api_id, api_hash, session_string):
    conn = get_db()
    conn.execute(
        "INSERT INTO accounts (phone, api_id, api_hash, session_string) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(phone) DO UPDATE SET api_id=excluded.api_id, api_hash=excluded.api_hash, "
        "session_string=excluded.session_string",
        (phone, int(api_id), api_hash, session_string),
    )
    conn.commit()


def get_account(phone):
    conn = get_db()
    row = conn.execute("SELECT * FROM accounts WHERE phone = ?", (phone,)).fetchone()
    return dict(row) if row else None


def list_accounts():
    conn = get_db()
    rows = conn.execute("SELECT id, phone, api_id FROM accounts ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def is_logged_in(phone):
    account = get_account(phone)
    if not account or not account.get("session_string"):
        return False

    async def _check():
        client = _client_for(account["api_id"], account["api_hash"], account["session_string"])
        await client.connect()
        try:
            return await client.is_user_authorized()
        finally:
            await client.disconnect()

    return _run(_check())


def send_code(phone, api_id, api_hash):
    async def _send():
        client = _client_for(api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return {"ok": True, "phone_code_hash": sent.phone_code_hash, "session": client.session.save()}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            await client.disconnect()

    result = _run(_send())
    if result.get("ok"):
        _pending[phone] = {
            "session": result["session"],
            "phone_code_hash": result["phone_code_hash"],
            "api_id": int(api_id),
            "api_hash": api_hash,
        }
    return result


def verify_code(phone, code):
    pending = _pending.get(phone)
    if not pending:
        return {"ok": False, "error": "No pending login for this phone. Send the code again."}

    async def _verify():
        client = _client_for(pending["api_id"], pending["api_hash"], pending["session"])
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=pending["phone_code_hash"])
            return {"ok": True, "needs_2fa": False, "session": client.session.save()}
        except errors.SessionPasswordNeededError:
            return {"ok": False, "needs_2fa": True, "session": client.session.save()}
        except Exception as e:
            return {"ok": False, "needs_2fa": False, "error": str(e)}
        finally:
            await client.disconnect()

    result = _run(_verify())
    if result.get("needs_2fa"):
        pending["session"] = result["session"]
    elif result.get("ok"):
        save_account(phone, pending["api_id"], pending["api_hash"], result["session"])
        _pending.pop(phone, None)
    return result


def verify_2fa(phone, password):
    pending = _pending.get(phone)
    if not pending:
        return {"ok": False, "error": "No pending login for this phone."}

    async def _verify():
        client = _client_for(pending["api_id"], pending["api_hash"], pending["session"])
        await client.connect()
        try:
            await client.sign_in(password=password)
            return {"ok": True, "session": client.session.save()}
        except errors.PasswordHashInvalidError:
            return {"ok": False, "error": "Invalid 2FA password."}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            await client.disconnect()

    result = _run(_verify())
    if result.get("ok"):
        save_account(phone, pending["api_id"], pending["api_hash"], result["session"])
        _pending.pop(phone, None)
    return result


def logout(phone):
    conn = get_db()
    conn.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
    conn.commit()
    _pending.pop(phone, None)
