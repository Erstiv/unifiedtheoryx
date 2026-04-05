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

    # Handle custom tangents from danger mode
    custom_count_str = form.get("custom_tangent_count", "0")
    try:
        custom_count = int(custom_count_str)
    except (ValueError, TypeError):
        custom_count = 0
    for ci in range(custom_count):
        title = form.get(f"custom_tangent_title_{ci}", "").strip()
        if title:
            approved.append({
                "title": title,
                "depth": form.get(f"custom_tangent_depth_{ci}", "paragraph"),
                "description": form.get(f"custom_tangent_desc_{ci}", ""),
                "custom": True,
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


@router.get("/topic/{topic_id}/review-tangent-research", response_class=HTMLResponse)
async def review_tangent_research(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Danger mode: review detailed tangent research with editing."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)

    tangent_research_output = None
    for run in topic.pipeline_runs:
        for ar in run.agent_runs:
            if ar.agent_name == AgentName.TANGENT_RESEARCHER and ar.output_json:
                tangent_research_output = ar.output_json

    return templates.TemplateResponse(request, "topic/review_tangent_research.html", {
        "topic": topic,
        "tangent_research": tangent_research_output,
    })


@router.post("/topic/{topic_id}/save-tangent-edits")
async def save_tangent_edits(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Save user edits to tangent research (danger mode)."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Not found"}, status_code=404)

    form = await request.form()
    action = form.get("action", "save")

    try:
        tangent_count = int(form.get("tangent_count", "0"))
    except (ValueError, TypeError):
        tangent_count = 0

    edited_tangents = []
    for i in range(tangent_count):
        edited_tangents.append({
            "key_facts": form.get(f"tangent_{i}_key_facts", "").split("\n"),
            "connection_to_main": form.get(f"tangent_{i}_connection", ""),
            "contrast_with_main": form.get(f"tangent_{i}_contrast", ""),
            "best_anecdote": form.get(f"tangent_{i}_anecdote", ""),
            "neuroscience_angle": form.get(f"tangent_{i}_neuro", ""),
            "sources": [s.strip() for s in form.get(f"tangent_{i}_sources", "").split("\n") if s.strip()],
        })

    edits = topic.danger_mode_edits or {}
    edits["tangent_research"] = edited_tangents
    topic.danger_mode_edits = edits
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(topic, "danger_mode_edits")
    db.commit()

    if action == "approve":
        # Start Phase 2
        pipeline_run = create_phase_run(db, topic_id, 2)
        threading.Thread(target=_run_phase_background, args=(pipeline_run.id,), daemon=True).start()
        return RedirectResponse(f"/topic/{topic_id}/run/{pipeline_run.id}", status_code=303)

    return RedirectResponse(f"/topic/{topic_id}/review-tangent-research", status_code=303)


@router.post("/topic/{topic_id}/rerun-tangent-research")
async def rerun_tangent_research_route(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Rerun tangent research with user guidance (danger mode)."""
    form = await request.form()
    guidance = form.get("guidance", "")

    # Set the topic back to tangent research state
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Not found"}, status_code=404)

    def _rerun_bg():
        _db = SessionLocal()
        try:
            run_tangent_research(_db, topic_id)
        except Exception as e:
            import logging
            logging.getLogger("unified_theory").error(f"Tangent rerun failed: {e}")
        finally:
            _db.close()

    threading.Thread(target=_rerun_bg, daemon=True).start()
    return RedirectResponse(f"/topic/{topic_id}/tangent-progress", status_code=303)


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
async def approve_drafts(request: Request, topic_id: int, db: Session = Depends(get_db)):
    """Approve drafts and start Phase 3."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return JSONResponse({"error": "Topic not found"}, status_code=404)

    # Check if danger mode edits were submitted
    danger_mode = request.session.get("danger_mode", False) if hasattr(request, "session") else False
    if danger_mode:
        form = await request.form()
        edits = topic.danger_mode_edits or {}
        edits["paper"] = form.get("paper_content", "")
        edits["script"] = form.get("script_content", "")
        edits["title"] = form.get("edit_title", "")
        edits["subtitle"] = form.get("edit_subtitle", "")
        edits["cold_open"] = form.get("edit_cold_open", "")
        edits["expert_name"] = form.get("expert_name", "")
        edits["expert_title"] = form.get("expert_title", "")
        edits["expert_personality"] = form.get("expert_personality", "")
        edits["everybody_name"] = form.get("everybody_name", "")
        edits["everybody_relationship"] = form.get("everybody_relationship", "")
        edits["everybody_personality"] = form.get("everybody_personality", "")
        # Social hooks
        hook_count = int(form.get("social_hook_count", "0"))
        hooks = []
        for i in range(hook_count):
            platform = form.get(f"hook_platform_{i}", "")
            text = form.get(f"hook_text_{i}", "")
            if text.strip():
                hooks.append({"platform": platform, "text": text})
        if hooks:
            edits["social_hooks"] = hooks
        topic.danger_mode_edits = edits
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(topic, "danger_mode_edits")
        db.commit()

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
