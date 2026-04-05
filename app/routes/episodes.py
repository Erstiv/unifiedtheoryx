"""Routes — Episode viewing."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Topic, Episode
from app.templating import templates

router = APIRouter()


@router.get("/topic/{topic_id}/episode", response_class=HTMLResponse)
async def view_episode(request: Request, topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    episode = db.query(Episode).filter(Episode.topic_id == topic_id).first()
    if not episode:
        return HTMLResponse("Episode not ready yet", status_code=404)

    return templates.TemplateResponse(request, "topic/episode.html", {
        "topic": topic,
        "episode": episode,
    })
