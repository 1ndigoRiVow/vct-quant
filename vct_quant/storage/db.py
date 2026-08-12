"""vct_quant.storage.db — SQLite 连接与迁移。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .. import config

SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or str(config.DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        if own:
            conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """轻量迁移：旧库补充新增列，保证 CREATE TABLE IF NOT EXISTS 覆盖不到的场景。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(player_stats)").fetchall()}
    if "rounds" not in cols:
        conn.execute("ALTER TABLE player_stats ADD COLUMN rounds INTEGER DEFAULT 0")


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
