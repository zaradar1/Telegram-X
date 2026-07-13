"""SQLite index: channels, messages, downloads, duplicates + legacy batch-forward tables.

Everything lives in one WAL-mode SQLite file (settings.DB_FILE) so the search
engine, duplicate detector, stats module, and web UI can all read/write the
same index without a network round-trip.
"""

import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from settings import DB_FILE

_lock = threading.RLock()


def get_conn(db_path: str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_FILE) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    with _lock, get_conn(db_path) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                id                INTEGER PRIMARY KEY,
                title             TEXT,
                username          TEXT,
                type              TEXT,      -- CHANNEL, GROUP, BOT
                is_premium        BOOLEAN DEFAULT 0,
                last_indexed_at   TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER,
                channel_id    INTEGER,
                sender_id     INTEGER,
                date          TIMESTAMP,
                text          TEXT,
                has_media     BOOLEAN DEFAULT 0,
                media_type    TEXT,      -- photo, video, audio, document
                file_name     TEXT,
                file_size     INTEGER DEFAULT 0,
                file_hash     TEXT,      -- SHA256, filled in after download
                caption       TEXT,
                password      TEXT,
                PRIMARY KEY (id, channel_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id);
            CREATE INDEX IF NOT EXISTS idx_messages_hash    ON messages(file_hash);
            CREATE INDEX IF NOT EXISTS idx_messages_fname   ON messages(file_name);

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                channel_id UNINDEXED, msg_id UNINDEXED,
                text, caption, file_name
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_id           INTEGER,
                channel_id       INTEGER,
                file_name        TEXT,
                file_path        TEXT,
                status           TEXT DEFAULT 'pending', -- pending, downloading, paused, done, failed
                priority         INTEGER DEFAULT 5,
                retries          INTEGER DEFAULT 0,
                downloaded_bytes INTEGER DEFAULT 0,
                total_bytes      INTEGER DEFAULT 0,
                start_time       TIMESTAMP,
                end_time         TIMESTAMP,
                UNIQUE(msg_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS duplicates (
                hash      TEXT PRIMARY KEY,
                msg_ids   TEXT,     -- comma-separated "channel_id:msg_id"
                file_name TEXT,
                file_size INTEGER
            );

            CREATE TABLE IF NOT EXISTS links (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id    INTEGER,
                msg_id        INTEGER,
                url           TEXT,
                status        TEXT DEFAULT 'pending', -- pending, downloaded, skipped, failed
                file_path     TEXT,
                file_size     INTEGER DEFAULT 0,
                discovered_at TEXT DEFAULT (datetime('now')),
                updated_at    TEXT DEFAULT (datetime('now')),
                UNIQUE(channel_id, msg_id, url)
            );
            CREATE INDEX IF NOT EXISTS idx_links_status ON links(status);

            CREATE TABLE IF NOT EXISTS batch_records (
                batch_id    TEXT PRIMARY KEY,
                src         TEXT,
                dst         TEXT,
                total_files INTEGER DEFAULT 0,
                sent        INTEGER DEFAULT 0,
                failed      INTEGER DEFAULT 0,
                batch_num   INTEGER DEFAULT 0,
                last_msg_id INTEGER DEFAULT 0,
                state       TEXT DEFAULT 'running',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS batch_files (
                batch_id    TEXT,
                msg_id      INTEGER,
                filename    TEXT,
                size        INTEGER DEFAULT 0,
                media_type  TEXT,
                status      TEXT DEFAULT 'pending',
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (batch_id, msg_id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                label          TEXT,
                api_id         INTEGER,
                api_hash       TEXT,
                session_string TEXT,   -- encrypted at rest, see encryption.py
                phone          TEXT,
                is_premium     BOOLEAN DEFAULT 0,
                is_current     BOOLEAN DEFAULT 0,
                last_login     TEXT,
                created_at     TEXT DEFAULT (datetime('now'))
            );
        """)


# ── Accounts (multi-account login) ─────────────────────────────────────
# session_string here is always the *encrypted* form — encrypt/decrypt at
# the call site (gui.py) via encryption.py; this module stays encryption-
# agnostic and just stores/retrieves whatever string it's given.

def add_account(label: str, api_id: int, api_hash: str, session_string: str,
                 phone: Optional[str] = None, is_premium: bool = False,
                 db_path: str = DB_FILE) -> int:
    """Insert a new account and mark it as the current one."""
    with _lock, get_conn(db_path) as c:
        c.execute("UPDATE accounts SET is_current=0")
        cur = c.execute(
            "INSERT INTO accounts (label, api_id, api_hash, session_string,"
            " phone, is_premium, is_current, last_login)"
            " VALUES (?,?,?,?,?,?,1,datetime('now'))",
            (label, api_id, api_hash, session_string, phone, is_premium),
        )
        return cur.lastrowid


def get_accounts(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    with get_conn(db_path) as c:
        rows = c.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_account(account_id: int, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    with get_conn(db_path) as c:
        row = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return dict(row) if row else None


def get_current_account(db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    with get_conn(db_path) as c:
        row = c.execute("SELECT * FROM accounts WHERE is_current=1 LIMIT 1").fetchone()
    return dict(row) if row else None


def set_current_account(account_id: int, db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute("UPDATE accounts SET is_current=0")
        c.execute("UPDATE accounts SET is_current=1, last_login=datetime('now') WHERE id=?",
                   (account_id,))


def update_account_session(account_id: int, session_string: Optional[str] = None,
                            is_premium: Optional[bool] = None, phone: Optional[str] = None,
                            db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "UPDATE accounts SET session_string=COALESCE(?, session_string),"
            " is_premium=COALESCE(?, is_premium), phone=COALESCE(?, phone),"
            " last_login=datetime('now') WHERE id=?",
            (session_string, is_premium, phone, account_id),
        )


def delete_account(account_id: int, db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))


# ── Channels ──────────────────────────────────────────────────────────

def upsert_channel(channel_id: int, title: str, username: Optional[str],
                    kind: str, is_premium: bool = False,
                    db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT INTO channels (id, title, username, type, is_premium, last_indexed_at)"
            " VALUES (?,?,?,?,?, datetime('now'))"
            " ON CONFLICT(id) DO UPDATE SET"
            " title=excluded.title, username=excluded.username, type=excluded.type,"
            " is_premium=excluded.is_premium, last_indexed_at=datetime('now')",
            (channel_id, title, username, kind, is_premium),
        )


def get_channels(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    with get_conn(db_path) as c:
        rows = c.execute("SELECT * FROM channels ORDER BY title").fetchall()
    return [dict(r) for r in rows]


# ── Messages ──────────────────────────────────────────────────────────

def upsert_message(channel_id: int, msg_id: int, sender_id: Optional[int],
                    date: str, text: str, has_media: bool,
                    media_type: Optional[str], file_name: Optional[str],
                    file_size: int, caption: Optional[str],
                    password: Optional[str] = None,
                    file_hash: Optional[str] = None,
                    db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT INTO messages (id, channel_id, sender_id, date, text, has_media,"
            " media_type, file_name, file_size, file_hash, caption, password)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id, channel_id) DO UPDATE SET"
            " sender_id=excluded.sender_id, date=excluded.date, text=excluded.text,"
            " has_media=excluded.has_media, media_type=excluded.media_type,"
            " file_name=excluded.file_name, file_size=excluded.file_size,"
            " file_hash=COALESCE(excluded.file_hash, messages.file_hash),"
            " caption=excluded.caption, password=excluded.password",
            (msg_id, channel_id, sender_id, date, text, has_media,
             media_type, file_name, file_size, file_hash, caption, password),
        )
        c.execute("DELETE FROM messages_fts WHERE channel_id=? AND msg_id=?",
                   (channel_id, msg_id))
        c.execute(
            "INSERT INTO messages_fts (channel_id, msg_id, text, caption, file_name)"
            " VALUES (?,?,?,?,?)",
            (channel_id, msg_id, text or "", caption or "", file_name or ""),
        )


def set_message_hash(channel_id: int, msg_id: int, file_hash: str,
                      db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "UPDATE messages SET file_hash=? WHERE id=? AND channel_id=?",
            (file_hash, msg_id, channel_id),
        )


def get_messages(channel_id: int, limit: Optional[int] = None,
                  db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM messages WHERE channel_id=? ORDER BY date DESC"
    params: List[Any] = [channel_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_conn(db_path) as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ── Downloads ─────────────────────────────────────────────────────────

def upsert_download(msg_id: int, channel_id: int, file_name: str,
                     file_path: str, status: str = "pending",
                     priority: int = 5, total_bytes: int = 0,
                     db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT INTO downloads (msg_id, channel_id, file_name, file_path,"
            " status, priority, total_bytes, start_time)"
            " VALUES (?,?,?,?,?,?,?, datetime('now'))"
            " ON CONFLICT(msg_id, channel_id) DO UPDATE SET"
            " status=excluded.status, file_path=excluded.file_path,"
            " total_bytes=excluded.total_bytes",
            (msg_id, channel_id, file_name, file_path, status, priority, total_bytes),
        )


def update_download_progress(msg_id: int, channel_id: int, downloaded_bytes: int,
                              status: Optional[str] = None,
                              db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        if status:
            c.execute(
                "UPDATE downloads SET downloaded_bytes=?, status=?,"
                " end_time=CASE WHEN ? IN ('done','failed') THEN datetime('now') ELSE end_time END"
                " WHERE msg_id=? AND channel_id=?",
                (downloaded_bytes, status, status, msg_id, channel_id),
            )
        else:
            c.execute(
                "UPDATE downloads SET downloaded_bytes=? WHERE msg_id=? AND channel_id=?",
                (downloaded_bytes, msg_id, channel_id),
            )


def get_downloads(status: Optional[str] = None,
                   db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM downloads"
    params: List[Any] = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY start_time DESC"
    with get_conn(db_path) as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ── Duplicates ────────────────────────────────────────────────────────

def register_duplicate(file_hash: str, channel_id: int, msg_id: int,
                        file_name: str, file_size: int,
                        db_path: str = DB_FILE) -> List[str]:
    """Record a file hash occurrence. Returns the full list of "channel:msg"
    refs sharing this hash (length > 1 means duplicates exist)."""
    ref = f"{channel_id}:{msg_id}"
    with _lock, get_conn(db_path) as c:
        row = c.execute(
            "SELECT msg_ids FROM duplicates WHERE hash=?", (file_hash,)
        ).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO duplicates (hash, msg_ids, file_name, file_size)"
                " VALUES (?,?,?,?)",
                (file_hash, ref, file_name, file_size),
            )
            return [ref]
        refs = row["msg_ids"].split(",") if row["msg_ids"] else []
        if ref not in refs:
            refs.append(ref)
            c.execute("UPDATE duplicates SET msg_ids=? WHERE hash=?",
                      (",".join(refs), file_hash))
        return refs


def get_duplicate_groups(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Only groups with more than one reference are real duplicates."""
    with get_conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM duplicates WHERE instr(msg_ids, ',') > 0"
            " ORDER BY file_size DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_channel_duplicate_groups(channel_id: int, db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Return duplicate media groups for a single channel from indexed messages."""
    with get_conn(db_path) as c:
        rows = c.execute(
            "SELECT id, file_name, file_size, file_hash FROM messages"
            " WHERE channel_id=? AND has_media=1 AND (file_hash IS NOT NULL OR file_name IS NOT NULL)"
            " ORDER BY file_size DESC, id ASC",
            (channel_id,),
        ).fetchall()

    groups: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = row["file_hash"] or f"{row['file_name'] or ''}|{row['file_size'] or 0}"
        if not key:
            continue
        group = seen.get(key)
        if group is None:
            group = {
                "hash": row["file_hash"] or key,
                "file_name": row["file_name"],
                "file_size": row["file_size"],
                "msg_ids": [],
                "msg_count": 0,
            }
            seen[key] = group
        group["msg_ids"].append(f"{channel_id}:{row['id']}")
        group["msg_count"] += 1

    for group in seen.values():
        if group["msg_count"] > 1:
            groups.append(group)
    return groups


def delete_messages_and_related(channel_id: int, msg_ids: List[int], remove_files: bool = False,
                                 db_path: str = DB_FILE) -> int:
    """Delete duplicate messages while preserving one item per duplicate group.

    msg_ids should be every message id in one or more duplicate groups; the
    lowest id in each group (file_hash or file_name match) is kept, the rest
    are removed from the index (and, if remove_files, from disk — file_name
    is only a real filesystem path here when the caller passes the on-disk
    download path rather than the original Telegram filename).
    """
    if not msg_ids:
        return 0

    with _lock, get_conn(db_path) as c:
        placeholders = ",".join("?" for _ in msg_ids)
        rows = c.execute(
            f"SELECT id, file_name, file_hash FROM messages WHERE channel_id=? AND id IN ({placeholders})",
            [channel_id, *msg_ids],
        ).fetchall()
        rows = sorted(rows, key=lambda row: row["id"])

        if not rows:
            return 0

        grouped: Dict[Optional[str], List[Any]] = {}
        for row in rows:
            key = row["file_hash"] or row["file_name"]
            grouped.setdefault(key, []).append(row)

        deleted_ids: List[int] = []
        for group_rows in grouped.values():
            if not group_rows:
                continue
            for row in group_rows[1:]:
                deleted_ids.append(row["id"])

        deleted_refs = {f"{channel_id}:{msg_id}" for msg_id in deleted_ids}
        for msg_id in deleted_ids:
            if remove_files:
                row = c.execute(
                    "SELECT file_name FROM messages WHERE id=? AND channel_id=?",
                    (msg_id, channel_id),
                ).fetchone()
                path = row["file_name"] if row else None
                if path and os.path.exists(path):
                    os.remove(path)
            c.execute("DELETE FROM messages WHERE id=? AND channel_id=?", (msg_id, channel_id))
            c.execute("DELETE FROM messages_fts WHERE channel_id=? AND msg_id=?", (channel_id, msg_id))

        duplicate_rows = c.execute("SELECT hash, msg_ids FROM duplicates").fetchall()
        for duplicate_row in duplicate_rows:
            refs = [ref for ref in (duplicate_row["msg_ids"] or "").split(",") if ref]
            remaining = [ref for ref in refs if ref not in deleted_refs]
            if remaining:
                c.execute("UPDATE duplicates SET msg_ids=? WHERE hash=?",
                          (",".join(remaining), duplicate_row["hash"]))
            else:
                c.execute("DELETE FROM duplicates WHERE hash=?", (duplicate_row["hash"],))

    return len(deleted_ids)


# ── Links (plain URLs found in message text) ──────────────────────────

def upsert_link(channel_id: int, msg_id: int, url: str,
                 db_path: str = DB_FILE) -> None:
    """Record a discovered link. Leaves status/file_path alone on repeat
    scans so re-indexing doesn't reset an already-downloaded link."""
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT INTO links (channel_id, msg_id, url) VALUES (?,?,?)"
            " ON CONFLICT(channel_id, msg_id, url) DO NOTHING",
            (channel_id, msg_id, url),
        )


def get_links(status: Optional[str] = None, channel_id: Optional[int] = None,
              db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM links"
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    if channel_id is not None:
        clauses.append("channel_id=?")
        params.append(channel_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY discovered_at DESC"
    with get_conn(db_path) as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_link(link_id: int, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    with get_conn(db_path) as c:
        row = c.execute("SELECT * FROM links WHERE id=?", (link_id,)).fetchone()
    return dict(row) if row else None


def update_link_status(link_id: int, status: str, file_path: Optional[str] = None,
                        file_size: int = 0, db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "UPDATE links SET status=?, file_path=COALESCE(?, file_path),"
            " file_size=CASE WHEN ?>0 THEN ? ELSE file_size END,"
            " updated_at=datetime('now') WHERE id=?",
            (status, file_path, file_size, file_size, link_id),
        )


# ── Batch forward (legacy, moved from monolith) ──────────────────────

def batch_upsert(bid: str, src: str, dst: str, total: int, db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT OR IGNORE INTO batch_records"
            " (batch_id,src,dst,total_files,state) VALUES (?,?,?,?,'running')"
            " ON CONFLICT(batch_id) DO UPDATE SET"
            " total_files=excluded.total_files,updated_at=datetime('now')",
            (bid, src, dst, total),
        )


def batch_progress(bid: str, sent: int, failed: int, bnum: int, last_id: int,
                    state: str = "running", db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "UPDATE batch_records SET sent=?,failed=?,batch_num=?,"
            "last_msg_id=?,state=?,updated_at=datetime('now') WHERE batch_id=?",
            (sent, failed, bnum, last_id, state, bid),
        )


def batch_file_record(bid: str, msg_id: int, fname: str, size: int,
                       mtype: str, status: str, db_path: str = DB_FILE) -> None:
    with _lock, get_conn(db_path) as c:
        c.execute(
            "INSERT OR REPLACE INTO batch_files"
            " (batch_id,msg_id,filename,size,media_type,status,updated_at)"
            " VALUES (?,?,?,?,?,?,datetime('now'))",
            (bid, msg_id, fname, size, mtype, status),
        )


def batch_load_existing(src: str, dst: str, db_path: str = DB_FILE) -> Optional[dict]:
    with get_conn(db_path) as c:
        row = c.execute(
            "SELECT * FROM batch_records WHERE src=? AND dst=?"
            " AND state NOT IN ('done','failed')"
            " ORDER BY created_at DESC LIMIT 1",
            (src, dst),
        ).fetchone()
    return dict(row) if row else None


def batch_list_all(db_path: str = DB_FILE) -> List[dict]:
    with get_conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM batch_records ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [dict(r) for r in rows]


def batch_list_files(bid: str, db_path: str = DB_FILE) -> List[dict]:
    with get_conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM batch_files WHERE batch_id=? ORDER BY msg_id ASC",
            (bid,),
        ).fetchall()
    return [dict(r) for r in rows]


def is_processed(src: str, msg_id: int, db_path: str = DB_FILE) -> bool:
    with get_conn(db_path) as c:
        return bool(c.execute(
            "SELECT 1 FROM batch_files WHERE batch_id IN"
            " (SELECT batch_id FROM batch_records WHERE src=? AND state='done')"
            " AND msg_id=? AND status='done'",
            (src, msg_id),
        ).fetchone())
