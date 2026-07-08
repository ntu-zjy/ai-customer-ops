import argparse
import sys

from alembic import command
from alembic.config import Config

from .analysis import analyze_due_users, analyze_user
from .config import get_settings
from .database import session_scope
from .hermes_sync import sync_hermes_messages
from .routing import ensure_default_routing_rules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="event-crm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Run database migrations and seed defaults")
    subparsers.add_parser("db-upgrade", help="Run Alembic upgrade head")
    subparsers.add_parser("db-stamp-baseline", help="Stamp an existing v0 database at baseline")
    subparsers.add_parser("seed-rules", help="Seed default routing rules")
    subparsers.add_parser("sync-hermes", help="Sync new messages from Hermes state.db")

    analyze_due = subparsers.add_parser("analyze-due", help="Analyze users with new messages")
    analyze_due.add_argument("--limit", type=int, default=None)

    analyze_one = subparsers.add_parser("analyze-user", help="Analyze one user by CRM user id")
    analyze_one.add_argument("user_id")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "init-db":
        upgrade_database()
        with session_scope() as db:
            created = ensure_default_routing_rules(db)
        print(f"database is ready; seeded {created} routing rule(s)")
        return 0

    if args.command == "db-upgrade":
        upgrade_database()
        print("database upgraded")
        return 0

    if args.command == "db-stamp-baseline":
        alembic_cfg = Config("alembic.ini")
        command.stamp(alembic_cfg, "0001_baseline_current")
        print("database stamped at 0001_baseline_current")
        return 0

    if args.command == "seed-rules":
        with session_scope() as db:
            created = ensure_default_routing_rules(db)
        print(f"seeded {created} routing rule(s)")
        return 0

    if args.command == "sync-hermes":
        with session_scope() as db:
            inserted = sync_hermes_messages(db, settings)
        print(f"synced {inserted} message(s)")
        return 0

    if args.command == "analyze-due":
        with session_scope() as db:
            analyzed = analyze_due_users(db, settings, limit=args.limit)
        print(f"analyzed {analyzed} user(s)")
        return 0

    if args.command == "analyze-user":
        with session_scope() as db:
            analyze_user(db, settings, args.user_id)
        print(f"analyzed user {args.user_id}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def upgrade_database() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
