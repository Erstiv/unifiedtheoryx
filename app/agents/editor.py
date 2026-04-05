from __future__ import annotations
"""Editor — refines both paper and script for voice consistency and quality."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("editor")


class EditorAgent(BaseAgent):
    agent_name = "editor"
    display_name = "Editor"
    phase = 3
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
