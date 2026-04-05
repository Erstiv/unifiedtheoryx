from __future__ import annotations
"""
Pipeline Runner — phase-gated orchestration for The Grand Unified Theory of X.

Pipeline flow:
  Phase 1: Deep Researcher → Tangent Finder → PAUSE (user selects tangents)
           → Tangent Researcher (approved tangents only) → Phase 2 unlocks
  Phase 2: Paper Writer → Script Writer → Title & Hook → PAUSE (user reviews)
  Phase 3: Editor → Show Notes → COMPLETE (episode created)
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import (
    PipelineRun, AgentRun, AgentName, RunStatus, Topic, TopicStatus,
    PHASE_AGENTS, Episode, EpisodeStatus,
)

logger = logging.getLogger("unified_theory.runner")

_AGENT_CLASS_MAP = None


def _get_agent_class_map():
    global _AGENT_CLASS_MAP
    if _AGENT_CLASS_MAP is None:
        _AGENT_CLASS_MAP = {}
        agent_imports = {
            AgentName.DEEP_RESEARCHER: ("app.agents.deep_researcher", "DeepResearcherAgent"),
            AgentName.TANGENT_FINDER: ("app.agents.tangent_finder", "TangentFinderAgent"),
            AgentName.TANGENT_RESEARCHER: ("app.agents.tangent_researcher", "TangentResearcherAgent"),
            AgentName.PAPER_WRITER: ("app.agents.paper_writer", "PaperWriterAgent"),
            AgentName.SCRIPT_WRITER: ("app.agents.script_writer", "ScriptWriterAgent"),
            AgentName.TITLE_HOOK: ("app.agents.title_hook", "TitleHookAgent"),
            AgentName.EDITOR: ("app.agents.editor", "EditorAgent"),
            AgentName.SHOW_NOTES: ("app.agents.show_notes", "ShowNotesAgent"),
        }
        for agent_name, (module_path, class_name) in agent_imports.items():
            try:
                import importlib
                mod = importlib.import_module(module_path)
                _AGENT_CLASS_MAP[agent_name] = getattr(mod, class_name)
            except (ImportError, AttributeError):
                pass
    return _AGENT_CLASS_MAP


def create_phase_run(db: Session, topic_id: int, phase: int) -> PipelineRun:
    """Create a pipeline run for a specific phase."""
    agents = PHASE_AGENTS.get(phase, [])
    if not agents:
        raise ValueError(f"Invalid phase: {phase}")

    pipeline_run = PipelineRun(
        topic_id=topic_id,
        phase=phase,
        status=RunStatus.PENDING,
        agents_to_run=[a.value for a in agents],
    )
    db.add(pipeline_run)
    db.flush()

    for i, agent_name in enumerate(agents):
        agent_run = AgentRun(
            pipeline_run_id=pipeline_run.id,
            agent_name=agent_name,
            sequence_order=i,
            status=RunStatus.PENDING,
        )
        db.add(agent_run)

    db.commit()
    db.refresh(pipeline_run)
    return pipeline_run


def execute_phase(db: Session, pipeline_run_id: int):
    """Execute all agents in a phase run sequentially."""
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
    if not pipeline_run:
        raise ValueError(f"PipelineRun {pipeline_run_id} not found")

    pipeline_run.status = RunStatus.RUNNING
    pipeline_run.started_at = datetime.now(timezone.utc)
    db.commit()

    topic = db.query(Topic).filter(Topic.id == pipeline_run.topic_id).first()
    topic.current_phase = pipeline_run.phase
    topic.status = TopicStatus.RUNNING
    db.commit()

    prior_outputs = _gather_prior_outputs(db, pipeline_run.topic_id, pipeline_run.phase)
    agent_class_map = _get_agent_class_map()

    # Danger mode: override prior outputs with user edits for Phase 3
    if pipeline_run.phase == 3 and topic.danger_mode_edits:
        edits = topic.danger_mode_edits
        if edits.get("paper") and "paper_writer" in prior_outputs:
            prior_outputs["paper_writer"]["paper"] = edits["paper"]
        if edits.get("script") and "script_writer" in prior_outputs:
            prior_outputs["script_writer"]["script"] = edits["script"]
        if "title_hook" in prior_outputs:
            if edits.get("title"):
                prior_outputs["title_hook"]["title"] = edits["title"]
            if edits.get("subtitle"):
                prior_outputs["title_hook"]["subtitle"] = edits["subtitle"]
            if edits.get("cold_open"):
                prior_outputs["title_hook"]["cold_open"] = edits["cold_open"]
            if edits.get("social_hooks"):
                prior_outputs["title_hook"]["social_hooks"] = edits["social_hooks"]
        logger.info("Danger mode: injected user edits into Phase 3 context")

    try:
        for agent_run in pipeline_run.agent_runs:
            agent_class = agent_class_map.get(agent_run.agent_name)
            if not agent_class:
                logger.error(f"No agent class for {agent_run.agent_name}")
                agent_run.status = RunStatus.FAILED
                agent_run.error_message = f"Agent class not implemented: {agent_run.agent_name.value}"
                db.commit()
                continue

            logger.info(f"Running agent: {agent_run.agent_name.value} (Phase {pipeline_run.phase})")
            agent = agent_class(db=db, topic_id=pipeline_run.topic_id, agent_run=agent_run)
            output = agent.run(prior_outputs)
            prior_outputs[agent_run.agent_name.value] = output
            logger.info(f"Agent {agent_run.agent_name.value} completed. Tokens: {agent_run.total_tokens}, Cost: ${agent_run.cost_usd:.4f}")

        # Phase complete — determine next state
        if pipeline_run.phase == 1:
            pipeline_run.status = RunStatus.PAUSED_FOR_REVIEW
            topic.status = TopicStatus.PAUSED_PHASE_1
        elif pipeline_run.phase == 2:
            pipeline_run.status = RunStatus.PAUSED_FOR_REVIEW
            topic.status = TopicStatus.PAUSED_PHASE_2
        else:
            pipeline_run.status = RunStatus.COMPLETED
            topic.status = TopicStatus.COMPLETED
            _create_episode(db, topic, prior_outputs)

        pipeline_run.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Phase {pipeline_run.phase} {'completed' if pipeline_run.phase == 3 else 'paused for review'}.")
        return prior_outputs

    except Exception as e:
        logger.error(f"Phase {pipeline_run.phase} failed: {e}")
        pipeline_run.status = RunStatus.FAILED
        pipeline_run.error_message = str(e)
        pipeline_run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise


def run_tangent_research(db: Session, topic_id: int):
    """Run the Tangent Researcher for approved tangents (between Phase 1 and Phase 2)."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic or not topic.approved_tangents:
        raise ValueError("No approved tangents to research")

    topic.status = TopicStatus.PAUSED_TANGENTS
    db.commit()

    # Create a special pipeline run for tangent research
    pipeline_run = PipelineRun(
        topic_id=topic_id,
        phase=1,  # Still phase 1 conceptually
        status=RunStatus.RUNNING,
        agents_to_run=["tangent_researcher"],
        started_at=datetime.now(timezone.utc),
    )
    db.add(pipeline_run)
    db.flush()

    agent_run = AgentRun(
        pipeline_run_id=pipeline_run.id,
        agent_name=AgentName.TANGENT_RESEARCHER,
        sequence_order=0,
        status=RunStatus.PENDING,
    )
    db.add(agent_run)
    db.commit()

    prior_outputs = _gather_prior_outputs(db, topic_id, 2)  # Get all phase 1 outputs
    agent_class_map = _get_agent_class_map()
    agent_class = agent_class_map.get(AgentName.TANGENT_RESEARCHER)

    if not agent_class:
        raise ValueError("TangentResearcherAgent not implemented")

    logger.info(f"Running tangent research for topic '{topic.title}' ({len(topic.approved_tangents)} tangents)")
    agent = agent_class(db=db, topic_id=topic_id, agent_run=agent_run)
    output = agent.run(prior_outputs)

    pipeline_run.status = RunStatus.COMPLETED
    pipeline_run.completed_at = datetime.now(timezone.utc)
    topic.status = TopicStatus.PAUSED_PHASE_1  # Back to review state, Phase 2 now available
    db.commit()

    logger.info("Tangent research completed.")
    return output


def _create_episode(db: Session, topic: Topic, prior_outputs: dict):
    """Create the Episode record from Phase 3 outputs."""
    editor_output = prior_outputs.get("editor", {})
    show_notes_output = prior_outputs.get("show_notes", {})
    title_output = prior_outputs.get("title_hook", {})

    episode = db.query(Episode).filter(Episode.topic_id == topic.id).first()
    if not episode:
        episode = Episode(topic_id=topic.id)
        db.add(episode)

    episode.title = title_output.get("title", topic.title)
    episode.subtitle = title_output.get("subtitle", "")
    episode.cold_open = title_output.get("cold_open", "")
    episode.paper_content = editor_output.get("paper", "")
    episode.script_content = editor_output.get("script", "")
    episode.seo_title = show_notes_output.get("seo_title", "")
    episode.seo_description = show_notes_output.get("seo_description", "")
    episode.seo_keywords = show_notes_output.get("seo_keywords", [])
    episode.social_snippets = show_notes_output.get("social_snippets", [])
    episode.show_notes = show_notes_output.get("show_notes", "")
    episode.citations_appendix = editor_output.get("citations_appendix", "")

    # Apply danger mode title/subtitle/cold_open edits if they exist
    edits = topic.danger_mode_edits or {}
    if edits.get("title"):
        episode.title = edits["title"]
    if edits.get("subtitle"):
        episode.subtitle = edits["subtitle"]
    if edits.get("cold_open"):
        episode.cold_open = edits["cold_open"]
    if edits.get("social_hooks"):
        episode.social_snippets = edits["social_hooks"]
    episode.status = EpisodeStatus.READY
    db.commit()


def _gather_prior_outputs(db: Session, topic_id: int, current_phase: int) -> dict[str, dict]:
    """Gather all completed agent outputs from previous phases."""
    prior_outputs = {}
    previous_runs = db.query(PipelineRun).filter(
        PipelineRun.topic_id == topic_id,
        PipelineRun.phase < current_phase,
        PipelineRun.status.in_([RunStatus.COMPLETED, RunStatus.PAUSED_FOR_REVIEW]),
    ).all()

    for run in previous_runs:
        for ar in run.agent_runs:
            if ar.status == RunStatus.COMPLETED and ar.output_json:
                prior_outputs[ar.agent_name.value] = ar.output_json

    # Also gather from current phase completed agents (for tangent researcher)
    if current_phase == 2:
        current_runs = db.query(PipelineRun).filter(
            PipelineRun.topic_id == topic_id,
            PipelineRun.phase == 1,
        ).all()
        for run in current_runs:
            for ar in run.agent_runs:
                if ar.status == RunStatus.COMPLETED and ar.output_json:
                    prior_outputs[ar.agent_name.value] = ar.output_json

    return prior_outputs


def rerun_single_agent(db: Session, pipeline_run_id: int, agent_name: AgentName,
                       guidance: str = None):
    """Re-execute a single agent within an existing pipeline run."""
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
    if not pipeline_run:
        raise ValueError(f"PipelineRun {pipeline_run_id} not found")

    target = None
    for ar in pipeline_run.agent_runs:
        if ar.agent_name == agent_name:
            target = ar
            break
    if not target:
        raise ValueError(f"Agent {agent_name.value} not in PipelineRun {pipeline_run_id}")

    target.status = RunStatus.PENDING
    target.output_json = None
    target.output_raw = None
    target.error_message = None
    target.input_prompt = None
    target.input_tokens = 0
    target.output_tokens = 0
    target.total_tokens = 0
    target.cost_usd = 0.0
    target.started_at = None
    target.completed_at = None
    target.model_used = None
    target.rerun_guidance = guidance
    db.commit()

    prior_outputs = _gather_prior_outputs(db, pipeline_run.topic_id, pipeline_run.phase)
    for ar in pipeline_run.agent_runs:
        if ar.sequence_order < target.sequence_order and ar.status == RunStatus.COMPLETED and ar.output_json:
            prior_outputs[ar.agent_name.value] = ar.output_json

    agent_class_map = _get_agent_class_map()
    agent_class = agent_class_map.get(agent_name)
    if not agent_class:
        raise ValueError(f"No agent class for {agent_name.value}")

    logger.info(f"Rerunning: {agent_name.value}" + (f" with guidance" if guidance else ""))
    agent = agent_class(db=db, topic_id=pipeline_run.topic_id, agent_run=target)
    agent.run(prior_outputs)
    logger.info(f"Rerun complete: {agent_name.value}")


def get_pipeline_status(db: Session, pipeline_run_id: int) -> dict:
    """Get current status of a pipeline run."""
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
    if not pipeline_run:
        return None

    total_cost = sum(ar.cost_usd or 0 for ar in pipeline_run.agent_runs)
    total_tokens = sum(ar.total_tokens or 0 for ar in pipeline_run.agent_runs)

    return {
        "id": pipeline_run.id,
        "phase": pipeline_run.phase,
        "status": pipeline_run.status.value,
        "started_at": pipeline_run.started_at.isoformat() if pipeline_run.started_at else None,
        "completed_at": pipeline_run.completed_at.isoformat() if pipeline_run.completed_at else None,
        "error_message": pipeline_run.error_message,
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "agents": [
            {
                "name": ar.agent_name.value,
                "display_name": ar.agent_name.value.replace("_", " ").title(),
                "sequence": ar.sequence_order,
                "status": ar.status.value,
                "model": ar.model_used,
                "tokens": ar.total_tokens or 0,
                "cost_usd": ar.cost_usd or 0,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
                "error": ar.error_message,
            }
            for ar in pipeline_run.agent_runs
        ],
    }
