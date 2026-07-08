from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.hermes_sync import sync_hermes_messages
from app.models import CustomerEvent, Message, User

from conftest import create_hermes_state


def test_sync_hermes_messages_isolates_users_and_deduplicates(db, app_env: Path) -> None:
    create_hermes_state(app_env)

    inserted = sync_hermes_messages(db, get_settings())
    db.commit()

    assert inserted == 3
    users = list(db.scalars(select(User).order_by(User.external_user_id)))
    assert [user.external_user_id for user in users] == ["alice", "bob"]

    alice_messages = list(db.scalars(select(Message).where(Message.user_id == users[0].id)))
    bob_messages = list(db.scalars(select(Message).where(Message.user_id == users[1].id)))
    assert len(alice_messages) == 2
    assert len(bob_messages) == 1
    assert {message.external_user_id for message in alice_messages} == {"alice"}
    assert {message.external_user_id for message in bob_messages} == {"bob"}
    assert users[0].customer_stage == "consulted"
    assert users[1].customer_stage == "consulted"
    assert db.scalar(select(CustomerEvent).where(CustomerEvent.event_type == "message_received")) is not None
    assert len(list(db.scalars(select(CustomerEvent)))) == 3

    inserted_again = sync_hermes_messages(db, get_settings())
    db.commit()
    assert inserted_again == 0
