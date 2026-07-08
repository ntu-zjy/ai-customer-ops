from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .config import Settings
from .dashboard import get_dashboard_data
from .hermes_client import HermesClient


def answer_strategy_question(db: Session, settings: Settings, question: str) -> str:
    data = get_dashboard_data(db)
    fallback = deterministic_answer(data, question)
    client = HermesClient(settings)
    if not client.is_configured():
        return fallback

    system_prompt = (
        "你是小微企业 AI客户经营系统的老板战略Agent。"
        "只能基于提供的CRM聚合数据回答，不要编造外部数据。"
        "回答要短，给出经营判断和下一步建议。"
    )
    user_prompt = json.dumps(
        {
            "question": question,
            "crm_dashboard": {
                "kpis": [kpi.__dict__ for kpi in data["kpis"]],
                "stage_counts": data["stage_counts"],
                "source_counts": data["source_counts"],
                "top_questions": data["top_questions"],
                "employee_rows": [
                    {k: (str(v) if k == "last_event_at" else v) for k, v in row.items()}
                    for row in data["employee_rows"]
                ],
                "event_counts": data["event_counts"],
                "advice": data["advice"],
            },
        },
        ensure_ascii=False,
    )
    try:
        result = client.chat_json(system_prompt, user_prompt)
        answer = str(result.get("answer") or result.get("summary") or "").strip()
        return answer or fallback
    except Exception:
        return fallback


def deterministic_answer(data: dict, question: str) -> str:
    kpis = {item.label: item.value for item in data["kpis"]}
    advice = "；".join(data["advice"])
    top_source = data["source_counts"][0]["source"] if data["source_counts"] else "暂无来源数据"
    top_question = data["top_questions"][0]["question"] if data["top_questions"] else "暂无高频问题"
    return (
        f"基于当前CRM数据：今日新增客户 {kpis.get('今日新增客户', '0')}，"
        f"高意向客户 {kpis.get('高意向客户', '0')}，AI解决率 {kpis.get('AI解决率', '0%')}。"
        f"当前主要来源是 {top_source}，客户高频问题是“{top_question}”。建议：{advice}"
    )

