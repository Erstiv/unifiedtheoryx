"""Routes — Pipeline execution, status polling, tangent approval, and review."""
import json
import threading
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.templating import templates
from app.models import (
    Topic, TopicStatus, PipelineRun, AgentRun, AgentName, RunStatus,
)
from app.pipeline.runner import (
    create_phase_run, execute_phase, run_tangent_research,
    get_pipeline_status, rerun_single_agent,
)

router = APIRouter()


def _run_phase_background(pipeline_run_id: int):
    """Execute a phase in a background thread."""
    db = SessionLocal()
    try:
        execute_phase(db, pipeline_run_id)
    except Exception as e:
        import logging
        logging.getLogger("unified_theory").error(f"Phase execution failed: {e}")
    finally:
        db.close()


def _run_tangent_background(topic_id: int):
    """Execute tangent research in a background thread."""
    db = SessionLocal()
    try:
        run_tangent_research(db, topic_id)
    except Exception as e:
        import logging
        logging.getLogger("unified_theory").error(f"Tangent research failed: {e}")
    finally:
        db.close()


@router.post("/topic/{topic_id}/run-phase/{phase}")
async def start_phase(topic_id: int, phase: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Topic not found"}, status_code=404)

    pipeline_run = create_phase_run(db, topic_id, phase)
    threading.Thread(
        target=_run_phase_background,
        args=(pipeline_run.id,),
        daemon=True,
    ).start()

    return RedirectResponse(f"/topic/{topic_id}/run/{pipeline_run.id}", status_code=303)


@router.get("/topic/{topic_id}/run/{run_id}", response_class=HTMLResponse)
async def run_status_page(request: Request, topic_id: int, run_id: int,
                          db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not topic or not pipeline_run:
        return HTMLResponse("Not found", status_code=404)

    return templates.TemplateResponse(request, "topic/run_status.html", {
        "topic": topic, "run": pipeline_run,
    })


@router.get("/api/topic/{topic_id}/run/{run_id}/status")
async def run_status_api(topic_id: int, run_id: int, db: Session = Depends(get_db)):
    status = get_pipeline_status(db, run_id)
    if not status:
        return JSONResponse({"error": "Not found"}, status_code=404)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    status["topic_status"] = topic.status.value if topic else None
    return JSONResponse(status)


@router.get("/topic/{topic_id}/review-outline", response_class=HTMLResponse)
async def review_outline(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Review research results and select tangents."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    # Get Phase 1 agent outputs
    research_output = None
    tangent_output = None
    tangent_research_output = None

    for run in topic.pipeline_runs:
        for ar in run.agent_runs:
            if ar.agent_name == AgentName.DEEP_RESEARCHER and ar.output_json:
                research_output = ar.output_json
            if ar.agent_name == AgentName.TANGENT_FINDER and ar.output_json:
                tangent_output = ar.output_json
            if ar.agent_name == AgentName.TANGENT_RESEARCHER and ar.output_json:
                tangent_research_output = ar.output_json

    tangents = tangent_output.get("tangents", []) if tangent_output else []
    tangents_researched = topic.status != TopicStatus.PAUSED_PHASE_1 or tangent_research_output is not None

    return templates.TemplateResponse(request, "topic/review_outline.html", {
        "topic": topic,
        "research": research_output,
        "tangents": tangents,
        "tangent_research": tangent_research_output,
        "tangents_researched": tangent_research_output is not None,
        "phase2_ready": tangent_research_output is not None or topic.approved_tangents == [],
    })


@router.post("/topic/{topic_id}/approve-tangents")
async def approve_tangents(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Approve selected tangents and trigger tangent research."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Topic not found"}, status_code=404)

    form = await request.form()
    selected_indices = form.getlist("tangent_indices")

    # Get the tangent proposals
    tangent_output = None
    for run in topic.pipeline_runs:
        for ar in run.agent_runs:
            if ar.agent_name == AgentName.TANGENT_FINDER and ar.output_json:
                tangent_output = ar.output_json
                break

    if not tangent_output:
        return JSONResponse({"error": "No tangent proposals found"}, status_code=400)

    all_tangents = tangent_output.get("tangents", [])
    approved = []
    for idx in selected_indices:
        i = int(idx)
        if 0 <= i < len(all_tangents):
            tangent = all_tangents[i]
            depth = form.get(f"depth_{i}", tangent.get("suggested_depth", "paragraph"))
            approved.append({
                "title": tangent["title"],
                "depth": depth,
                "description": tangent.get("hook", ""),
            })

    topic.approved_tangents = approved
    db.commit()

    if approved:
        # Run tangent research in background
        threading.Thread(
            target=_run_tangent_background,
            args=(topic_id,),
            daemon=True,
        ).start()
        return RedirectResponse(f"/topic/{topic_id}/tangent-progress", status_code=303)
    else:
        # No tangents selected — skip straight to Phase 2 readiness
        topic.approved_tangents = []
        db.commit()
        return RedirectResponse(f"/topic/{topic_id}/review-outline", status_code=303)


@router.get("/topic/{topic_id}/tangent-progress", response_class=HTMLResponse)
async def tangent_progress(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Show loading spinner while tangent research runs."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)
    return templates.TemplateResponse(request, "topic/tangent_progress.html", {
        "topic": topic,
    })


@router.get("/api/topic/{topic_id}/tangent-status")
async def tangent_status_api(topic_id: int, db: Session = Depends(get_db)):
    """Check if tangent research is done."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Not found"}, status_code=404)

    # Check if tangent researcher has completed
    done = False
    for run in topic.pipeline_runs:
        for ar in run.agent_runs:
            if ar.agent_name == AgentName.TANGENT_RESEARCHER and ar.output_json:
                done = True
    return JSONResponse({"done": done, "status": topic.status.value})


@router.get("/topic/{topic_id}/review-drafts", response_class=HTMLResponse)
async def review_drafts(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Review paper and script drafts side by side."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    paper_output = None
    script_output = None
    title_output = None

    for run in topic.pipeline_runs:
        for ar in run.agent_runs:
            if ar.agent_name == AgentName.PAPER_WRITER and ar.output_json:
                paper_output = ar.output_json
            if ar.agent_name == AgentName.SCRIPT_WRITER and ar.output_json:
                script_output = ar.output_json
            if ar.agent_name == AgentName.TITLE_HOOK and ar.output_json:
                title_output = ar.output_json

    return templates.TemplateResponse(request, "topic/review_drafts.html", {
        "topic": topic,
        "paper": paper_output,
        "script": script_output,
        "title_data": title_output,
    })


@router.post("/topic/{topic_id}/approve-drafts")
async def approve_drafts(topic_id: int, db: Session = Depends(get_db)):
    """Approve drafts and start Phase 3."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Topic not found"}, status_code=404)

    pipeline_run = create_phase_run(db, topic_id, 3)
    threading.Thread(
        target=_run_phase_background,
        args=(pipeline_run.id,),
        daemon=True,
    ).start()

    return RedirectResponse(f"/topic/{topic_id}/run/{pipeline_run.id}", status_code=303)


@router.post("/topic/{topic_id}/rerun/{run_id}/{agent_name}")
async def rerun_agent(
    topic_id: int, run_id: int, agent_name: str,
    guidance: str = Form(""),
    db: Session = Depends(get_db),
):
    """Rerun a single agent with optional guidance."""
    try:
        agent_enum = AgentName(agent_name)
    except ValueError:
        return JSONResponse({"error": f"Unknown agent: {agent_name}"}, status_code=400)

    def _rerun_bg():
        _db = SessionLocal()
        try:
            rerun_single_agent(_db, run_id, agent_enum, guidance or None)
        except Exception as e:
            import logging
            logging.getLogger("unified_theory").error(f"Rerun failed: {e}")
        finally:
            _db.close()

    threading.Thread(target=_rerun_bg, daemon=True).start()
    return RedirectResponse(f"/topic/{topic_id}", status_code=303)
