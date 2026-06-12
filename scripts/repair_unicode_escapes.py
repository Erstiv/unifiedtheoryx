"""One-off repair: decode literal \\uXXXX escape sequences stored in generated content.

Agents that saw ASCII-escaped JSON in their prompt context sometimes echoed the
escapes as literal text (e.g. "August Kekul\\u00e9"), which then got stored and
rendered verbatim. Generation is fixed in app/agents/base.py; this script cleans
rows written before that fix.

Usage (from repo root, same env/DATABASE_URL as the app):
    python -m scripts.repair_unicode_escapes --dry-run   # report only
    python -m scripts.repair_unicode_escapes             # apply
"""
import argparse
import sys

from app.database import SessionLocal
from app.models import AgentRun, BibleEntry, Episode, Topic
from app.agents.base import decode_unicode_escapes

EPISODE_TEXT_FIELDS = [
    "title", "subtitle", "cold_open", "paper_content", "script_content",
    "seo_title", "seo_description", "show_notes", "citations_appendix",
]
EPISODE_JSON_FIELDS = ["seo_keywords", "social_snippets"]


def _repair_fields(obj, fields, changes, label):
    changed = False
    for field in fields:
        value = getattr(obj, field, None)
        if value is None:
            continue
        repaired = decode_unicode_escapes(value)
        if repaired != value:
            setattr(obj, field, repaired)
            changes.append(f"{label}.{field}")
            changed = True
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    db = SessionLocal()
    changes = []
    try:
        for ep in db.query(Episode).all():
            _repair_fields(ep, EPISODE_TEXT_FIELDS + EPISODE_JSON_FIELDS, changes,
                           f"episode[topic={ep.topic_id}]")

        # output_json feeds reruns and later phases; output_raw/input_prompt are
        # raw transcripts where \uXXXX is legitimate JSON encoding — leave those.
        for ar in db.query(AgentRun).all():
            _repair_fields(ar, ["output_json"], changes, f"agent_run[{ar.id}:{ar.agent_name.value}]")

        for be in db.query(BibleEntry).all():
            _repair_fields(be, ["title", "content", "entry_data"], changes, f"bible_entry[{be.id}]")

        for t in db.query(Topic).all():
            _repair_fields(t, ["approved_tangents", "danger_mode_edits"], changes, f"topic[{t.id}]")

        if not changes:
            print("No literal unicode escapes found — nothing to repair.")
            return 0

        print(f"{len(changes)} field(s) with literal escapes:")
        for c in changes:
            print(f"  - {c}")

        if args.dry_run:
            db.rollback()
            print("Dry run — no changes written.")
        else:
            db.commit()
            print("Repaired and committed.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
