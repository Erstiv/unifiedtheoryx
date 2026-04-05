"""Routes — Topic CRUD and backlog management."""
import re
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Topic, TopicStatus
from app.templating import templates
from app.auth import is_admin

router = APIRouter()


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:100]


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    topics = db.query(Topic).order_by(Topic.created_at.desc()).limit(20).all()
    stats = {
        "total": db.query(Topic).count(),
        "completed": db.query(Topic).filter(Topic.status == TopicStatus.COMPLETED).count(),
        "in_progress": db.query(Topic).filter(Topic.status.in_([
            TopicStatus.RUNNING, TopicStatus.PAUSED_PHASE_1,
            TopicStatus.PAUSED_TANGENTS, TopicStatus.PAUSED_PHASE_2
        ])).count(),
    }
    return templates.TemplateResponse(request, "dashboard.html", {
        "topics": topics, "stats": stats
    })


@router.get("/topic/new", response_class=HTMLResponse)
async def new_topic_form(request: Request):
    return templates.TemplateResponse(request, "topic/new.html")


@router.post("/topic/new")
async def create_topic(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    page_count: int = Form(2),
    script_minutes: int = Form(10),
    narrator_count: int = Form(1),
    db: Session = Depends(get_db),
):
    slug = _slugify(title)
    existing = db.query(Topic).filter(Topic.slug == slug).first()
    if existing:
        slug = f"{slug}-{db.query(Topic).count() + 1}"

    topic = Topic(
        title=title,
        slug=slug,
        description=description if description else None,
        page_count=max(1, min(3, page_count)),
        script_minutes=max(8, min(12, script_minutes)),
        narrator_count=max(1, min(3, narrator_count)),
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    return RedirectResponse(f"/topic/{topic.id}", status_code=303)


@router.get("/topic/{topic_id}", response_class=HTMLResponse)
async def topic_overview(request: Request, topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    return templates.TemplateResponse(request, "topic/overview.html", {
        "topic": topic
    })


@router.get("/backlog", response_class=HTMLResponse)
async def backlog(request: Request, db: Session = Depends(get_db)):
    topics = db.query(Topic).order_by(Topic.created_at.desc()).all()
    return templates.TemplateResponse(request, "backlog.html", {
        "topics": topics
    })


@router.post("/topic/{topic_id}/delete")
async def delete_topic(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Delete a topic and all related data (admin only)."""
    if not is_admin(request):
        return RedirectResponse("/login", status_code=303)
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    # Delete related records
    from app.models import PipelineRun, AgentRun, Episode, OutputDocument, BibleEntry, BibleScope
    for run in topic.pipeline_runs:
        db.query(AgentRun).filter(AgentRun.pipeline_run_id == run.id).delete()
    db.query(PipelineRun).filter(PipelineRun.topic_id == topic_id).delete()
    db.query(Episode).filter(Episode.topic_id == topic_id).delete()
    db.query(OutputDocument).filter(OutputDocument.topic_id == topic_id).delete()
    db.query(BibleEntry).filter(BibleEntry.topic_id == topic_id, BibleEntry.scope == BibleScope.TOPIC).delete()
    db.delete(topic)
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/topic/{topic_id}/add-idea")
async def add_idea(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """Quick-add a topic idea to the backlog."""
    slug = _slugify(title)
    existing = db.query(Topic).filter(Topic.slug == slug).first()
    if existing:
        slug = f"{slug}-{db.query(Topic).count() + 1}"

    topic = Topic(title=title, slug=slug, description=description or None)
    db.add(topic)
    db.commit()
    return RedirectResponse("/backlog", status_code=303)
