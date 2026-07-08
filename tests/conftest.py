import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.database import create_tables, get_session_factory, reset_for_tests


@pytest.fixture()
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "crm.db"
    hermes_db = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HERMES_STATE_DB", str(hermes_db))
    monkeypatch.setenv("HERMES_BOT_ID", "bot-1")
    monkeypatch.setenv("HERMES_SOURCE_FILTER", "wecom")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    reset_for_tests()
    create_tables()
    yield hermes_db
    reset_for_tests()


@pytest.fixture()
def db(app_env: Path) -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_hermes_state(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT,
                title TEXT,
                started_at REAL NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_name TEXT,
                tool_calls TEXT,
                timestamp REAL NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO sessions (id, source, user_id, title, started_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("sess-a", "wecom", "alice", "Alice DM", 1000.0),
                ("sess-b", "wecom", "bob", "Bob DM", 1000.0),
                ("sess-c", "telegram", "charlie", "Other platform", 1000.0),
            ],
        )
        conn.executemany(
            "INSERT INTO messages (id, session_id, role, content, tool_name, tool_calls, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "sess-a", "user", "我想报名活动", None, None, 1001.0),
                (2, "sess-a", "assistant", "可以，我帮你看一下。", None, None, 1002.0),
                (3, "sess-b", "user", "价格多少？", None, None, 1003.0),
                (4, "sess-c", "user", "不应该同步", None, None, 1004.0),
            ],
        )
        conn.commit()

