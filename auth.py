"""Telegram session/login logic — GUI-agnostic, pure asyncio.

Kept independent of Tkinter so it can be reused by the web UI, a future CLI,
or tests. The interactive phone/OTP/2FA prompts still go through stdin by
default (matching the original console-driven flow); pass custom callables to
run them elsewhere (e.g. from a GUI dialog).
"""

import asyncio
from typing import Any, Callable, Dict, Optional

InputFn = Callable[[str], str]


def _import_telethon():
    try:
        from telethon import TelegramClient, errors
        from telethon.sessions import StringSession
        return TelegramClient, errors, StringSession
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Missing Python dependency 'telethon'. Add it to Chaquopy pip dependencies and rebuild the app."
        ) from e


def _default_prompt(prompt: str) -> str:
    return input(prompt).strip()


async def _ask(loop: asyncio.AbstractEventLoop, prompt_fn: InputFn, prompt: str) -> str:
    return await loop.run_in_executor(None, lambda: prompt_fn(prompt))


_current_client: Optional[TelegramClient] = None
_current_phone: Optional[str] = None
_current_phone_code_hash: Optional[str] = None


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_client_async(api_id: int, api_hash: str):
    TelegramClient, _, StringSession = _import_telethon()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    return client


async def request_otp_async(api_id: int, api_hash: str, phone: str) -> str:
    global _current_client, _current_phone, _current_phone_code_hash
    if _current_client is not None:
        try:
            await _current_client.disconnect()
        except Exception:
            pass
    _current_client = await _create_client_async(api_id, api_hash)
    sent = await _current_client.send_code_request(phone)
    _current_phone = phone
    _current_phone_code_hash = getattr(sent, "phone_code_hash", None)
    return "OTP sent to phone"


async def sign_in_async(code: str, password: Optional[str] = None) -> str:
    global _current_client, _current_phone, _current_phone_code_hash
    if _current_client is None or _current_phone_code_hash is None or _current_phone is None:
        raise RuntimeError("Please request OTP first.")
    _, errors, _ = _import_telethon()
    try:
        await _current_client.sign_in(
            phone=_current_phone,
            code=code,
            phone_code_hash=_current_phone_code_hash,
        )
    except errors.SessionPasswordNeededError:
        if password is None:
            raise RuntimeError("Two-factor password is required.")
        await _current_client.sign_in(password=password)
    session_str = _current_client.session.save()
    await _current_client.disconnect()
    _current_client = None
    _current_phone = None
    _current_phone_code_hash = None
    return session_str


def request_otp_sync(api_id: int, api_hash: str, phone: str) -> str:
    return _run_async(request_otp_async(api_id, api_hash, phone))


def sign_in_sync(code: str, password: Optional[str] = None) -> str:
    return _run_async(sign_in_async(code, password))


async def generate_session_async(
    api_id: int,
    api_hash: str,
    phone_prompt: InputFn = _default_prompt,
    code_prompt: InputFn = _default_prompt,
    password_prompt: InputFn = _default_prompt,
    two_factor_prompt: InputFn = _default_prompt,
) -> str:
    """Interactive session generator. Returns a StringSession string."""
    TelegramClient, errors, StringSession = _import_telethon()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    loop = asyncio.get_event_loop()

    if not await client.is_user_authorized():
        phone = await _ask(loop, phone_prompt,
                            "\n📱 Enter phone number (e.g. +91xxxxxxxxxx): ")
        await client.send_code_request(phone)

        code = await _ask(loop, code_prompt, "🔑 Enter the OTP code you received: ")
        try:
            await client.sign_in(phone, code)
        except errors.SessionPasswordNeededError:
            pwd = await _ask(loop, two_factor_prompt, "🔐 Enter your 2FA password: ")
            await client.sign_in(password=pwd)
        except Exception as e:
            await client.disconnect()
            raise RuntimeError(f"Sign-in failed: {e}")

    session_str = client.session.save()
    me = await client.get_me()
    print(f"\n✅ Logged in as {getattr(me, 'first_name', 'User')}")
    await client.disconnect()
    return session_str


async def qr_login_async(
    api_id: int,
    api_hash: str,
    on_qr_url: Callable[[str], None],
    password_prompt: InputFn = _default_prompt,
    timeout: float = 60.0,
) -> str:
    """QR-code login, mirroring Telegram Desktop's "log in by scanning" flow.

    Calls on_qr_url(url) with a `tg://login?token=...` URL for the caller to
    render as a QR code; regenerates and re-calls it if the code expires
    before being scanned. Prompts for a 2FA password if the account has one.
    Returns a StringSession string on success.
    """
    TelegramClient, errors, StringSession = _import_telethon()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    loop = asyncio.get_event_loop()

    qr = await client.qr_login()
    on_qr_url(qr.url)

    while True:
        try:
            await qr.wait(timeout=timeout)
            break
        except errors.SessionPasswordNeededError:
            pwd = await _ask(loop, password_prompt, "🔐 Enter your 2FA password: ")
            await client.sign_in(password=pwd)
            break
        except asyncio.TimeoutError:
            await qr.recreate()
            on_qr_url(qr.url)

    session_str = client.session.save()
    await client.disconnect()
    return session_str


def validate_session_string(session_str: str) -> None:
    """Raise RuntimeError with a helpful message if the session string is
    missing or malformed."""
    if not (session_str or "").strip():
        raise RuntimeError(
            "Session string is empty.\n\n"
            "Delete telegram_config.json and restart to re-enter credentials,\n"
            "or use the 'Generate Session' button."
        )
    _, _, StringSession = _import_telethon()
    try:
        StringSession(session_str)
    except Exception as e:
        raise RuntimeError(
            f"Invalid session string format: {e}\n\n"
            "Delete telegram_config.json and restart to generate a new one."
        )


async def start_client(config: Dict[str, Any]) -> Dict[str, Any]:
    """Connect and authorize a TelegramClient from a saved config.

    Returns {"client": TelegramClient, "name": str, "premium": bool}.
    """
    session_str = (config.get("session_string") or "").strip()
    validate_session_string(session_str)

    TelegramClient, _, StringSession = _import_telethon()
    client = TelegramClient(
        StringSession(session_str),
        int(config["api_id"]),
        config["api_hash"],
    )
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Session not authorized — regenerate session string.")

    me = await client.get_me()
    return {
        "client": client,
        "name": getattr(me, "first_name", "User") or "User",
        "premium": bool(getattr(me, "premium", False)),
    }
