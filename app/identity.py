import hashlib


def make_user_id(platform: str, bot_id: str, external_user_id: str) -> str:
    raw = f"{platform.strip().lower()}:{bot_id.strip()}:{external_user_id.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

