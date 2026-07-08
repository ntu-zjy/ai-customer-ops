from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.database import reset_for_tests


def test_alembic_upgrade_head_on_empty_sqlite(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migrate.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    reset_for_tests()

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert "customer_events" in inspector.get_table_names()
    assert "routing_rules" in inspector.get_table_names()
    assert "customer_stage" in [column["name"] for column in inspector.get_columns("users")]
    engine.dispose()
    reset_for_tests()

