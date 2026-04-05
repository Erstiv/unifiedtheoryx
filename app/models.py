"""The Grand Unified Theory of X — Database Models"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
from app.database import Base


# --- Enums ---

class TopicStatus(enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED_PHASE_1 = "paused_phase_1"      # After research, before tangent approval
    PAUSED_TANGENTS = "paused_tangents"      # Tangent research running
    PAUSED_PHASE_2 = "paused_phase_2"        # After writing, before polish
    COMPLETED = "completed"


class RunStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_FOR_REVIEW = "paused_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentName(enum.Enum):
    # Phase 1: Research & Outline
    DEEP_RESEARCHER = "deep_researcher"
    TANGENT_FINDER = "tangent_finder"
    TANGENT_RESEARCHER = "tangent_researcher"
    # Phase 2: Writing
    PAPER_WRITER = "paper_writer"
    SCRIPT_WRITER = "script_writer"
    TITLE_HOOK = "title_hook"
    # Phase 3: Polish & Package
    EDITOR = "editor"
    SHOW_NOTES = "show_notes"


# Phase 1 runs Deep Researcher + Tangent Finder, pauses for tangent approval,
# then runs Tangent Researcher separately before Phase 2 unlocks.
PHASE_AGENTS = {
    1: [AgentName.DEEP_RESEARCHER, AgentName.TANGENT_FINDER],
    2: [AgentName.PAPER_WRITER, AgentName.SCRIPT_WRITER, AgentName.TITLE_HOOK],
    3: [AgentName.EDITOR, AgentName.SHOW_NOTES],
}


class BibleScope(enum.Enum):
    GLOBAL = "global"
    TOPIC = "topic"


class BibleCategory(enum.Enum):
    # Global (Voice & Style Bible)
    VOICE_BLEND = "voice_blend"
    EPISODE_STRUCTURE = "episode_structure"
    NEUROSCIENCE_FRAMING = "neuroscience_framing"
    WRITING_RULES = "writing_rules"
    ANTI_PATTERNS = "anti_patterns"
    # Topic-specific (accumulated by agents)
    DIRECTIVES = "directives"
    ETYMOLOGY = "etymology"
    HISTORY = "history"
    NEUROSCIENCE = "neuroscience"
    CULTURAL = "cultural"
    EXAMPLES = "examples"
    TANGENTS = "tangents"
    CURRENT_EVENTS = "current_events"
    SOURCES = "sources"


class EpisodeStatus(enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    PUBLISHED = "published"


# --- Core Models ---

class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    description = Column(Text)  # Optional user notes about what to explore
    page_count = Column(Integer, default=2)  # 1-3 pages
    script_minutes = Column(Integer, default=10)  # 8-12 minutes
    narrator_count = Column(Integer, default=1)  # 1-3 narrators
    expert_gender = Column(String(20), default="any")  # "male", "female", "any"
    everybody_gender = Column(String(20), default="any")  # "male", "female", "any"
    status = Column(SQLEnum(TopicStatus), default=TopicStatus.DRAFT)
    current_phase = Column(Integer, default=0)
    approved_tangents = Column(JSON)  # [{title, depth, description}, ...]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    published_at = Column(DateTime)

    pipeline_runs = relationship("PipelineRun", back_populates="topic",
                                 order_by="PipelineRun.created_at.desc()")
    bible_entries = relationship("BibleEntry", back_populates="topic",
                                 foreign_keys="BibleEntry.topic_id")
    episode = relationship("Episode", back_populates="topic", uselist=False)
    output_documents = relationship("OutputDocument", back_populates="topic")


# --- Pipeline ---

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    phase = Column(Integer, nullable=False)
    status = Column(SQLEnum(RunStatus), default=RunStatus.PENDING)
    agents_to_run = Column(JSON, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="pipeline_runs")
    agent_runs = relationship("AgentRun", back_populates="pipeline_run",
                              order_by="AgentRun.sequence_order")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=False)
    agent_name = Column(SQLEnum(AgentName), nullable=False)
    sequence_order = Column(Integer, nullable=False)
    status = Column(SQLEnum(RunStatus), default=RunStatus.PENDING)
    model_used = Column(String(100))
    input_prompt = Column(Text)
    output_json = Column(JSON)
    output_raw = Column(Text)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    rerun_guidance = Column(Text)

    pipeline_run = relationship("PipelineRun", back_populates="agent_runs")


# --- Knowledge Base ---

class BibleEntry(Base):
    __tablename__ = "bible_entries"

    id = Column(Integer, primary_key=True)
    scope = Column(SQLEnum(BibleScope), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    category = Column(SQLEnum(BibleCategory), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    entry_data = Column(JSON)
    source = Column(String(100), default="manual")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="bible_entries", foreign_keys=[topic_id])


# --- Episode (final output) ---

class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False, unique=True)
    title = Column(String(500))
    subtitle = Column(String(500))
    cold_open = Column(Text)
    paper_content = Column(Text)  # Final edited paper (markdown)
    script_content = Column(Text)  # Final edited script (markdown)
    seo_title = Column(String(200))
    seo_description = Column(String(500))
    seo_keywords = Column(JSON)  # ["keyword1", "keyword2", ...]
    social_snippets = Column(JSON)  # [{"platform": "twitter", "text": "..."}, ...]
    show_notes = Column(Text)  # Markdown: references, further reading
    status = Column(SQLEnum(EpisodeStatus), default=EpisodeStatus.DRAFT)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="episode")


# --- Output Documents ---

class OutputDocument(Base):
    __tablename__ = "output_documents"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    doc_type = Column(String(50), nullable=False)  # paper_pdf, paper_docx, script_pdf, script_docx
    file_path = Column(String(1000), nullable=False)
    file_name = Column(String(255), nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    topic = relationship("Topic", back_populates="output_documents")
