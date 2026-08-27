"""文件库 SQLite 元数据层。

表结构见 docs/07-文件存储.md §3。仅 images 表（任务记录留作后续）。
连接线程安全：check_same_thread=False，写入加全局锁。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import get_storage

_write_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id            TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    format        TEXT NOT NULL,
    width_px      INTEGER,
    height_px     INTEGER,
    dpi           INTEGER,
    mode          TEXT,
    size_bytes    INTEGER,
    source        TEXT NOT NULL,
    ref_type      TEXT,
    ref_size      TEXT,
    task_id       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_created_at ON images(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_images_source ON images(source);
CREATE INDEX IF NOT EXISTS idx_images_ref ON images(ref_type, ref_size);
"""


def get_conn() -> sqlite3.Connection:
    """返回库 DB 连接（行工厂 sqlite3.Row）。首次自动建表。"""
    db_path = get_storage().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    """ISO 时间戳（不含微秒精度，避免跨进程不一致）。"""
    return datetime.now().isoformat(timespec="seconds")


def insert_image(row: dict[str, Any]) -> dict[str, Any]:
    """插入一条 image 记录，返回完整行（dict）。"""
    now = _now()
    row = {**row, "created_at": row.get("created_at", now), "updated_at": now}
    cols = ",".join(row.keys())
    placeholders = ",".join("?" * len(row))
    with _write_lock:
        with get_conn() as conn:
            conn.execute(f"INSERT INTO images ({cols}) VALUES ({placeholders})", list(row.values()))
    return row


def get_image(image_id: str) -> Optional[dict[str, Any]]:
    """按 id 取单条记录。"""
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    return dict(r) if r else None


def list_images(
    *,
    source: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_size: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """按条件分页查询，created_at 倒序。"""
    clauses, params = _build_where(source, ref_type, ref_size, q)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM images{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def count_images(
    *,
    source: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_size: Optional[str] = None,
    q: Optional[str] = None,
) -> int:
    """按条件统计总条数（与 list_images 同 where，用于分页）。"""
    clauses, params = _build_where(source, ref_type, ref_size, q)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM images{where}", params).fetchone()
    return int(row["c"]) if row else 0


def _build_where(source, ref_type, ref_size, q) -> tuple[list[str], list[Any]]:
    """构造查询条件子句与参数（list/count 共用）。"""
    clauses: list[str] = []
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if ref_type:
        clauses.append("ref_type = ?")
        params.append(ref_type)
    if ref_size:
        clauses.append("ref_size = ?")
        params.append(ref_size)
    if q:
        clauses.append("original_name LIKE ?")
        params.append(f"%{q}%")
    return clauses, params


def delete_image(image_id: str) -> bool:
    """删除一条记录，返回是否删除了行。"""
    with _write_lock:
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
            return cur.rowcount > 0
