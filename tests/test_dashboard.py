from datetime import datetime, timezone

from app.dashboard import get_dashboard_data, get_workbench_data
from app.identity import make_user_id
from app.models import CustomerEvent, Message, User, UserProfile
from app.strategy_agent import answer_strategy_question
from app.config import get_settings


def test_dashboard_aggregates_real_data(db) -> None:
    user_id = make_user_id("wecom", "bot-1", "alice")
    now = datetime.now(timezone.utc)
    db.add(
        User(
            id=user_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="alice",
            customer_stage="high_intent",
            source_channel="公众号",
            owner_name="张晓彤",
            first_seen_at=now,
            last_seen_at=now,
            last_message_at=now,
            last_event_at=now,
        )
    )
    db.add(UserProfile(user_id=user_id, summary="用户想报名", intent_score=82, stage="high_intent"))
    db.add(
        Message(
            hermes_message_id=20,
            hermes_session_id="sess-a",
            user_id=user_id,
            platform="wecom",
            bot_id="bot-1",
            external_user_id="alice",
            role="user",
            message_type="text",
            content="报名价格是多少？",
            created_at=now,
        )
    )
    db.add(CustomerEvent(user_id=user_id, event_type="message_received", title="收到客户消息", actor="customer", created_at=now))
    db.commit()

    dashboard = get_dashboard_data(db)
    workbench = get_workbench_data(db)

    assert dashboard["total_users"] == 1
    assert dashboard["source_counts"][0]["source"] == "公众号"
    assert dashboard["top_questions"][0]["question"] == "报名价格是多少？"
    assert workbench["users"][0].id == user_id


def test_strategy_agent_fallback_returns_summary(db) -> None:
    answer = answer_strategy_question(db, get_settings(), "最近经营情况如何？")

    assert "基于当前CRM数据" in answer

