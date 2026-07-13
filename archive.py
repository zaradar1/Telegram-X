"""ZIP archive browsing — list and selectively extract without unpacking
the whole archive first. Stdlib only (no RAR/7z, which need external
system binaries/libraries beyond what pip can install)."""

import os
import zipfile
from typing import Any, Dict, List, Optional


def is_zip(file_path: str) -> bool:
    return zipfile.is_zipfile(file_path)


def list_contents(file_path: str) -> List[Dict[str, Any]]:
    """List every entry in a ZIP archive with name/size/compressed-size/
    is_dir, without extracting anything."""
    entries: List[Dict[str, Any]] = []
    with zipfile.ZipFile(file_path) as zf:
        for info in zf.infolist():
            entries.append({
                "name": info.filename,
                "size": info.file_size,
                "compressed_size": info.compress_size,
                "is_dir": info.is_dir(),
                "date": "%04d-%02d-%02d %02d:%02d" % info.date_time[:5],
            })
    return entries


def extract_selected(file_path: str, names: List[str], dest_dir: str,
                      password: Optional[str] = None) -> List[str]:
    """Extract only the given entry names into dest_dir. Returns the list
    of paths actually written."""
    os.makedirs(dest_dir, exist_ok=True)
    pwd = password.encode() if password else None
    written = []
    with zipfile.ZipFile(file_path) as zf:
        for name in names:
            zf.extract(name, path=dest_dir, pwd=pwd)
            written.append(os.path.join(dest_dir, name))
    return written


def extract_all(file_path: str, dest_dir: str, password: Optional[str] = None) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    pwd = password.encode() if password else None
    with zipfile.ZipFile(file_path) as zf:
        zf.extractall(path=dest_dir, pwd=pwd)
    return dest_dir
