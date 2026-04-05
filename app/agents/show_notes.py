from __future__ import annotations
"""Show Notes Generator — references, SEO, social snippets, further reading."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("show_notes")


class ShowNotesAgent(BaseAgent):
    agent_name = "show_notes"
    display_name = "Show Notes Generator"
    phase = 3
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
