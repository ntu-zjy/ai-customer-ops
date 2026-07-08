from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .constants import CUSTOMER_STAGE_LABELS, CUSTOMER_STAGES
from .models import CustomerEvent, Message, User, UserProfile, UserTag
from .routing import get_action_suggestion


@dataclass(frozen=True)
class Kpi:
    label: str
    value: str
    hint: str


def get_workbench_data(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    users = list(
        db.scalars(
            select(User)
            .options(selectinload(User.profile), selectinload(User.tags))
            .order_by(User.last_event_at.desc().nullslast(), User.last_message_at.desc().nullslast())
            .limit(80)
        )
    )
    selected_user = users[0] if users else None

    today_new = db.scalar(select(func.count()).select_from(User).where(User.first_seen_at >= today_start)) or 0
    high_intent = count_high_intent(db)
    pending = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.customer_stage.in_(["high_intent", "follow_up", "pending_review"]))
    ) or 0
    ai_resolution = compute_ai_resolution_rate(db, week_start)

    suggestions = []
    for user in users[:4]:
        suggestion = get_action_suggestion(db, user)
        suggestions.append({"user": user, "suggestion": suggestion})

    reminders = [
        {"label": "高意向客户待跟进", "count": high_intent, "tone": "danger"},
        {"label": "审核/人工处理", "count": pending, "tone": "warning"},
        {"label": "今日新增客户", "count": today_new, "tone": "info"},
    ]

    questions = get_common_questions(db, since=week_start, limit=5)

    return {
        "kpis": [
            Kpi("今日新增客户", str(today_new), "来自企微私聊同步"),
            Kpi("高意向客户", str(high_intent), "建议优先人工承接"),
            Kpi("待跟进", str(pending), "高意向、审核和人工阶段"),
            Kpi("AI解决率", f"{ai_resolution:.1f}%", "近7天 AI 回复覆盖率"),
        ],
        "users": users,
        "selected_user": selected_user,
        "selected_suggestion": get_action_suggestion(db, selected_user) if selected_user else None,
        "suggestions": suggestions,
        "reminders": reminders,
        "questions": questions,
    }


def get_dashboard_data(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    today_new = db.scalar(select(func.count()).select_from(User).where(User.first_seen_at >= today_start)) or 0
    high_intent = count_high_intent(db)
    converted = db.scalar(select(func.count()).select_from(User).where(User.customer_stage == "converted")) or 0
    ai_resolution = compute_ai_resolution_rate(db, week_start)

    stage_counts = get_stage_counts(db)
    source_counts = get_source_counts(db)
    top_questions = get_common_questions(db, since=week_start, limit=5)
    employee_rows = get_employee_rows(db)
    event_counts = get_event_counts(db, since=week_start)

    return {
        "kpis": [
            Kpi("今日新增客户", str(today_new), "较适合看投放当天效果"),
            Kpi("高意向客户", str(high_intent), "建议当天人工跟进"),
            Kpi("已成交客户", str(converted), "当前 CRM 阶段统计"),
            Kpi("AI解决率", f"{ai_resolution:.1f}%", "近7天 AI 回复覆盖率"),
        ],
        "total_users": total_users,
        "stage_counts": stage_counts,
        "source_counts": source_counts,
        "top_questions": top_questions,
        "employee_rows": employee_rows,
        "event_counts": event_counts,
        "funnel": build_funnel(stage_counts, total_users),
        "advice": build_business_advice(today_new, high_intent, ai_resolution, top_questions),
    }


def count_high_intent(db: Session) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where((User.customer_stage == "high_intent") | (UserProfile.intent_score >= 70))
        )
        or 0
    )


def compute_ai_resolution_rate(db: Session, since: datetime) -> float:
    user_messages = db.scalar(
        select(func.count()).select_from(Message).where(Message.role == "user").where(Message.created_at >= since)
    ) or 0
    ai_replies = db.scalar(
        select(func.count()).select_from(Message).where(Message.role == "assistant").where(Message.created_at >= since)
    ) or 0
    if user_messages == 0:
        return 0.0
    return min(100.0, ai_replies / user_messages * 100)


def get_stage_counts(db: Session) -> list[dict]:
    rows = dict(db.execute(select(User.customer_stage, func.count()).group_by(User.customer_stage)).all())
    return [
        {
            "stage": stage,
            "label": CUSTOMER_STAGE_LABELS.get(stage, stage),
            "count": int(rows.get(stage, 0)),
        }
        for stage in CUSTOMER_STAGES
        if rows.get(stage, 0)
    ]


def get_source_counts(db: Session) -> list[dict]:
    rows = db.execute(
        select(func.coalesce(User.source_channel, User.platform), func.count())
        .group_by(func.coalesce(User.source_channel, User.platform))
        .order_by(func.count().desc())
        .limit(6)
    ).all()
    return [{"source": source or "未知", "count": count} for source, count in rows]


def get_event_counts(db: Session, since: datetime) -> dict[str, int]:
    rows = db.execute(
        select(CustomerEvent.event_type, func.count())
        .where(CustomerEvent.created_at >= since)
        .group_by(CustomerEvent.event_type)
    ).all()
    return {event_type: int(count) for event_type, count in rows}


def get_employee_rows(db: Session) -> list[dict]:
    rows = db.execute(
        select(func.coalesce(User.owner_name, "未分配"), func.count(), func.max(User.last_event_at))
        .group_by(func.coalesce(User.owner_name, "未分配"))
        .order_by(func.count().desc())
        .limit(6)
    ).all()
    return [{"owner": owner, "customers": count, "last_event_at": last_event_at} for owner, count, last_event_at in rows]


def get_common_questions(db: Session, since: datetime, limit: int) -> list[dict]:
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.role == "user")
            .where(Message.created_at >= since)
            .where(Message.content.is_not(None))
            .order_by(Message.created_at.desc())
            .limit(300)
        )
    )
    phrases: Counter[str] = Counter()
    for message in messages:
        text = (message.content or "").strip()
        if not text:
            continue
        if any(marker in text for marker in ("?", "？", "吗", "怎么", "多少", "报名", "价格", "时间", "群")):
            phrases[text[:32]] += 1
    return [{"question": question, "count": count} for question, count in phrases.most_common(limit)]


def build_funnel(stage_counts: list[dict], total_users: int) -> list[dict]:
    stage_map = {item["stage"]: item["count"] for item in stage_counts}
    order = ["consulted", "registered", "approved", "paid", "joined_group", "converted"]
    return [
        {
            "stage": stage,
            "label": CUSTOMER_STAGE_LABELS.get(stage, stage),
            "count": int(stage_map.get(stage, 0)),
            "rate": round((stage_map.get(stage, 0) / total_users * 100), 1) if total_users else 0.0,
        }
        for stage in order
    ]


def build_business_advice(today_new: int, high_intent: int, ai_resolution: float, questions: list[dict]) -> list[str]:
    advice = []
    if high_intent:
        advice.append(f"优先跟进 {high_intent} 位高意向客户，避免咨询热度衰减。")
    if today_new == 0:
        advice.append("今日暂无新增客户，建议检查渠道投放或活动入口。")
    if ai_resolution < 60:
        advice.append("近7天 AI 回复覆盖率偏低，建议补充知识文档和常见问题。")
    if questions:
        advice.append(f"客户高频问题集中在“{questions[0]['question']}”，可优先优化话术。")
    if not advice:
        advice.append("当前客户承接稳定，建议继续观察渠道质量和员工响应速度。")
    return advice[:4]

