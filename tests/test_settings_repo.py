from app.settings_repo import get_knowledge_urls, set_knowledge_urls


def test_knowledge_urls_are_cleaned_and_deduplicated(db) -> None:
    set_knowledge_urls(db, [" https://example.feishu.cn/wiki/a ", "", "https://example.feishu.cn/wiki/a", "https://b"])
    db.commit()

    assert get_knowledge_urls(db) == ["https://example.feishu.cn/wiki/a", "https://b"]

