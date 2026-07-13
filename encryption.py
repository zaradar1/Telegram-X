"""Session-string encryption at rest.

Stores the encryption key in the OS keyring when a backend is available
(macOS Keychain, Windows Credential Locker, GNOME Keyring/KWallet via Secret
Service on Linux). Falls back to a locally-stored key file with restricted
permissions when no keyring backend exists — weaker (anyone who can read
your files can read the key file too), but still keeps the session string
out of plain JSON, and degrades no worse than before this existed.
"""

import base64
import os
import stat
from typing import Dict

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KEYRING_SERVICE = "telegram_manager"
KEYRING_USERNAME = "session_encryption_key"
LOCAL_KEY_FILE = ".tg_manager_key"


def _get_or_create_key() -> bytes:
    try:
        import keyring
        existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if existing:
            return existing.encode()
        key = Fernet.generate_key()
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode())
        return key
    except Exception:
        pass  # no usable keyring backend on this system — use a local key file

    if os.path.exists(LOCAL_KEY_FILE):
        with open(LOCAL_KEY_FILE, "rb") as f:
            return f.read().strip()

    key = Fernet.generate_key()
    with open(LOCAL_KEY_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(LOCAL_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    return key


def encrypt(plaintext: str) -> str:
    """Encrypt a session string for storage. Empty input passes through."""
    if not plaintext:
        return ""
    return Fernet(_get_or_create_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a session string. If the input isn't a valid Fernet token —
    e.g. a plaintext session saved before encryption was added — it's
    returned as-is so existing configs keep working until next save."""
    if not ciphertext:
        return ""
    try:
        return Fernet(_get_or_create_key()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return ciphertext


def _derive_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def export_encrypt(plaintext: str, password: str) -> Dict[str, str]:
    """Re-encrypt plaintext with a password you choose, for a portable
    backup file that isn't tied to this machine's keyring/key file."""
    salt = os.urandom(16)
    key = _derive_key_from_password(password, salt)
    token = Fernet(key).encrypt(plaintext.encode())
    return {"salt": base64.b64encode(salt).decode(), "token": token.decode()}


def export_decrypt(blob: Dict[str, str], password: str) -> str:
    """Reverse of export_encrypt. Raises InvalidToken on a wrong password."""
    salt = base64.b64decode(blob["salt"])
    key = _derive_key_from_password(password, salt)
    return Fernet(key).decrypt(blob["token"].encode()).decode()
