from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .analysis import analyze_user
from .config import get_settings
from .constants import CUSTOMER_STAGE_LABELS, CUSTOMER_STAGES
from .dashboard import get_dashboard_data, get_workbench_data
from .database import get_db
from .events import change_customer_stage
from .marketing import generate_xiaohongshu_asset, get_recent_marketing_assets
from .models import CustomerEvent, MarketingAsset, Message, RoutingRule, User
from .routing import get_action_suggestion, get_routing_rules, update_routing_rule
from .settings_repo import get_knowledge_urls, set_knowledge_urls
from .strategy_agent import answer_strategy_question

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def format_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


templates.env.filters["datetime"] = format_dt
templates.env.globals["stage_label"] = lambda stage: CUSTOMER_STAGE_LABELS.get(stage, stage)


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/admin/workbench", status_code=303)


@router.get("/admin/workbench", response_class=HTMLResponse)
def workbench(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    data = get_workbench_data(db)
    return templates.TemplateResponse(
        request,
        "admin/workbench.html",
        {
            "data": data,
            "settings": get_settings(),
            "stages": CUSTOMER_STAGES,
        },
    )


@router.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, answer: str = "", question: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "data": get_dashboard_data(db),
            "answer": answer,
            "question": question,
            "settings": get_settings(),
        },
    )


@router.post("/admin/dashboard/ask")
def dashboard_ask(question: str = Form(default=""), db: Session = Depends(get_db)) -> RedirectResponse:
    answer = answer_strategy_question(db, get_settings(), question.strip() or "本周经营情况如何？")
    return RedirectResponse(
        f"/admin/dashboard?question={url_quote(question)}&answer={url_quote(answer)}",
        status_code=303,
    )


@router.get("/admin/marketing", response_class=HTMLResponse)
def marketing(request: Request, asset_id: int | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    assets = get_recent_marketing_assets(db)
    selected = db.get(MarketingAsset, asset_id) if asset_id else (assets[0] if assets else None)
    return templates.TemplateResponse(
        request,
        "admin/marketing.html",
        {
            "assets": assets,
            "selected": selected,
            "settings": get_settings(),
        },
    )


@router.post("/admin/marketing/generate")
def marketing_generate(
    topic: str = Form(...),
    audience: str = Form(default=""),
    goal: str = Form(default=""),
    tone: str = Form(default=""),
    source_context: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")
    asset = generate_xiaohongshu_asset(
        db,
        get_settings(),
        topic=topic,
        audience=audience,
        goal=goal,
        tone=tone,
        source_context=source_context,
    )
    db.commit()
    db.refresh(asset)
    return RedirectResponse(f"/admin/marketing?asset_id={asset.id}", status_code=303)


@router.get("/admin/users", response_class=HTMLResponse)
def users(
    request: Request,
    q: str = Query(default=""),
    stage: str = Query(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    settings = get_settings()
    stmt = (
        select(User)
        .options(selectinload(User.profile), selectinload(User.tags))
        .order_by(User.last_message_at.desc().nullslast(), User.first_seen_at.desc())
        .limit(settings.admin_page_size)
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.external_user_id.ilike(pattern), User.display_name.ilike(pattern)))
    if stage:
        stmt = stmt.where(User.customer_stage == stage)

    users_list = list(db.scalars(stmt))
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "users": users_list,
            "q": q,
            "stage": stage,
            "stages": CUSTOMER_STAGES,
            "settings": settings,
        },
    )


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    user = db.scalar(
        select(User).options(selectinload(User.profile), selectinload(User.tags)).where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(500)
        )
    )
    events = list(
        db.scalars(
            select(CustomerEvent)
            .where(CustomerEvent.user_id == user_id)
            .order_by(CustomerEvent.created_at.desc(), CustomerEvent.id.desc())
            .limit(50)
        )
    )
    return templates.TemplateResponse(
        request,
        "admin/user_detail.html",
        {
            "user": user,
            "messages": messages,
            "events": events,
            "stages": CUSTOMER_STAGES,
            "suggestion": get_action_suggestion(db, user),
            "settings": get_settings(),
        },
    )


@router.post("/admin/users/{user_id}/analyze")
def analyze_user_endpoint(user_id: str, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        analyze_user(db, get_settings(), user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(f"/admin/users/{user_id}?analyzed=1", status_code=303)


@router.post("/admin/users/{user_id}/stage")
def update_user_stage(
    user_id: str,
    customer_stage: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if customer_stage not in CUSTOMER_STAGES:
        raise HTTPException(status_code=400, detail="Invalid customer stage")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    change_customer_stage(db, user, customer_stage, actor="employee")
    db.commit()
    return RedirectResponse(f"/admin/users/{user_id}?stage_updated=1", status_code=303)


@router.get("/admin/rules", response_class=HTMLResponse)
def rules(request: Request, saved: int = 0, db: Session = Depends(get_db)) -> HTMLResponse:
    rules_list = get_routing_rules(db)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin/rules.html",
        {
            "rules": rules_list,
            "saved": bool(saved),
            "settings": get_settings(),
            "stages": CUSTOMER_STAGES,
        },
    )


@router.post("/admin/rules/{rule_id}")
def update_rule(
    rule_id: int,
    enabled: str | None = Form(default=None),
    target: str = Form(default=""),
    message: str = Form(default=""),
    priority: int = Form(default=100),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    rule = db.get(RoutingRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    update_routing_rule(db, rule, enabled=enabled == "on", target=target, message=message, priority=priority)
    db.commit()
    return RedirectResponse("/admin/rules?saved=1", status_code=303)


@router.get("/admin/settings/knowledge", response_class=HTMLResponse)
def knowledge_settings(request: Request, saved: int = 0, db: Session = Depends(get_db)) -> HTMLResponse:
    urls = get_knowledge_urls(db)
    return templates.TemplateResponse(
        request,
        "admin/knowledge.html",
        {
            "urls_text": "\n".join(urls),
            "saved": bool(saved),
            "settings": get_settings(),
        },
    )


@router.post("/admin/settings/knowledge")
def update_knowledge_settings(
    urls_text: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
    set_knowledge_urls(db, urls)
    db.commit()
    return RedirectResponse("/admin/settings/knowledge?saved=1", status_code=303)


def url_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value or "", safe="")
