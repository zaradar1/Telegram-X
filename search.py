"""Search engine over the SQLite index: full-text (FTS5) + advanced filters."""

from typing import Any, Dict, List, Optional

import database


def _fts_escape(query: str) -> str:
    """Quote the query so FTS5 treats it as a phrase rather than parsing
    operators (AND/OR/NOT/*) out of arbitrary user input."""
    return '"' + query.replace('"', '""') + '"'


def search_text(query: str, db_path: str = database.DB_FILE) -> List[Dict[str, Any]]:
    """Full-text search across message text, caption, and file name."""
    if not query.strip():
        return []
    with database.get_conn(db_path) as c:
        rows = c.execute(
            """
            SELECT m.* FROM messages_fts f
            JOIN messages m ON m.channel_id = f.channel_id AND m.id = f.msg_id
            WHERE messages_fts MATCH ?
            ORDER BY m.date DESC
            """,
            (_fts_escape(query),),
        ).fetchall()
    return [dict(r) for r in rows]


def search_filename(query: str, db_path: str = database.DB_FILE) -> List[Dict[str, Any]]:
    with database.get_conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM messages WHERE file_name LIKE ? ORDER BY date DESC",
            (f"%{query}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def search_advanced(
    filename: Optional[str] = None,
    caption: Optional[str] = None,
    sender_id: Optional[int] = None,
    extension: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    media_type: Optional[str] = None,
    channel_id: Optional[int] = None,
    db_path: str = database.DB_FILE,
) -> List[Dict[str, Any]]:
    """Build a dynamic SQL query over `messages` from whichever filters are set."""
    clauses: List[str] = []
    params: List[Any] = []

    if filename:
        clauses.append("file_name LIKE ?")
        params.append(f"%{filename}%")
    if caption:
        clauses.append("caption LIKE ?")
        params.append(f"%{caption}%")
    if sender_id is not None:
        clauses.append("sender_id = ?")
        params.append(sender_id)
    if extension:
        clauses.append("file_name LIKE ?")
        params.append(f"%.{extension.lstrip('.')}")
    if min_size is not None:
        clauses.append("file_size >= ?")
        params.append(min_size)
    if max_size is not None:
        clauses.append("file_size <= ?")
        params.append(max_size)
    if from_date:
        clauses.append("date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("date <= ?")
        params.append(to_date)
    if media_type:
        clauses.append("media_type = ?")
        params.append(media_type)
    if channel_id is not None:
        clauses.append("channel_id = ?")
        params.append(channel_id)

    sql = "SELECT * FROM messages"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date DESC"

    with database.get_conn(db_path) as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
