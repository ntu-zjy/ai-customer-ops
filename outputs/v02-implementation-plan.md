# v0.2 实施计划：AI客户经营系统后台升级

## 1. Summary

v0.2 在现有 FastAPI + Jinja2 + PostgreSQL + Hermes 架构上升级，不引入前端 SPA。目标是把现有“薄 CRM 列表页”升级成可演示、可部署、可继续扩展的 AI客户经营系统后台。

本次实现重点：

- 数据底座：`customer_stage`、`customer_events`、`routing_rules`。
- 页面：员工工作台、客户管理升级、规则配置、老板经营看板、战略 Agent。
- 营销：小红书图文生成 Skill，产出标题、封面、分镜、配图提示词、正文和标签。
- 迁移：新增 Alembic，支持 fresh deploy 和 v0 已有库升级。
- 测试：覆盖迁移、同步事件、阶段保护、看板聚合和页面渲染。

## 2. Implementation Changes

### 2.1 数据模型和迁移

- `users` 新增字段：
  - `customer_stage`
  - `source_channel`
  - `owner_name`
  - `last_event_at`
- 新增 `customer_events`：
  - 记录消息、AI回复、阶段变化、画像分析、后续成交动作。
  - 所有老板看板和战略 Agent 优先基于事件聚合。
- 新增 `routing_rules`：
  - 内置活动/社群模板规则。
  - v0.2 只做 action suggestion，不执行真实外部动作。
- 新增 Alembic：
  - `0001_baseline_current`：创建 v0 基线表。
  - `0002_v02_customer_ops`：升级 v0.2 字段和表。

已有 v0 服务器升级：

```bash
python -m app.cli db-stamp-baseline
python -m app.cli db-upgrade
python -m app.cli seed-rules
```

新服务器部署：

```bash
python -m app.cli init-db
```

### 2.2 后端服务

- `events.py`
  - 统一写入客户事件。
  - 手动阶段变更写 `stage_changed`。
- `routing.py`
  - seed 默认分流规则。
  - 根据客户阶段生成推荐动作。
  - 支持后台编辑启停、目标、说明和优先级。
- `dashboard.py`
  - 聚合工作台和老板看板数据。
  - 统计 KPI、漏斗、阶段分布、来源、员工、高频问题。
- `strategy_agent.py`
  - 基于 dashboard 聚合数据回答老板问题。
  - Hermes API 不可用时返回 deterministic fallback。
- `marketing.py`
  - 以 Agent Skill 方式生成小红书图文包。
  - Hermes API 不可用时返回活动/社群模板兜底内容。
  - 保存到 `marketing_assets` 供运营回看。

### 2.3 同步和分析

- Hermes 同步：
  - 新消息仍按 Hermes message id 去重。
  - 用户消息写 `message_received`，AI 回复写 `ai_replied`。
  - 新客户从 `new` 推进到 `consulted`。
  - 更新 `source_channel` 和 `last_event_at`。
- 用户画像分析：
  - 更新 `user_profiles` 和 `user_tags`。
  - 写 `analysis_completed`。
  - 只允许 AI 从 new/consulted/interested 推进到 consulted/interested/high_intent/follow_up。
  - 不覆盖 registered、paid、joined_group、converted 等业务阶段。

### 2.4 Web 后台

- 根路径跳转到 `/admin/workbench`。
- 新增 `/admin/workbench`：
  - KPI、客户表、客户摘要、推荐动作、待办提醒、高频问题。
- 升级 `/admin/users` 和 `/admin/users/{user_id}`：
  - 使用 canonical `customer_stage`。
  - 支持手动更新阶段。
  - 展示客户事件和推荐动作。
- 新增 `/admin/rules`：
  - 展示默认活动/社群规则。
  - 支持启停、目标、说明、优先级编辑。
- 新增 `/admin/dashboard`：
  - 老板 KPI、转化漏斗、渠道效果、阶段分布、员工跟进、高频问题、经营建议。
- 新增 `/admin/dashboard/ask`：
  - 战略 Agent 查询。
- 新增 `/admin/marketing` 和 `/admin/marketing/generate`：
  - 输入主题、人群、目标、语气和补充资料。
  - 输出标题、封面、分镜、配图 prompt、正文、标签和 CTA。

## 3. Deployment Notes

- 新增依赖：`alembic`。
- `python -m app.cli init-db` 现在会执行 Alembic `upgrade head` 并 seed 默认规则。
- 服务器部署脚本可继续调用 `init-db`。
- 已有 v0 服务器不能直接 `upgrade head`，需要先 `db-stamp-baseline`。
- Nginx、systemd、Hermes 配置保持不变。

## 4. Test Plan

已新增/保留以下测试：

- Alembic 空 SQLite 库 `upgrade head`。
- marketing assets 迁移和 fallback 生成可用。
- Hermes 同步消息后写入 `customer_events`，并保持消息去重。
- 两个企微用户的消息、事件、画像不串。
- AI 分析不会覆盖 `paid` 等业务阶段。
- 员工工作台、老板看板、规则配置、知识库、客户页可空数据渲染。
- 看板聚合使用真实测试数据。
- 战略 Agent fallback 在 Hermes API 未配置时可用。
- 小红书图文生成在 Hermes API 未配置时可用，并保存历史记录。

本地验证命令：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall app
DATABASE_URL=sqlite:///./work/smoke.db .venv/bin/python -m app.cli init-db
```

## 5. Acceptance Criteria

- `/admin/workbench` 返回 200，并展示员工工作台。
- `/admin/dashboard` 返回 200，并展示老板经营看板。
- `/admin/rules` 返回 200，并展示默认分流规则。
- `/admin/marketing` 返回 200，并能生成小红书图文包。
- `/admin/users/{user_id}` 可手动更新客户阶段，数据库产生 `stage_changed`。
- Hermes 同步后 `messages` 和 `customer_events` 都有记录。
- PRD 和实施计划都保存到 `outputs/`。
