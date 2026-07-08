#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/event-crm/app}"
APP_USER="${APP_USER:-eventcrm}"
ENV_DIR="/etc/event-crm"

apt-get update
apt-get install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib nginx apache2-utils

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home /opt/event-crm --shell /usr/sbin/nologin "$APP_USER"
mkdir -p /opt/event-crm/hermes-home "$ENV_DIR"
chown -R "$APP_USER:$APP_USER" /opt/event-crm

sudo -u postgres psql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'event_crm') THEN
    CREATE ROLE event_crm LOGIN PASSWORD 'event_crm';
  END IF;
END
$$;
SELECT 'CREATE DATABASE event_crm OWNER event_crm'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'event_crm')\gexec
SQL

cd "$APP_ROOT"
python3.12 -m venv /opt/event-crm/.venv
/opt/event-crm/.venv/bin/pip install --upgrade pip
/opt/event-crm/.venv/bin/pip install -e .

if [ ! -f "$ENV_DIR/event-crm.env" ]; then
  cp "$APP_ROOT/.env.example" "$ENV_DIR/event-crm.env"
  chmod 640 "$ENV_DIR/event-crm.env"
  chown root:"$APP_USER" "$ENV_DIR/event-crm.env"
fi

cp "$APP_ROOT/deploy/systemd/"*.service "$APP_ROOT/deploy/systemd/"*.timer /etc/systemd/system/
cp "$APP_ROOT/deploy/nginx/event-crm.conf" /etc/nginx/sites-available/event-crm.conf
ln -sf /etc/nginx/sites-available/event-crm.conf /etc/nginx/sites-enabled/event-crm.conf
rm -f /etc/nginx/sites-enabled/default

if [ ! -f /etc/nginx/.event-crm.htpasswd ]; then
  htpasswd -bc /etc/nginx/.event-crm.htpasswd admin changeme
fi

systemctl daemon-reload
/opt/event-crm/.venv/bin/python -m app.cli init-db
nginx -t

cat <<'EOF'
Install finished.

Next:
1. Edit /etc/event-crm/event-crm.env.
2. Change Basic Auth password: htpasswd /etc/nginx/.event-crm.htpasswd admin
3. Configure Hermes with HERMES_HOME=/opt/event-crm/hermes-home hermes gateway setup
4. systemctl enable --now hermes-gateway event-crm event-crm-sync.timer event-crm-analyze.timer nginx
EOF

