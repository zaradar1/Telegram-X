"""Shared helpers used across telegram_manager modules."""

import hashlib
import os
import re

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def format_size(num_bytes: float) -> str:
    """Human-readable file size, e.g. 1536 -> '1.5 KB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def clean_filename(name: str, max_length: int = 200) -> str:
    """Strip characters that are invalid in filenames on common filesystems."""
    name = _INVALID_FILENAME_CHARS.sub("_", name or "").strip()
    return name[:max_length] if len(name) > max_length else name


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def compute_sha256(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """Stream-hash a file with SHA256 without loading it fully into memory."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha.update(chunk)
    return sha.hexdigest()


def chunked(seq, size: int):
    """Yield successive `size`-sized chunks from seq."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
