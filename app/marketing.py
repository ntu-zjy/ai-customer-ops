from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .dashboard import get_dashboard_data
from .hermes_client import HermesClient
from .models import MarketingAsset
from .settings_repo import get_knowledge_urls


def generate_xiaohongshu_asset(
    db: Session,
    settings: Settings,
    *,
    topic: str,
    audience: str,
    goal: str,
    tone: str,
    source_context: str,
) -> MarketingAsset:
    result = generate_asset_result(db, settings, topic, audience, goal, tone, source_context)
    asset = MarketingAsset(
        channel="xiaohongshu",
        topic=topic.strip(),
        audience=audience.strip(),
        goal=goal.strip(),
        tone=tone.strip(),
        source_context=source_context.strip(),
        result=result,
        status="generated",
        created_by="agent",
    )
    db.add(asset)
    return asset


def get_recent_marketing_assets(db: Session, limit: int = 12) -> list[MarketingAsset]:
    return list(
        db.scalars(
            select(MarketingAsset)
            .where(MarketingAsset.channel == "xiaohongshu")
            .order_by(MarketingAsset.created_at.desc(), MarketingAsset.id.desc())
            .limit(limit)
        )
    )


def generate_asset_result(
    db: Session,
    settings: Settings,
    topic: str,
    audience: str,
    goal: str,
    tone: str,
    source_context: str,
) -> dict[str, Any]:
    client = HermesClient(settings)
    if not client.is_configured():
        return fallback_xhs_result(db, topic, audience, goal, tone, source_context)

    dashboard = get_dashboard_data(db)
    system_prompt = (
        "你是AI客户经营系统的营销内容Skill，专门生成小红书图文。"
        "你必须输出JSON对象，不要输出Markdown。"
        "内容要适合小红书：标题抓人但不夸大，封面文字短，分镜清晰，正文自然，标签可搜索。"
        "不要承诺未给出的价格、名额、时间、疗效或收益。"
    )
    user_prompt = json.dumps(
        {
            "platform": "xiaohongshu",
            "topic": topic,
            "audience": audience,
            "goal": goal,
            "tone": tone,
            "source_context": source_context,
            "knowledge_urls": get_knowledge_urls(db),
            "crm_signals": {
                "top_questions": dashboard["top_questions"],
                "stage_counts": dashboard["stage_counts"],
                "business_advice": dashboard["advice"],
            },
            "required_schema": {
                "title_options": ["string", "string", "string"],
                "cover_text": "string, <=18 Chinese chars if possible",
                "hook": "string",
                "slides": [
                    {
                        "index": "integer",
                        "title": "string",
                        "body": "string",
                        "visual_prompt": "string for image generation",
                    }
                ],
                "caption": "string",
                "hashtags": ["string"],
                "cta": "string",
                "design_notes": "string",
            },
        },
        ensure_ascii=False,
    )
    try:
        return normalize_xhs_result(client.chat_json(system_prompt, user_prompt), topic)
    except Exception:
        return fallback_xhs_result(db, topic, audience, goal, tone, source_context)


def fallback_xhs_result(
    db: Session,
    topic: str,
    audience: str,
    goal: str,
    tone: str,
    source_context: str,
) -> dict[str, Any]:
    dashboard = get_dashboard_data(db)
    top_question = dashboard["top_questions"][0]["question"] if dashboard["top_questions"] else "报名后下一步怎么走"
    audience_text = audience or "正在关注活动和社群的人"
    goal_text = goal or "引导咨询和报名"
    tone_text = tone or "真实、清爽、有行动感"
    title = topic.strip() or "一场适合小团队的AI活动"
    slides = [
        {
            "index": 1,
            "title": "为什么最近大家都在问这个？",
            "body": f"围绕「{title}」，客户最常问的是：{top_question}。",
            "visual_prompt": f"小红书封面，蓝白清爽科技风，主题为{title}，大字标题，活动/社群场景，真实质感",
        },
        {
            "index": 2,
            "title": "适合谁来参加",
            "body": f"更适合{audience_text}，尤其是想把咨询、报名、进群和跟进串起来的人。",
            "visual_prompt": "干净的信息图，人物头像、标签、客户分层、社群图标，蓝绿点缀",
        },
        {
            "index": 3,
            "title": "你能获得什么",
            "body": "活动信息、案例拆解、同频交流和后续资料入口都会被整理成清晰路径。",
            "visual_prompt": "活动权益清单，日程、资料、社群、客服入口，移动端卡片风格",
        },
        {
            "index": 4,
            "title": "下一步怎么做",
            "body": f"如果你想{goal_text}，可以先咨询/报名，再根据资格进入活动群或人工跟进。",
            "visual_prompt": "流程图视觉，咨询到报名到入群到跟进，简洁箭头，蓝白背景",
        },
    ]
    return normalize_xhs_result(
        {
            "title_options": [f"{title}，到底适合谁？", f"别再错过这些活动信息了", f"报名之前，先看这4点"],
            "cover_text": "报名前先看",
            "hook": f"如果你正在关注「{title}」，这篇帮你快速判断是否适合。",
            "slides": slides,
            "caption": (
                f"这篇整理给{audience_text}。\n\n"
                f"主题：{title}\n"
                f"风格：{tone_text}\n"
                f"重点：先把常见问题讲清楚，再把报名/入群/人工跟进路径说明白。\n\n"
                f"{source_context.strip()[:180]}"
            ).strip(),
            "hashtags": ["#活动报名", "#私域运营", "#AI工具", "#社群运营", "#小微企业"],
            "cta": "想了解具体安排，可以先私信/咨询客服获取报名入口。",
            "design_notes": "蓝白清爽风，封面突出结果，内页用流程图和清单降低理解成本。",
        },
        title,
    )


def normalize_xhs_result(result: dict[str, Any], topic: str) -> dict[str, Any]:
    title_options = [str(item).strip() for item in result.get("title_options", []) if str(item).strip()]
    while len(title_options) < 3:
        title_options.append(f"{topic}，报名前先看这几点")

    slides = result.get("slides", [])
    normalized_slides = []
    for index, slide in enumerate(slides[:8], start=1):
        normalized_slides.append(
            {
                "index": int(slide.get("index") or index),
                "title": str(slide.get("title") or f"第{index}页").strip(),
                "body": str(slide.get("body") or "").strip(),
                "visual_prompt": str(slide.get("visual_prompt") or "").strip(),
            }
        )
    if not normalized_slides:
        normalized_slides.append(
            {
                "index": 1,
                "title": topic,
                "body": "补充活动亮点、适合人群和报名路径。",
                "visual_prompt": f"小红书图文，主题{topic}，蓝白清爽，信息图风格",
            }
        )

    hashtags = [str(item).strip() for item in result.get("hashtags", []) if str(item).strip()]
    return {
        "title_options": title_options[:5],
        "cover_text": str(result.get("cover_text") or title_options[0])[:30],
        "hook": str(result.get("hook") or "").strip(),
        "slides": normalized_slides,
        "caption": str(result.get("caption") or "").strip(),
        "hashtags": hashtags[:12],
        "cta": str(result.get("cta") or "").strip(),
        "design_notes": str(result.get("design_notes") or "").strip(),
    }

