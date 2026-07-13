"""Duplicate file detection: hash downloaded media and cross-reference the index."""

import os
from typing import Dict, List, Optional

import database
from utils import compute_sha256


def register_file(file_path: str, channel_id: int, msg_id: int,
                   db_path: str = database.DB_FILE) -> Dict:
    """Hash a downloaded file, store the hash, and report whether it's a
    duplicate of something already indexed."""
    file_hash = compute_sha256(file_path)
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    database.set_message_hash(channel_id, msg_id, file_hash, db_path=db_path)
    refs = database.register_duplicate(
        file_hash, channel_id, msg_id, file_name, file_size, db_path=db_path)

    return {
        "hash": file_hash,
        "size": file_size,
        "is_duplicate": len(refs) > 1,
        "refs": refs,
    }


def find_duplicates(db_path: str = database.DB_FILE) -> List[Dict]:
    """All hash groups that have more than one associated message."""
    return database.get_duplicate_groups(db_path=db_path)


def check_hash_exists(file_path: str, db_path: str = database.DB_FILE) -> Optional[List[str]]:
    """Hash a candidate file before saving it; return existing refs if it's
    already in the index (so callers can skip the save/download)."""
    file_hash = compute_sha256(file_path)
    with database.get_conn(db_path) as c:
        row = c.execute(
            "SELECT msg_ids FROM duplicates WHERE hash=?", (file_hash,)
        ).fetchone()
    if row is None:
        return None
    return row["msg_ids"].split(",") if row["msg_ids"] else None
