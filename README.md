# AI客户经营系统 v0.2

这个项目实现面向小微企业的 AI 客户经营系统：从 Hermes Agent 的 `state.db` 同步企微消息到 PostgreSQL，提供员工工作台、客户管理、知识库、规则配置、老板看板和战略 Agent 入口。

## 本地启动

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
python -m app.cli init-db
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

默认数据库是 PostgreSQL。临时本地试跑可以把 `.env` 里的 `DATABASE_URL` 改成：

```bash
DATABASE_URL=sqlite:///./event_crm.db
```

## 关键命令

```bash
python -m app.cli init-db
python -m app.cli db-upgrade
python -m app.cli db-stamp-baseline
python -m app.cli seed-rules
python -m app.cli sync-hermes
python -m app.cli analyze-due --limit 50
python -m app.cli analyze-user <crm-user-id>
```

## 服务器部署顺序

1. 腾讯云 CVM 使用 Ubuntu 24.04 LTS，安全组开放 `22` 和 `80`。
2. 上传本项目到 `/opt/event-crm/app`。
3. 参考 `scripts/install_ubuntu.sh` 安装 Python、PostgreSQL、Nginx、venv 和 systemd 单元。
4. 编辑 `/etc/event-crm/event-crm.env`，填入数据库、Hermes home、WeCom Bot ID、本机 Hermes API key。
5. 配置 Hermes 独立 home：`HERMES_HOME=/opt/event-crm/hermes-home hermes gateway setup`，选择 WeCom。
6. 如需普通微信外部用户咨询，配置企业微信“微信客服”回调：`http://<公网 IP>/wecom/kf/callback`，并在 `event-crm.env` 填入 `WECOM_KF_TOKEN`、`WECOM_KF_ENCODING_AES_KEY`、`WECOM_CORP_ID`。
7. 禁用 Hermes 全局记忆：关闭 external memory provider，禁用 memory toolset，保持 `MEMORY.md` 和 `USER.md` 为空或不存在。
8. 启动服务：`systemctl enable --now hermes-gateway event-crm event-crm-sync.timer event-crm-analyze.timer`。
9. 打开 `http://<公网 IP>/admin/workbench`，使用 Nginx Basic Auth 账号密码访问。

已有 v0 数据库升级到 v0.2 时，先执行：

```bash
python -m app.cli db-stamp-baseline
python -m app.cli db-upgrade
python -m app.cli seed-rules
```

## 隔离原则

- 用户身份由 `platform + bot_id + external_user_id` 生成，不共享用户上下文。
- CRM 只从 Hermes `state.db` 只读同步消息，不写 Hermes 内部状态。
- 用户画像只存 PostgreSQL 的 `user_profiles` / `user_tags`。
- 客户阶段以 `users.customer_stage` 为准，客户事件写入 `customer_events`。
- 飞书文档 URL 是共享知识源配置，不做 RAG、embedding 或向量库。

## v0.2 页面

```text
/admin/workbench              员工工作台
/admin/users                  客户管理
/admin/settings/knowledge     知识库
/admin/rules                  规则配置
/admin/marketing              营销素材 Skill
/admin/dashboard              老板经营看板
/wecom/kf/callback            企业微信微信客服回调验证入口
```
