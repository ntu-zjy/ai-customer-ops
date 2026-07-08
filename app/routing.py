from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .constants import DEFAULT_ROUTING_RULES
from .models import RoutingRule, User, utc_now


def ensure_default_routing_rules(db: Session) -> int:
    existing_names = set(db.scalars(select(RoutingRule.name)))
    created = 0
    for item in DEFAULT_ROUTING_RULES:
        if item["name"] in existing_names:
            continue
        db.add(
            RoutingRule(
                name=item["name"],
                from_stage=item["from_stage"],
                action=item["action"],
                target=item.get("target", ""),
                message=item.get("message", ""),
                priority=item.get("priority", 100),
                enabled=True,
                conditions={},
            )
        )
        created += 1
    return created


def get_routing_rules(db: Session) -> list[RoutingRule]:
    ensure_default_routing_rules(db)
    return list(db.scalars(select(RoutingRule).order_by(RoutingRule.priority.asc(), RoutingRule.id.asc())))


def get_rule_for_stage(db: Session, stage: str) -> RoutingRule | None:
    ensure_default_routing_rules(db)
    return db.scalar(
        select(RoutingRule)
        .where(RoutingRule.from_stage == stage)
        .where(RoutingRule.enabled.is_(True))
        .order_by(RoutingRule.priority.asc(), RoutingRule.id.asc())
    )


def get_action_suggestion(db: Session, user: User) -> dict[str, str]:
    rule = get_rule_for_stage(db, user.customer_stage or "new")
    if rule is None:
        return {
            "action": "answer",
            "target": "AI客服继续接待",
            "message": "暂无匹配规则，继续记录客户问题并等待人工判断。",
            "rule_name": "默认接待",
        }
    return {
        "action": rule.action,
        "target": rule.target,
        "message": rule.message,
        "rule_name": rule.name,
    }


def update_routing_rule(
    db: Session,
    rule: RoutingRule,
    *,
    enabled: bool,
    target: str,
    message: str,
    priority: int,
) -> RoutingRule:
    rule.enabled = enabled
    rule.target = target.strip()
    rule.message = message.strip()
    rule.priority = max(1, priority)
    rule.updated_at = utc_now()
    return rule

