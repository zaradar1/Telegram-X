"""Detect archive/file passwords embedded in message text or captions."""

import re
from typing import Optional

PASSWORD_PATTERNS = [
    # Require a punctuation delimiter (":", "=", "-") between the keyword and
    # the value — bare whitespace ("password here") produces too many false
    # positives on ordinary prose.
    re.compile(r'(?:password|pass|pwd|pw|key)\s*[:=\-]\s*([^\s]+)', re.IGNORECASE),
    re.compile(r'🔑\s*([^\s]+)'),
    re.compile(r'رمز(?:\s*المرور)?\s*[:=\-]\s*([^\s]+)'),  # Arabic "password"
]


def extract_password(text: Optional[str]) -> Optional[str]:
    """Return the first password-looking token found in text, or None."""
    if not text:
        return None
    for pattern in PASSWORD_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip('.,:;!?()[]{}"\'')
            if candidate:
                return candidate
    return None
