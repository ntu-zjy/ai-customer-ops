from sqlalchemy.orm import Session

from .models import AppSetting, utc_now

KNOWLEDGE_URLS_KEY = "knowledge_document_urls"
HERMES_SYNC_CURSOR_KEY = "hermes_sync_cursor"


def get_json_setting(db: Session, key: str, default: dict | None = None) -> dict:
    setting = db.get(AppSetting, key)
    if setting is None:
        return default or {}
    return setting.value or {}


def set_json_setting(db: Session, key: str, value: dict) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
        setting.updated_at = utc_now()


def get_knowledge_urls(db: Session) -> list[str]:
    value = get_json_setting(db, KNOWLEDGE_URLS_KEY, {"urls": []})
    urls = value.get("urls", [])
    return [str(url).strip() for url in urls if str(url).strip()]


def set_knowledge_urls(db: Session, urls: list[str]) -> None:
    cleaned = []
    seen = set()
    for url in urls:
        normalized = url.strip()
        if normalized and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)
    set_json_setting(db, KNOWLEDGE_URLS_KEY, {"urls": cleaned})


def get_sync_cursor(db: Session) -> int:
    value = get_json_setting(db, HERMES_SYNC_CURSOR_KEY, {"last_message_id": 0})
    return int(value.get("last_message_id") or 0)


def set_sync_cursor(db: Session, last_message_id: int) -> None:
    set_json_setting(db, HERMES_SYNC_CURSOR_KEY, {"last_message_id": int(last_message_id)})

