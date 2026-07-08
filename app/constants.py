CUSTOMER_STAGES = [
    "new",
    "consulted",
    "interested",
    "high_intent",
    "registered",
    "pending_review",
    "approved",
    "paid",
    "joined_group",
    "attended",
    "converted",
    "follow_up",
    "lost",
    "dormant",
]

CUSTOMER_STAGE_LABELS = {
    "new": "新客户",
    "consulted": "已咨询",
    "interested": "感兴趣",
    "high_intent": "高意向",
    "registered": "已报名",
    "pending_review": "待审核",
    "approved": "审核通过",
    "paid": "已付费",
    "joined_group": "已入群",
    "attended": "已参加",
    "converted": "已成交",
    "follow_up": "待跟进",
    "lost": "流失",
    "dormant": "沉睡",
}

PROFILE_STAGES = {"new", "interested", "high_intent", "registered", "follow_up", "inactive"}
AI_RECOMMENDABLE_CUSTOMER_STAGES = {"consulted", "interested", "high_intent", "follow_up"}
MANUAL_PROTECTED_STAGES = {
    "registered",
    "pending_review",
    "approved",
    "paid",
    "joined_group",
    "attended",
    "converted",
    "lost",
    "dormant",
}

EVENT_TYPES = [
    "message_received",
    "ai_replied",
    "stage_changed",
    "human_assigned",
    "group_link_sent",
    "form_submitted",
    "payment_success",
    "routing_suggested",
    "analysis_completed",
]

ROUTING_ACTIONS = [
    "answer",
    "send_form",
    "send_payment",
    "send_group_link",
    "assign_human",
    "nurture",
    "recommend_resource",
]

DEFAULT_ROUTING_RULES = [
    {
        "name": "新客户接待",
        "from_stage": "new",
        "action": "answer",
        "target": "AI客服继续接待",
        "message": "先回答活动/社群基础问题，并识别客户需求。",
        "priority": 10,
    },
    {
        "name": "已咨询发报名页",
        "from_stage": "consulted",
        "action": "send_form",
        "target": "活动报名H5",
        "message": "客户已完成初步咨询，推荐发送报名/预约页面。",
        "priority": 20,
    },
    {
        "name": "感兴趣客户继续转化",
        "from_stage": "interested",
        "action": "send_form",
        "target": "活动报名H5",
        "message": "客户有兴趣但尚未报名，推荐给出报名入口和活动价值说明。",
        "priority": 30,
    },
    {
        "name": "高意向客户人工跟进",
        "from_stage": "high_intent",
        "action": "assign_human",
        "target": "资深员工",
        "message": "高意向客户需要5分钟内人工跟进。",
        "priority": 40,
    },
    {
        "name": "已报名发活动群",
        "from_stage": "registered",
        "action": "send_group_link",
        "target": "活动群入口",
        "message": "报名成功后发送活动群入口，同步议程、地址和会前资料。",
        "priority": 50,
    },
    {
        "name": "待审核提醒员工",
        "from_stage": "pending_review",
        "action": "assign_human",
        "target": "审核负责人",
        "message": "客户需要审核资格，提醒员工处理。",
        "priority": 60,
    },
    {
        "name": "审核通过发群入口",
        "from_stage": "approved",
        "action": "send_group_link",
        "target": "活动群入口",
        "message": "审核通过后发送活动群或闭门会入口。",
        "priority": 70,
    },
    {
        "name": "已付费发权益页",
        "from_stage": "paid",
        "action": "recommend_resource",
        "target": "权益页",
        "message": "支付成功后发送权益页，包含群入口、资料、预约和客服入口。",
        "priority": 80,
    },
    {
        "name": "待跟进客户提醒",
        "from_stage": "follow_up",
        "action": "assign_human",
        "target": "客户负责人",
        "message": "客户需要人工承接，建议尽快联系。",
        "priority": 90,
    },
    {
        "name": "沉睡客户养熟",
        "from_stage": "dormant",
        "action": "nurture",
        "target": "养熟SOP",
        "message": "低意向或长期未互动客户进入内容养熟路径。",
        "priority": 100,
    },
]

