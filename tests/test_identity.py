from app.identity import make_user_id


def test_user_id_includes_platform_bot_and_external_user() -> None:
    first = make_user_id("wecom", "bot-a", "user-1")
    same = make_user_id("WECOM", "bot-a", "user-1")
    other_bot = make_user_id("wecom", "bot-b", "user-1")
    other_user = make_user_id("wecom", "bot-a", "user-2")

    assert first == same
    assert first != other_bot
    assert first != other_user

