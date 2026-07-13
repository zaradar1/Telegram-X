"""LibreTranslate wrapper — tries multiple public mirrors, first one wins."""

import json
import urllib.request
from typing import Callable, Dict, List, Optional

from settings import LIBRETRANSLATE_MIRRORS


def translate_one(text: str, target_lang: str, timeout: int = 8) -> str:
    """Translate a single string. Returns '' on failure (all mirrors down)."""
    if not text:
        return ""
    payload = json.dumps({
        "q": text, "source": "auto", "target": target_lang, "format": "text",
    }).encode("utf-8")
    for mirror in LIBRETRANSLATE_MIRRORS:
        try:
            req = urllib.request.Request(
                mirror, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
                translated = result.get("translatedText", "")
                if translated:
                    return translated
        except Exception:
            continue
    return ""


def translate_all(messages: List[Dict], target_lang: str,
                   progress_cb: Optional[Callable[[int, int], None]] = None) -> List[Dict]:
    """Translate item['text'] for each message dict in place, storing the
    result under item['translated']. Meant to run off the UI thread."""
    total = len(messages)
    for i, item in enumerate(messages):
        if progress_cb:
            progress_cb(i + 1, total)
        item["translated"] = translate_one(item["text"], target_lang)
    return messages
