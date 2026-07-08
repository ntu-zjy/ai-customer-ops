from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import Settings
from .hermes_client import HermesClient
from .constants import AI_RECOMMENDABLE_CUSTOMER_STAGES, MANUAL_PROTECTED_STAGES, PROFILE_STAGES
from .events import record_event
from .models import AnalysisRun, Message, User, UserProfile, UserTag, utc_now
from .settings_repo import get_knowledge_urls

ALLOWED_STAGES = PROFILE_STAGES
FIXED_TAGS = ["高意向", "价格顾虑", "时间冲突", "报名咨询", "活动规则咨询", "待人工跟进"]


def analyze_user(db: Session, settings: Settings, user_id: str) -> UserProfile:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"User not found: {user_id}")

    messages = list(
        db.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .where(Message.role.in_(["user", "assistant"]))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    )
    if not messages:
        result = empty_result()
    else:
        result = run_llm_analysis(db, settings, user, messages)

    profile = upsert_profile(db, user, messages, result)
    maybe_apply_ai_customer_stage(db, user, result["stage"])
    replace_tags(db, user.id, result.get("tags", []))
    db.add(AnalysisRun(user_id=user.id, status="success", raw_output=result))
    record_event(
        db,
        user,
        "analysis_completed",
        "AI画像已更新",
        detail=result["summary"][:240],
        actor="ai",
        metadata={"stage": result["stage"], "intent_score": result["intent_score"], "tags": result.get("tags", [])},
    )
    return profile


def analyze_due_users(db: Session, settings: Settings, limit: int | None = None) -> int:
    latest_message_id = (
        select(func.max(Message.hermes_message_id))
        .where(Message.user_id == User.id)
        .where(Message.role == "user")
        .correlate(User)
        .scalar_subquery()
    )
    profile_last_id = (
        select(UserProfile.last_analyzed_message_id).where(UserProfile.user_id == User.id).correlate(User).scalar_subquery()
    )
    stmt = (
        select(User.id)
        .where(latest_message_id.is_not(None))
        .where((profile_last_id.is_(None)) | (latest_message_id > profile_last_id))
        .order_by(User.last_message_at.desc())
        .limit(limit or settings.analyze_due_limit)
    )
    user_ids = list(db.scalars(stmt))
    analyzed = 0
    for user_id in user_ids:
        try:
            analyze_user(db, settings, user_id)
            analyzed += 1
        except Exception as exc:  # keep the batch moving
            db.add(AnalysisRun(user_id=user_id, status="failed", error=str(exc)))
    return analyzed


def run_llm_analysis(db: Session, settings: Settings, user: User, messages: list[Message]) -> dict[str, Any]:
    client = HermesClient(settings)
    if not client.is_configured():
        return heuristic_analysis(messages)

    knowledge_urls = get_knowledge_urls(db)
    system_prompt = (
        "你是活动 CRM 用户画像分析器。只分析当前提供的单个用户消息，不读取或引用其他用户记忆。"
        "不要写入 Hermes memory，不要使用全局用户画像。输出必须是一个 JSON 对象。"
    )
    user_prompt = json.dumps(
        {
            "task": "根据该用户自己的聊天记录生成 CRM 分析。",
            "constraints": {
                "allowed_stages": sorted(ALLOWED_STAGES),
                "allowed_tags": FIXED_TAGS,
                "score_range": "0-100",
                "knowledge_urls_are_shared_reference_only": knowledge_urls,
            },
            "required_schema": {
                "summary": "string",
                "intent_score": "integer",
                "stage": "new|interested|high_intent|registered|follow_up|inactive",
                "tags": ["固定标签集合中的若干项"],
                "follow_up_suggestion": "string",
                "evidence_message_ids": ["integer"],
            },
            "user": {
                "id": user.id,
                "external_user_id": user.external_user_id,
            },
            "messages": [
                {
                    "id": message.hermes_message_id,
                    "role": message.role,
                    "type": message.message_type,
                    "content": message.content or "",
                    "created_at": message.created_at.isoformat(),
                }
                for message in messages[-80:]
            ],
        },
        ensure_ascii=False,
    )
    try:
        return normalize_result(client.chat_json(system_prompt, user_prompt), messages)
    except Exception:
        return heuristic_analysis(messages)


def heuristic_analysis(messages: list[Message]) -> dict[str, Any]:
    user_messages = [m for m in messages if m.role == "user"]
    text = "\n".join((m.content or "") for m in user_messages).lower()
    tags: list[str] = []
    score = 20 if user_messages else 0

    if any(word in text for word in ("报名", "参加", "名额", "链接", "预约", "怎么去", "地址")):
        tags.append("报名咨询")
        score += 25
    if any(word in text for word in ("价格", "多少钱", "费用", "优惠", "贵")):
        tags.append("价格顾虑")
        score += 10
    if any(word in text for word in ("时间", "几点", "日期", "冲突", "来不及")):
        tags.append("时间冲突")
        score += 10
    if any(word in text for word in ("规则", "流程", "需要", "准备", "要求")):
        tags.append("活动规则咨询")
        score += 10
    if any(word in text for word in ("人工", "联系我", "电话", "微信", "回电")):
        tags.append("待人工跟进")
        score += 15
    if any(word in text for word in ("确定", "马上", "已报名", "付款", "提交了")):
        tags.append("高意向")
        score += 25

    tags = [tag for tag in FIXED_TAGS if tag in set(tags)]
    score = min(score, 100)
    stage = "new"
    if "已报名" in text or "付款" in text:
        stage = "registered"
    elif "高意向" in tags or score >= 70:
        stage = "high_intent"
    elif "待人工跟进" in tags:
        stage = "follow_up"
    elif user_messages:
        stage = "interested"

    evidence = [m.hermes_message_id for m in user_messages[-5:]]
    last_text = (user_messages[-1].content or "").strip() if user_messages else ""
    summary = f"用户最近咨询：{last_text[:120]}" if last_text else "暂无可分析的用户消息。"
    suggestion = "优先人工跟进，确认报名意向和关键阻碍。" if score >= 60 else "保持自动回复，等待更多明确意向信号。"
    return normalize_result(
        {
            "summary": summary,
            "intent_score": score,
            "stage": stage,
            "tags": tags,
            "follow_up_suggestion": suggestion,
            "evidence_message_ids": evidence,
        },
        messages,
    )


def normalize_result(result: dict[str, Any], messages: list[Message]) -> dict[str, Any]:
    user_message_ids = {m.hermes_message_id for m in messages if m.role == "user"}
    stage = str(result.get("stage") or "new")
    if stage not in ALLOWED_STAGES:
        stage = "new"
    tags = [tag for tag in result.get("tags", []) if tag in FIXED_TAGS]
    evidence = []
    for raw_id in result.get("evidence_message_ids", []):
        try:
            message_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if message_id in user_message_ids:
            evidence.append(message_id)
    if not evidence:
        evidence = [m.hermes_message_id for m in messages if m.role == "user"][-5:]
    return {
        "summary": str(result.get("summary") or "").strip()[:4000],
        "intent_score": max(0, min(100, int(result.get("intent_score") or 0))),
        "stage": stage,
        "tags": tags,
        "follow_up_suggestion": str(result.get("follow_up_suggestion") or "").strip()[:2000],
        "evidence_message_ids": evidence,
    }


def empty_result() -> dict[str, Any]:
    return {
        "summary": "暂无可分析的用户消息。",
        "intent_score": 0,
        "stage": "new",
        "tags": [],
        "follow_up_suggestion": "等待用户首次咨询。",
        "evidence_message_ids": [],
    }


def upsert_profile(db: Session, user: User, messages: list[Message], result: dict[str, Any]) -> UserProfile:
    latest_user_message_id = max((m.hermes_message_id for m in messages if m.role == "user"), default=None)
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.summary = result["summary"]
    profile.intent_score = result["intent_score"]
    profile.stage = result["stage"]
    profile.follow_up_suggestion = result["follow_up_suggestion"]
    profile.evidence_message_ids = result["evidence_message_ids"]
    profile.last_analyzed_message_id = latest_user_message_id
    profile.updated_at = utc_now()
    return profile


def replace_tags(db: Session, user_id: str, tags: list[str]) -> None:
    db.execute(delete(UserTag).where(UserTag.user_id == user_id).where(UserTag.source == "analysis"))
    now = datetime.now(timezone.utc)
    for tag in tags:
        db.add(UserTag(user_id=user_id, tag=tag, confidence=100, source="analysis", updated_at=now))


def maybe_apply_ai_customer_stage(db: Session, user: User, profile_stage: str) -> None:
    current = user.customer_stage or "new"
    if current in MANUAL_PROTECTED_STAGES:
        return
    if current not in {"", "new", "consulted", "interested", "high_intent", "follow_up"}:
        return
    if profile_stage not in AI_RECOMMENDABLE_CUSTOMER_STAGES:
        return
    if current == profile_stage:
        return
    old_stage = current or "new"
    user.customer_stage = profile_stage
    record_event(
        db,
        user,
        "stage_changed",
        "AI建议客户阶段",
        detail=f"{old_stage} -> {profile_stage}",
        actor="ai",
        metadata={"old_stage": old_stage, "new_stage": profile_stage, "source": "profile_analysis"},
    )
