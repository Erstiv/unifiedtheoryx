"""
Knowledge Base Tool — two-tier knowledge system for The Grand Unified Theory of X.
Global tier: Voice rules, episode structure, neuroscience framing, writing guidelines.
Topic tier: Per-topic research accumulated by agents.
Ported from Muskoid's BrandBibleTool.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models import BibleEntry, BibleScope, BibleCategory


class KnowledgeBaseTool:
    """Interface for agents to read/write the knowledge base."""

    def __init__(self, db: Session, topic_id: Optional[int] = None):
        self.db = db
        self.topic_id = topic_id

    # --- Read ---

    def get_global_entries(self, category: Optional[BibleCategory] = None) -> list[BibleEntry]:
        q = self.db.query(BibleEntry).filter(
            BibleEntry.scope == BibleScope.GLOBAL,
            BibleEntry.is_active == True,
        )
        if category:
            q = q.filter(BibleEntry.category == category)
        return q.order_by(BibleEntry.sort_order, BibleEntry.title).all()

    def get_topic_entries(self, category: Optional[BibleCategory] = None) -> list[BibleEntry]:
        if not self.topic_id:
            return []
        q = self.db.query(BibleEntry).filter(
            BibleEntry.scope == BibleScope.TOPIC,
            BibleEntry.topic_id == self.topic_id,
            BibleEntry.is_active == True,
        )
        if category:
            q = q.filter(BibleEntry.category == category)
        return q.order_by(BibleEntry.sort_order, BibleEntry.title).all()

    def search(self, keyword: str, scope: Optional[BibleScope] = None) -> list[BibleEntry]:
        q = self.db.query(BibleEntry).filter(
            BibleEntry.is_active == True,
            (BibleEntry.title.ilike(f"%{keyword}%") | BibleEntry.content.ilike(f"%{keyword}%")),
        )
        if scope:
            q = q.filter(BibleEntry.scope == scope)
        if scope == BibleScope.TOPIC and self.topic_id:
            q = q.filter(BibleEntry.topic_id == self.topic_id)
        return q.all()

    # --- Write (topic tier only) ---

    def add_entry(self, category: BibleCategory, title: str, content: str,
                  source: str = "manual", entry_data: Optional[dict] = None) -> BibleEntry:
        entry = BibleEntry(
            scope=BibleScope.TOPIC,
            topic_id=self.topic_id,
            category=category,
            title=title,
            content=content,
            source=source,
            entry_data=entry_data,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def add_entries_bulk(self, entries: list[dict], source: str = "manual") -> list[BibleEntry]:
        created = []
        for e in entries:
            cat = e.get("category")
            if isinstance(cat, str):
                cat = BibleCategory(cat)
            entry = BibleEntry(
                scope=BibleScope.TOPIC,
                topic_id=self.topic_id,
                category=cat,
                title=e["title"],
                content=e["content"],
                source=source,
                entry_data=e.get("entry_data"),
            )
            self.db.add(entry)
            created.append(entry)
        self.db.commit()
        for entry in created:
            self.db.refresh(entry)
        return created

    def update_entry(self, entry_id: int, **kwargs) -> Optional[BibleEntry]:
        entry = self.db.query(BibleEntry).filter(BibleEntry.id == entry_id).first()
        if not entry:
            return None
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def delete_entry(self, entry_id: int) -> bool:
        entry = self.db.query(BibleEntry).filter(BibleEntry.id == entry_id).first()
        if not entry:
            return False
        entry.is_active = False
        self.db.commit()
        return True

    # --- Prompt Formatting ---

    def to_prompt_text(self, scope: BibleScope,
                       categories: Optional[list[BibleCategory]] = None) -> str:
        """Format knowledge base entries as text for LLM prompts."""
        if scope == BibleScope.GLOBAL:
            entries = self.get_global_entries()
            label = "VOICE & STYLE BIBLE"
        else:
            entries = self.get_topic_entries()
            label = "TOPIC KNOWLEDGE BASE"

        if categories:
            entries = [e for e in entries if e.category in categories]

        if not entries:
            return f"=== {label} ===\n(No entries yet)\n"

        def _sort_key(e):
            if e.category == BibleCategory.DIRECTIVES:
                return ("0_directives", e.sort_order)
            return (e.category.value, e.sort_order)

        lines = [f"=== {label} ==="]
        current_cat = None
        for entry in sorted(entries, key=_sort_key):
            if entry.category != current_cat:
                current_cat = entry.category
                if current_cat == BibleCategory.DIRECTIVES:
                    lines.append("\n!!! MANDATORY DIRECTIVES (ALL AGENTS MUST FOLLOW) !!!")
                    lines.append("The following are hard constraints.\n")
                else:
                    lines.append(f"\n--- {current_cat.value.replace('_', ' ').title()} ---")

            if current_cat == BibleCategory.DIRECTIVES:
                lines.append(f"  DIRECTIVE: [{entry.title}]")
            else:
                lines.append(f"  [{entry.title}]")
            content = entry.content
            if len(content) > 500:
                content = content[:497] + "..."
            lines.append(f"  {content}")
            lines.append("")

        lines.append(f"=== {len(entries)} entry(ies) total ===")
        return "\n".join(lines)
