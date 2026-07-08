from sqlalchemy import select

from app.config import get_settings
from app.marketing import generate_xiaohongshu_asset
from app.models import MarketingAsset


def test_generate_xiaohongshu_asset_fallback_persists(db) -> None:
    asset = generate_xiaohongshu_asset(
        db,
        get_settings(),
        topic="AI客户经营公开课",
        audience="小微企业老板",
        goal="引导咨询和报名",
        tone="真实、清爽、有行动感",
        source_context="分享客户接待、分层、分流和老板看板。",
    )
    db.commit()

    saved = db.scalar(select(MarketingAsset).where(MarketingAsset.id == asset.id))
    assert saved is not None
    assert saved.channel == "xiaohongshu"
    assert len(saved.result["title_options"]) >= 3
    assert saved.result["slides"]
    assert "#AI工具" in saved.result["hashtags"]

