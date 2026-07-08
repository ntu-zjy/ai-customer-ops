from datetime import datetime, timezone

from app.analysis import analyze_user
from app.config import get_settings
from app.identity import make_user_id
from sqlalchemy import select

from app.models import CustomerEvent, Message, User


def test_heuristic_analysis_uses_only_current_user_messages(db) -> None:
    alice_id = make_user_id("wecom", "bot-1", "alice")
    bob_id = make_user_id("wecom", "bot-1", "bob")
    now = datetime.now(timezone.utc)
    db.add(User(id=alice_id, platform="wecom", bot_id="bot-1", external_user_id="alice", last_message_at=now))
    db.add(User(id=bob_id, platform="wecom", bot_id="bot-1", external_user_id="bob", last_message_at=now))
    db.add(
        Message(
            hermes_message_id=1,
            hermes_session_id="sess-a",
            user_id=alice_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="alice",
            role="user",
            message_type="text",
            content="我想报名，价格多少钱？",
            created_at=now,
        )
    )
    db.add(
        Message(
            hermes_message_id=2,
            hermes_session_id="sess-b",
            user_id=bob_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="bob",
            role="user",
            message_type="text",
            content="我已经付款了",
            created_at=now,
        )
    )
    db.commit()

    profile = analyze_user(db, get_settings(), alice_id)
    db.commit()

    assert profile.user_id == alice_id
    assert profile.stage in {"interested", "high_intent"}
    assert "报名咨询" in [tag.tag for tag in db.get(User, alice_id).tags]
    assert "付款" not in profile.summary
    assert db.get(User, alice_id).customer_stage in {"interested", "high_intent"}
    assert db.scalar(select(CustomerEvent).where(CustomerEvent.user_id == alice_id).where(CustomerEvent.event_type == "analysis_completed"))


def test_analysis_does_not_overwrite_business_stage(db) -> None:
    user_id = make_user_id("wecom", "bot-1", "alice")
    now = datetime.now(timezone.utc)
    db.add(
        User(
            id=user_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="alice",
            customer_stage="paid",
            last_message_at=now,
        )
    )
    db.add(
        Message(
            hermes_message_id=10,
            hermes_session_id="sess-a",
            user_id=user_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="alice",
            role="user",
            message_type="text",
            content="我马上报名，请联系人工",
            created_at=now,
        )
    )
    db.commit()

    analyze_user(db, get_settings(), user_id)
    db.commit()

    assert db.get(User, user_id).customer_stage == "paid"
