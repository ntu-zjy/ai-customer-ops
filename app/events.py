from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import CustomerEvent, Message, User, utc_now


def record_event(
    db: Session,
    user: User,
    event_type: str,
    title: str,
    detail: str | None = None,
    actor: str = "system",
    source: str | None = None,
    related_message: Message | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> CustomerEvent:
    event_time = created_at or utc_now()
    event = CustomerEvent(
        user_id=user.id,
        event_type=event_type,
        title=title,
        detail=detail,
        actor=actor,
        source=source,
        related_message_id=related_message.id if related_message is not None else None,
        event_metadata=metadata or {},
        created_at=event_time,
    )
    db.add(event)
    user.last_event_at = event_time
    return event


def change_customer_stage(
    db: Session,
    user: User,
    new_stage: str,
    actor: str = "employee",
    detail: str | None = None,
) -> CustomerEvent | None:
    old_stage = user.customer_stage or "new"
    if old_stage == new_stage:
        return None
    user.customer_stage = new_stage
    return record_event(
        db,
        user,
        "stage_changed",
        "客户阶段更新",
        detail or f"{old_stage} -> {new_stage}",
        actor=actor,
        metadata={"old_stage": old_stage, "new_stage": new_stage},
    )

