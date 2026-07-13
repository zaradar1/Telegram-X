import sqlite3
import threading

from settings import DB_PATH

_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
    session_string TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    name TEXT,
    is_group INTEGER DEFAULT 0,
    is_channel INTEGER DEFAULT 0,
    PRIMARY KEY (account_id, id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sender TEXT,
    text TEXT,
    has_media INTEGER DEFAULT 0,
    media_type TEXT,
    file_name TEXT,
    file_size INTEGER,
    date TEXT,
    UNIQUE(account_id, chat_id, message_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, file_name, content='messages', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, file_name) VALUES (new.id, new.text, new.file_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name) VALUES('delete', old.id, old.text, old.file_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, file_name) VALUES('delete', old.id, old.text, old.file_name);
    INSERT INTO messages_fts(rowid, text, file_name) VALUES (new.id, new.text, new.file_name);
END;

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    file_path TEXT,
    file_hash TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_downloads_hash ON downloads(file_hash);

CREATE TABLE IF NOT EXISTS duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT NOT NULL,
    download_id INTEGER NOT NULL,
    FOREIGN KEY(download_id) REFERENCES downloads(id)
);

CREATE TABLE IF NOT EXISTS batch_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,
    source_chat_id INTEGER,
    target_chat_id INTEGER,
    status TEXT DEFAULT 'pending',
    total INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript(_SCHEMA)
    conn.commit()


def is_downloaded(account_id: int, chat_id: int, message_id: int) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM downloads WHERE account_id=? AND chat_id=? AND message_id=? AND status='done'",
        (account_id, chat_id, message_id),
    ).fetchone()
    return row is not None


def record_download(account_id: int, chat_id: int, message_id: int, file_path: str, file_hash: str) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO downloads (account_id, chat_id, message_id, file_path, file_hash, status) "
        "VALUES (?, ?, ?, ?, ?, 'done') "
        "ON CONFLICT(account_id, chat_id, message_id) DO UPDATE SET "
        "file_path=excluded.file_path, file_hash=excluded.file_hash, status='done'",
        (account_id, chat_id, message_id, file_path, file_hash),
    )
    download_id = conn.execute(
        "SELECT id FROM downloads WHERE account_id=? AND chat_id=? AND message_id=?",
        (account_id, chat_id, message_id),
    ).fetchone()["id"]
    dup = conn.execute(
        "SELECT id FROM downloads WHERE file_hash=? AND id != ? LIMIT 1",
        (file_hash, download_id),
    ).fetchone()
    if dup:
        conn.execute(
            "INSERT INTO duplicates (file_hash, download_id) VALUES (?, ?)",
            (file_hash, download_id),
        )
    conn.commit()


def list_duplicates() -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT d.file_hash AS file_hash, GROUP_CONCAT(dl.file_path, '||') AS paths "
        "FROM duplicates d JOIN downloads dl ON dl.file_hash = d.file_hash "
        "GROUP BY d.file_hash"
    ).fetchall()
    return [dict(r) for r in rows]


def search_messages(query: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT m.* FROM messages_fts f JOIN messages m ON m.id = f.rowid "
        "WHERE messages_fts MATCH ? LIMIT ?",
        (query, limit),
    ).fetchall()
    return [dict(r) for r in rows]
