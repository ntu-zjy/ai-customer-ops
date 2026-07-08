from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .events import record_event
from .identity import make_user_id
from .models import Message, User, utc_now
from .settings_repo import get_sync_cursor, set_sync_cursor


@dataclass(frozen=True)
class HermesMessageRow:
    hermes_message_id: int
    hermes_session_id: str
    role: str
    content: str | None
    timestamp: float
    tool_name: str | None
    tool_calls: str | None
    source: str
    session_user_id: str | None
    session_title: str | None


def fetch_hermes_rows(db_path: Path, after_message_id: int, source_filter: str, limit: int) -> list[HermesMessageRow]:
    if not db_path.exists():
        raise FileNotFoundError(f"Hermes state database not found: {db_path}")

    uri = f"file:{db_path}?mode=ro"
    params: list[object] = [after_message_id]
    source_clause = ""
    if source_filter:
        source_clause = "AND lower(s.source) LIKE lower(?)"
        params.append(f"%{source_filter}%")
    params.append(limit)

    query = f"""
        SELECT
            m.id,
            m.session_id,
            m.role,
            m.content,
            m.timestamp,
            m.tool_name,
            m.tool_calls,
            s.source,
            s.user_id,
            s.title
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        WHERE m.id > ?
          {source_clause}
        ORDER BY m.id ASC
        LIMIT ?
    """

    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [
        HermesMessageRow(
            hermes_message_id=int(row["id"]),
            hermes_session_id=str(row["session_id"]),
            role=str(row["role"]),
            content=row["content"],
            timestamp=float(row["timestamp"] or 0),
            tool_name=row["tool_name"],
            tool_calls=row["tool_calls"],
            source=str(row["source"] or ""),
            session_user_id=row["user_id"],
            session_title=row["title"],
        )
        for row in rows
    ]


def sync_hermes_messages(db: Session, settings: Settings) -> int:
    cursor = get_sync_cursor(db)
    rows = fetch_hermes_rows(
        settings.resolved_hermes_state_db,
        after_message_id=cursor,
        source_filter=settings.hermes_source_filter,
        limit=settings.sync_batch_size,
    )
    if not rows:
        return 0

    inserted = 0
    max_seen = cursor
    users_by_id: dict[str, User] = {}
    for row in rows:
        max_seen = max(max_seen, row.hermes_message_id)
        exists = db.scalar(select(Message.id).where(Message.hermes_message_id == row.hermes_message_id))
        if exists is not None:
            continue

        external_user_id = derive_external_user_id(row)
        user_id = make_user_id(settings.hermes_platform, settings.hermes_bot_id, external_user_id)
        created_at = datetime.fromtimestamp(row.timestamp, tz=timezone.utc)
        user = users_by_id.get(user_id)
        if user is None:
            user = db.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                platform=settings.hermes_platform,
                bot_id=settings.hermes_bot_id,
                external_user_id=external_user_id,
                display_name=external_user_id,
                customer_stage="new",
                source_channel=row.source or settings.hermes_platform,
                first_seen_at=created_at,
                last_seen_at=created_at,
            )
            db.add(user)
        users_by_id[user_id] = user

        user.last_seen_at = max_datetime(user.last_seen_at, created_at)
        user.last_message_at = max_datetime(user.last_message_at, created_at)
        user.message_count = (user.message_count or 0) + 1
        if not user.source_channel:
            user.source_channel = row.source or settings.hermes_platform

        message = Message(
            hermes_message_id=row.hermes_message_id,
            hermes_session_id=row.hermes_session_id,
            user_id=user.id,
            platform=settings.hermes_platform,
            bot_id=settings.hermes_bot_id,
            external_user_id=external_user_id,
            role=row.role,
            message_type=infer_message_type(row),
            content=row.content,
            raw_payload={
                "source": row.source,
                "session_title": row.session_title,
                "tool_name": row.tool_name,
                "tool_calls": parse_json(row.tool_calls),
            },
            created_at=created_at,
        )
        db.add(message)
        db.flush()
        record_message_event(db, user, message, row)
        inserted += 1

    set_sync_cursor(db, max_seen)
    return inserted


def record_message_event(db: Session, user: User, message: Message, row: HermesMessageRow) -> None:
    if message.role == "user":
        if user.customer_stage == "new":
            user.customer_stage = "consulted"
        record_event(
            db,
            user,
            "message_received",
            "收到客户消息",
            detail=(message.content or "")[:240],
            actor="customer",
            source=row.source,
            related_message=message,
            metadata={"hermes_message_id": row.hermes_message_id, "message_type": message.message_type},
            created_at=message.created_at,
        )
    elif message.role == "assistant":
        record_event(
            db,
            user,
            "ai_replied",
            "AI已回复",
            detail=(message.content or "")[:240],
            actor="ai",
            source=row.source,
            related_message=message,
            metadata={"hermes_message_id": row.hermes_message_id, "message_type": message.message_type},
            created_at=message.created_at,
        )


def derive_external_user_id(row: HermesMessageRow) -> str:
    if row.session_user_id:
        return str(row.session_user_id)
    session = row.hermes_session_id
    for separator in (":", "/", "|"):
        if separator in session:
            return session.split(separator)[-1]
    return session


def infer_message_type(row: HermesMessageRow) -> str:
    text = row.content or ""
    lowered = text.lower()
    if any(marker in lowered for marker in ("image", "图片", "voice", "语音", "file", "附件", "video", "视频")):
        return "media"
    if row.tool_name or row.tool_calls:
        return "tool"
    return "text"


def parse_json(raw: str | None) -> object | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def max_datetime(left: datetime | None, right: datetime) -> datetime:
    if left is None:
        return right
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    return max(left, right)
