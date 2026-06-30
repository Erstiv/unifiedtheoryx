"""The Grand Unified Theory of X — Etymology, Neuroscience, Culture, and Everything In Between"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from app.database import init_db, SessionLocal
from app.config import SESSION_SECRET
from app.models import BibleEntry, BibleScope, PipelineRun, Topic, RunStatus, TopicStatus  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("unified_theory")


def _cleanup_stuck_runs():
    """On startup, mark any RUNNING pipeline runs/agent_runs as FAILED (they died mid-flight)."""
    from app.models import AgentRun
    db = SessionLocal()
    try:
        count = 0
        # Fix stuck pipeline runs
        stuck_runs = db.query(PipelineRun).filter(PipelineRun.status == RunStatus.RUNNING).all()
        for run in stuck_runs:
            run.status = RunStatus.FAILED
            run.error_message = "Server restarted while this run was in progress."
            topic = db.query(Topic).filter(Topic.id == run.topic_id).first()
            if topic and topic.status == TopicStatus.RUNNING:
                topic.status = TopicStatus.PAUSED_PHASE_1 if run.phase == 1 else TopicStatus.PAUSED_PHASE_2
            count += 1

        # Also fix orphaned RUNNING agent_runs inside already-failed pipeline runs
        stuck_agents = db.query(AgentRun).filter(AgentRun.status == RunStatus.RUNNING).all()
        for ar in stuck_agents:
            ar.status = RunStatus.FAILED
            ar.error_message = "Server restarted while this agent was running."
            count += 1

        if count:
            db.commit()
            logger.warning(f"Cleaned up {count} stuck run(s) from previous session.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    _seed_knowledge_base()
    _cleanup_stuck_runs()
    logger.info("The Grand Unified Theory of X is ready.")
    yield


app = FastAPI(title="The Grand Unified Theory of X", version="0.1.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

from app.routes.auth import router as auth_router
app.include_router(auth_router)

from app.routes.topics import router as topics_router
app.include_router(topics_router)

from app.routes.pipeline import router as pipeline_router
app.include_router(pipeline_router)

from app.routes.episodes import router as episodes_router
app.include_router(episodes_router)

from app.routes.export import router as export_router
app.include_router(export_router)

from app.routes.bible import router as bible_router
app.include_router(bible_router)


def _seed_knowledge_base():
    """Load voice & style seed data if the global knowledge base is empty."""
    db = SessionLocal()
    try:
        count = db.query(BibleEntry).filter(BibleEntry.scope == BibleScope.GLOBAL).count()
        if count > 0:
            logger.info(f"Knowledge base already has {count} global entries, skipping seed.")
            return

        import json
        seed_path = Path(__file__).parent.parent / "bible_seed" / "seed_data.json"
        if not seed_path.exists():
            logger.warning("No seed_data.json found, skipping knowledge base seed.")
            return

        with open(seed_path) as f:
            seed_data = json.load(f)

        from app.models import BibleCategory
        for entry in seed_data:
            try:
                cat = BibleCategory(entry["category"])
            except ValueError:
                logger.warning(f"Unknown category: {entry['category']}, skipping.")
                continue

            be = BibleEntry(
                scope=BibleScope.GLOBAL,
                topic_id=None,
                category=cat,
                title=entry["title"],
                content=entry["content"],
                entry_data=entry.get("entry_data"),
                source="seed",
            )
            db.add(be)

        db.commit()
        logger.info(f"Seeded knowledge base with {len(seed_data)} entries.")
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    from app.config import APP_HOST, APP_PORT
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)
