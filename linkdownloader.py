"""Best-effort downloader for plain URLs found in message text.

Handles direct file links and Google Drive share links (its public,
unauthenticated `uc?export=download` endpoint — no login/CAPTCHA bypass
involved). Anything that comes back as an HTML page is skipped, since sites
like Mega or Mediafire require host-specific, often authenticated, download
flows this doesn't attempt to reproduce.
"""

import os
import re
import urllib.parse
from typing import List, Optional

import requests

from utils import clean_filename, ensure_dir

URL_PATTERN = re.compile(r'https?://[^\s<>"\')]+')

GDRIVE_ID_RE = re.compile(
    r'drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([\w-]+)'
)

DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB safety cap per file


def extract_links(text: Optional[str]) -> List[str]:
    """Return every http(s) URL found in a block of message text."""
    if not text:
        return []
    return URL_PATTERN.findall(text)


def _resolve_google_drive(url: str) -> str:
    m = GDRIVE_ID_RE.search(url)
    if not m:
        return url
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}"


def _filename_from_response(url: str, resp: "requests.Response") -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    if m:
        return urllib.parse.unquote(m.group(1))
    path = urllib.parse.urlparse(url).path
    return os.path.basename(path) or "downloaded_file"


def download_url(url: str, dest_dir: str, timeout: int = 30,
                  max_bytes: int = DEFAULT_MAX_BYTES) -> Optional[str]:
    """Download a single URL into dest_dir. Returns the saved path, or None
    if the link isn't a downloadable file (e.g. it resolved to an HTML page)
    or exceeded max_bytes."""
    ensure_dir(dest_dir)
    resolved = _resolve_google_drive(url)
    session = requests.Session()
    resp = session.get(resolved, stream=True, timeout=timeout, allow_redirects=True)

    # Google Drive shows an interstitial ("can't scan this file for viruses")
    # for large files, guarded by a confirm token stashed in a cookie.
    if "drive.google.com" in resolved and "text/html" in resp.headers.get("Content-Type", ""):
        token = next((v for k, v in resp.cookies.items() if k.startswith("download_warning")), None)
        if token:
            resp.close()
            resp = session.get(resolved, params={"confirm": token}, stream=True, timeout=timeout)

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        resp.close()
        return None

    fname = clean_filename(_filename_from_response(resolved, resp))
    dest_path = os.path.join(dest_dir, fname)

    written = 0
    try:
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    f.close()
                    os.remove(dest_path)
                    return None
                f.write(chunk)
    finally:
        resp.close()

    if written == 0:
        os.remove(dest_path)
        return None
    return dest_path
