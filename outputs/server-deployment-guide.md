# AI客户经营系统 v0.2 服务器部署指南

本文档面向一台全新的腾讯云 CVM，目标是在 Ubuntu 24.04 LTS 上部署：

- Hermes Agent WeCom 网关
- AI客户经营系统 FastAPI 后台
- PostgreSQL 数据库
- Nginx Basic Auth 反向代理
- systemd 常驻服务与定时任务

部署完成后，访问：

```text
http://<服务器公网 IP>/admin/workbench
```

## 1. 部署前准备

### 1.1 服务器规格

建议最低配置：

```text
系统：Ubuntu Server 24.04 LTS
CPU：2 vCPU
内存：4 GB
磁盘：40 GB SSD
公网：需要出站访问企业微信、模型服务、飞书文档
```

腾讯云安全组先开放：

```text
22/tcp   SSH
80/tcp   CRM 后台 HTTP
```

注意：当前方案按你的选择使用“公网 IP + Basic Auth”。这适合内测，不建议长期承载真实用户数据。正式运营前建议升级为“域名 + HTTPS + 更严格登录”。

### 1.2 需要准备的账号和密钥

提前准备：

```text
企业微信组织管理员权限
WeCom AI Bot 的 Bot ID / Secret
Hermes 可用的模型 provider 配置
飞书文档 / 飞书知识库 URL
服务器 root 或 sudo 权限
```

另外生成一个本机 Hermes API Server key，用于 CRM 后台调用 Hermes：

```bash
openssl rand -hex 32
```

下面用 `<HERMES_API_SERVER_KEY>` 表示这个值。

## 2. 约定目录

本项目按以下目录部署：

```text
/opt/event-crm/
  app/                 # 本项目代码
  .venv/               # Python 虚拟环境
  hermes-home/         # 独立 Hermes home，避免混用个人 Hermes 记忆

/etc/event-crm/
  event-crm.env        # CRM 服务配置
  hermes.env           # Hermes gateway 配置

/etc/systemd/system/
  event-crm.service
  event-crm-sync.service
  event-crm-sync.timer
  event-crm-analyze.service
  event-crm-analyze.timer
  hermes-gateway.service
```

## 3. 获取项目代码

推荐使用 GitHub 仓库部署，当前仓库为：

```text
https://github.com/ntu-zjy/ai-customer-ops
```

### 3.1 Public 仓库：直接 HTTPS Clone

如果仓库是 public，服务器不需要 GitHub Deploy Key。直接用 HTTPS 拉取：

```bash
sudo mkdir -p /opt/event-crm
sudo chown -R "$USER:$USER" /opt/event-crm
cd /opt/event-crm
git clone https://github.com/ntu-zjy/ai-customer-ops.git app
```

注意：不要使用下面这种 SSH 地址，除非你已经配置了 SSH key 或 Deploy Key：

```text
git@github.com:ntu-zjy/ai-customer-ops.git
```

### 3.2 Private 仓库：配置 GitHub 拉取权限

如果仓库改回 private，或者你希望服务器用 SSH 方式拉取，再在腾讯云 CVM 上生成一把单独的 SSH key：

```bash
ssh-keygen -t ed25519 -C "event-crm-cvm" -f ~/.ssh/event_crm_github
cat ~/.ssh/event_crm_github.pub
```

把输出的公钥添加到 GitHub：

```text
GitHub -> ntu-zjy/ai-customer-ops -> Settings -> Deploy keys -> Add deploy key
```

只需要勾选读权限即可；如果希望服务器上也能直接 push，再勾选写权限。

然后在服务器上添加 SSH 配置：

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/event_crm_github
  IdentitiesOnly yes
EOF

chmod 600 ~/.ssh/config
ssh -T git@github.com
```

如果你不想配置 Deploy Key，也可以用 HTTPS + GitHub token，但不建议把 token 写进脚本或文档。

### 3.3 Clone 代码到部署目录

如果已经按 3.1 用 HTTPS clone 过，可以跳过这一节。否则，配置好 Deploy Key 后再用 SSH clone：

```bash
sudo mkdir -p /opt/event-crm
sudo chown -R "$USER:$USER" /opt/event-crm
cd /opt/event-crm
git clone git@github.com:ntu-zjy/ai-customer-ops.git app
```

确认服务器上能看到项目文件：

```bash
ls -la /opt/event-crm/app
ls -la /opt/event-crm/app/scripts/install_ubuntu.sh
```

后续更新代码时，在服务器执行：

```bash
cd /opt/event-crm/app
git pull --ff-only
sudo systemctl restart event-crm
```

## 4. 安装系统依赖和 CRM 服务

进入项目目录：

```bash
cd /opt/event-crm/app
```

执行安装脚本：

```bash
sudo bash scripts/install_ubuntu.sh
```

脚本会做这些事：

- 安装 Python 3.12、PostgreSQL、Nginx、Basic Auth 工具
- 创建系统用户 `eventcrm`
- 创建 PostgreSQL 用户和数据库：`event_crm`
- 创建 `/opt/event-crm/.venv`
- 安装当前项目
- 复制 systemd 单元和 Nginx 配置
- 创建默认 Basic Auth：`admin / changeme`
- 初始化数据库表

安装完成后，先修改 Basic Auth 密码：

```bash
sudo htpasswd /etc/nginx/.event-crm.htpasswd admin
```

输入一个新的强密码。

## 5. 安装 Hermes Agent

官方当前的命令行安装方式是：

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

安装后重新加载 shell：

```bash
source ~/.bashrc
```

确认：

```bash
command -v hermes
hermes --help
```

项目的 systemd 单元默认用：

```text
/usr/local/bin/hermes
```

如果 `command -v hermes` 输出不是 `/usr/local/bin/hermes`，做一个软链接，或者修改 `deploy/systemd/hermes-gateway.service` 后重新复制到 `/etc/systemd/system/`。

推荐软链接：

```bash
sudo ln -sf "$(command -v hermes)" /usr/local/bin/hermes
/usr/local/bin/hermes --help
```

## 6. 配置环境变量

### 6.1 配置 CRM 服务

编辑：

```bash
sudo nano /etc/event-crm/event-crm.env
```

推荐内容：

```bash
APP_NAME="AI客户经营系统"
DATABASE_URL=postgresql+psycopg://event_crm:event_crm@localhost:5432/event_crm

HERMES_HOME=/opt/event-crm/hermes-home
HERMES_STATE_DB=/opt/event-crm/hermes-home/state.db
HERMES_PLATFORM=wecom
HERMES_BOT_ID=<你的 WeCom Bot ID>
HERMES_SOURCE_FILTER=wecom

HERMES_API_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=<HERMES_API_SERVER_KEY>
HERMES_MODEL_NAME=hermes-agent

WECOM_KF_TOKEN=<微信客服回调 Token>
WECOM_KF_ENCODING_AES_KEY=<微信客服 EncodingAESKey>
WECOM_CORP_ID=<企业微信 Corp ID>

SYNC_BATCH_SIZE=500
ANALYZE_DUE_LIMIT=50
ADMIN_PAGE_SIZE=100
```

关键点：

- `HERMES_BOT_ID` 必须和企业微信 AI Bot 一致。
- `HERMES_API_KEY` 必须等于下一节 Hermes 的 `API_SERVER_KEY`。
- `HERMES_STATE_DB` 指向独立 Hermes home 下的 `state.db`。
- `WECOM_KF_*` 用于普通微信外部用户访问的“微信客服”回调验证；如果暂时只测内部企微 Bot，可以先留空。

如果你要修改数据库默认密码：

```bash
sudo -u postgres psql -c "ALTER ROLE event_crm WITH PASSWORD '<新数据库密码>';"
sudo nano /etc/event-crm/event-crm.env
```

然后把 `DATABASE_URL` 里的密码同步改掉。

### 6.2 配置 Hermes gateway

创建或编辑：

```bash
sudo nano /etc/event-crm/hermes.env
```

写入：

```bash
HERMES_HOME=/opt/event-crm/hermes-home

WECOM_BOT_ID=<你的 WeCom Bot ID>
WECOM_SECRET=<你的 WeCom Bot Secret>
WECOM_DM_POLICY=open
WECOM_GROUP_POLICY=disabled

API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=<HERMES_API_SERVER_KEY>
```

保护权限：

```bash
sudo chmod 640 /etc/event-crm/event-crm.env /etc/event-crm/hermes.env
sudo chown root:eventcrm /etc/event-crm/event-crm.env /etc/event-crm/hermes.env
```

### 6.3 配置微信客服回调（外部微信用户）

如果要让普通微信用户咨询，创建企业微信“微信客服”账号后，在微信客服 API / 回调配置里填写：

```text
URL: http://<服务器公网 IP>/wecom/kf/callback
Token: 自己生成一段随机字符串，写入 WECOM_KF_TOKEN
EncodingAESKey: 企微后台随机生成，写入 WECOM_KF_ENCODING_AES_KEY
```

同时在 `/etc/event-crm/event-crm.env` 填入企业微信 `Corp ID`：

```bash
WECOM_CORP_ID=<企业微信 Corp ID>
```

当前代码会完成企业微信 URL 验证和回调确认。真实客户消息解密、调用 Hermes 回复、写入 CRM 的完整客服链路在后续版本补齐。

## 7. 初始化 Hermes 独立 Home

先确保目录归属：

```bash
sudo mkdir -p /opt/event-crm/hermes-home
sudo chown -R eventcrm:eventcrm /opt/event-crm/hermes-home
```

用独立 home 跑 Hermes setup：

```bash
sudo -u eventcrm -H env \
  HERMES_HOME=/opt/event-crm/hermes-home \
  /usr/local/bin/hermes setup
```

按提示配置模型 provider。

再配置 gateway：

```bash
sudo -u eventcrm -H env \
  HERMES_HOME=/opt/event-crm/hermes-home \
  WECOM_BOT_ID=<你的 WeCom Bot ID> \
  WECOM_SECRET=<你的 WeCom Bot Secret> \
  /usr/local/bin/hermes gateway setup
```

选择 WeCom / 企业微信。可以扫码创建，也可以手动输入 Bot ID 和 Secret。

## 8. 禁用 Hermes 全局记忆

这是本项目的关键隔离要求：用户画像和历史只存 CRM 数据库，不写入 Hermes 全局 memory。

执行：

```bash
sudo -u eventcrm -H env HERMES_HOME=/opt/event-crm/hermes-home \
  /usr/local/bin/hermes memory off || true

sudo -u eventcrm -H env HERMES_HOME=/opt/event-crm/hermes-home \
  /usr/local/bin/hermes tools disable memory || true
```

再检查并清空本地全局记忆文件：

```bash
sudo -u eventcrm mkdir -p /opt/event-crm/hermes-home
sudo -u eventcrm sh -c ': > /opt/event-crm/hermes-home/MEMORY.md'
sudo -u eventcrm sh -c ': > /opt/event-crm/hermes-home/USER.md'
```

如果 Hermes 配置文件存在，建议确认里面没有启用外部 memory provider：

```bash
sudo -u eventcrm sed -n '1,240p' /opt/event-crm/hermes-home/config.yaml
```

如果看到 Honcho、Mem0、Supermemory 等外部 memory provider，关闭它们后重启 gateway。

## 9. 初始化数据库和启动服务

重新加载 systemd：

```bash
sudo systemctl daemon-reload
```

初始化数据库表。新部署直接执行：

```bash
sudo -u eventcrm -H bash -lc '
  set -a
  source /etc/event-crm/event-crm.env
  set +a
  cd /opt/event-crm/app
  /opt/event-crm/.venv/bin/python -m app.cli init-db
'
```

如果这是已经运行过 v0 的旧数据库，先执行 baseline stamp，再升级：

```bash
sudo -u eventcrm -H bash -lc '
  set -a
  source /etc/event-crm/event-crm.env
  set +a
  cd /opt/event-crm/app
  /opt/event-crm/.venv/bin/python -m app.cli db-stamp-baseline
  /opt/event-crm/.venv/bin/python -m app.cli db-upgrade
  /opt/event-crm/.venv/bin/python -m app.cli seed-rules
'
```

检查 Nginx 配置：

```bash
sudo nginx -t
```

启动服务：

```bash
sudo systemctl enable --now postgresql
sudo systemctl enable --now nginx
sudo systemctl enable --now hermes-gateway
sudo systemctl enable --now event-crm
sudo systemctl enable --now event-crm-sync.timer
sudo systemctl enable --now event-crm-analyze.timer
```

检查状态：

```bash
sudo systemctl status hermes-gateway --no-pager
sudo systemctl status event-crm --no-pager
sudo systemctl status event-crm-sync.timer --no-pager
sudo systemctl status event-crm-analyze.timer --no-pager
```

## 10. 验证部署

### 10.1 服务健康检查

服务器本机：

```bash
curl -i http://127.0.0.1:8000/healthz
```

应返回：

```json
{"status":"ok"}
```

公网 Basic Auth：

```bash
curl -i -u admin:<你的 Basic Auth 密码> http://<公网IP>/healthz
```

后台页面：

```text
http://<公网IP>/admin/workbench
```

### 10.2 Hermes API Server

服务器本机验证：

```bash
curl -s http://127.0.0.1:8642/health

curl -s \
  -H "Authorization: Bearer <HERMES_API_SERVER_KEY>" \
  http://127.0.0.1:8642/v1/models
```

如果 `/v1/models` 返回模型列表，说明 CRM 后台能调用 Hermes 做用户画像分析。

### 10.3 企业微信私聊验证

用企业微信给 AI Bot 发几条 1 对 1 私聊消息：

```text
我想报名这个活动
活动时间是什么时候？
价格多少钱？
```

查看 Hermes 日志：

```bash
sudo journalctl -u hermes-gateway -n 120 --no-pager
```

手动触发同步：

```bash
sudo systemctl start event-crm-sync.service
sudo journalctl -u event-crm-sync.service -n 80 --no-pager
```

查看数据库：

```bash
sudo -u postgres psql -d event_crm -c "select id, external_user_id, message_count, last_message_at from users order by last_message_at desc limit 10;"
sudo -u postgres psql -d event_crm -c "select user_id, role, message_type, left(content, 80), created_at from messages order by created_at desc limit 20;"
```

打开后台：

```text
http://<公网IP>/admin/workbench
```

应能看到新用户和消息。

### 10.4 手动触发画像分析

后台点击用户详情页的“重新分析”，或命令行：

```bash
sudo -u eventcrm -H bash -lc '
  set -a
  source /etc/event-crm/event-crm.env
  set +a
  cd /opt/event-crm/app
  /opt/event-crm/.venv/bin/python -m app.cli analyze-due --limit 10
'
```

查看结果：

```bash
sudo -u postgres psql -d event_crm -c "select user_id, stage, intent_score, left(summary, 100), updated_at from user_profiles order by updated_at desc limit 10;"
sudo -u postgres psql -d event_crm -c "select user_id, tag, confidence, updated_at from user_tags order by updated_at desc limit 20;"
```

## 11. 配置飞书知识文档

访问：

```text
http://<公网IP>/admin/settings/knowledge
```

每行填写一个飞书文档或知识库 URL，例如：

```text
https://xxx.feishu.cn/wiki/...
https://xxx.feishu.cn/docx/...
```

保存后，这些 URL 会存入 `app_settings`。本项目不做 RAG、不做 embedding、不建向量库；这些 URL 作为共享活动知识入口，由 Hermes 在对话/分析时按能力读取或引用。

## 12. systemd 定时任务

当前有两个 timer：

```text
event-crm-sync.timer       每 60 秒同步 Hermes state.db 新消息
event-crm-analyze.timer    每 1 小时分析有新消息的用户
```

查看 timer：

```bash
sudo systemctl list-timers | grep event-crm
```

手动跑一次同步：

```bash
sudo systemctl start event-crm-sync.service
sudo journalctl -u event-crm-sync.service -n 80 --no-pager
```

手动跑一次分析：

```bash
sudo systemctl start event-crm-analyze.service
sudo journalctl -u event-crm-analyze.service -n 80 --no-pager
```

## 13. 日常运维命令

查看服务：

```bash
sudo systemctl status event-crm --no-pager
sudo systemctl status hermes-gateway --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status postgresql --no-pager
```

查看日志：

```bash
sudo journalctl -u event-crm -f
sudo journalctl -u hermes-gateway -f
sudo journalctl -u event-crm-sync.service -n 100 --no-pager
sudo journalctl -u event-crm-analyze.service -n 100 --no-pager
```

重启：

```bash
sudo systemctl restart event-crm
sudo systemctl restart hermes-gateway
sudo systemctl restart nginx
```

更新代码后：

```bash
cd /opt/event-crm/app
sudo -u eventcrm /opt/event-crm/.venv/bin/pip install -e .
sudo -u eventcrm -H bash -lc '
  set -a
  source /etc/event-crm/event-crm.env
  set +a
  cd /opt/event-crm/app
  /opt/event-crm/.venv/bin/python -m app.cli init-db
'
sudo systemctl restart event-crm
```

如果更新了 systemd 文件：

```bash
sudo cp /opt/event-crm/app/deploy/systemd/*.service /opt/event-crm/app/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart event-crm hermes-gateway
```

如果更新了 Nginx 配置：

```bash
sudo cp /opt/event-crm/app/deploy/nginx/event-crm.conf /etc/nginx/sites-available/event-crm.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 14. 备份和恢复

### 14.1 PostgreSQL 备份

```bash
sudo mkdir -p /opt/event-crm/backups
sudo -u postgres pg_dump event_crm | gzip | sudo tee /opt/event-crm/backups/event_crm-$(date +%F-%H%M).sql.gz >/dev/null
```

### 14.2 Hermes home 备份

注意：`hermes-home` 可能包含 secret、会话和状态库，备份文件要保护权限。

```bash
sudo tar -czf /opt/event-crm/backups/hermes-home-$(date +%F-%H%M).tar.gz \
  -C /opt/event-crm hermes-home
sudo chmod 600 /opt/event-crm/backups/hermes-home-*.tar.gz
```

### 14.3 恢复 PostgreSQL

```bash
gunzip -c /path/to/event_crm.sql.gz | sudo -u postgres psql event_crm
```

## 15. 排障清单

### 后台打不开

检查：

```bash
sudo systemctl status event-crm --no-pager
sudo systemctl status nginx --no-pager
sudo nginx -t
curl -i http://127.0.0.1:8000/healthz
```

常见原因：

- `event-crm.service` 没启动
- `/etc/event-crm/event-crm.env` 配错
- PostgreSQL 没启动
- Nginx Basic Auth 密码输错
- 腾讯云安全组没开放 80

### 企业微信消息没有进入 CRM

检查 Hermes 是否收到消息：

```bash
sudo journalctl -u hermes-gateway -n 200 --no-pager
```

检查 Hermes state.db 是否存在：

```bash
sudo ls -lh /opt/event-crm/hermes-home/state.db
```

手动同步：

```bash
sudo systemctl start event-crm-sync.service
sudo journalctl -u event-crm-sync.service -n 100 --no-pager
```

常见原因：

- `HERMES_STATE_DB` 路径不对
- `HERMES_SOURCE_FILTER` 和 Hermes sessions.source 不匹配
- WeCom Bot ID/Secret 配错
- 企业微信 AI Bot 没有给测试用户开放
- `WECOM_GROUP_POLICY` 没关，测试消息发到了群里但 v0 只做 1 对 1

### 画像分析没有结果

检查：

```bash
sudo journalctl -u event-crm-analyze.service -n 120 --no-pager
curl -s -H "Authorization: Bearer <HERMES_API_SERVER_KEY>" http://127.0.0.1:8642/v1/models
```

说明：

- 如果 `HERMES_API_KEY` 没配置，系统会使用启发式兜底分析。
- 如果 Hermes API Server 不通，分析不会影响消息同步，但画像质量会下降。
- `HERMES_API_KEY` 和 Hermes 的 `API_SERVER_KEY` 必须一致。

### Hermes gateway 起不来

检查二进制路径：

```bash
ls -l /usr/local/bin/hermes
/usr/local/bin/hermes --help
```

如果没有：

```bash
sudo ln -sf "$(command -v hermes)" /usr/local/bin/hermes
sudo systemctl restart hermes-gateway
```

检查环境变量：

```bash
sudo cat /etc/event-crm/hermes.env
```

不要把 `WECOM_SECRET` 发到聊天或日志里。

## 16. 上线验收清单

上线前逐项确认：

- `http://<公网IP>/healthz` 通过 Basic Auth 可访问
- `/admin/workbench` 能打开
- `/admin/dashboard` 能打开
- `/admin/rules` 能打开
- `/admin/marketing` 能打开
- `/admin/settings/knowledge` 已填写飞书文档 URL
- 企业微信 1 对 1 私聊能收到 Hermes 回复
- 群聊消息不响应
- 两个不同企微用户的 CRM 记录不串
- `MEMORY.md` 和 `USER.md` 为空或不存在
- Hermes external memory provider 已关闭
- `event-crm-sync.timer` 正常运行
- `event-crm-analyze.timer` 正常运行
- Basic Auth 默认密码 `changeme` 已修改
- 数据库默认密码已按需要修改
- 已设置备份策略

## 17. 参考资料

- Hermes 官方安装文档：<https://hermes-agent.nousresearch.com/docs/getting-started/installation>
- Hermes WeCom 文档：<https://hermes-agent.nousresearch.com/docs/user-guide/messaging/wecom>
- Hermes API Server / Open WebUI 文档：<https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui>
- Hermes Session Storage 文档：<https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage>
