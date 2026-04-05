from __future__ import annotations
"""Script Writer — writes the podcast script for 1-3 narrators."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("script_writer")


class ScriptWriterAgent(BaseAgent):
    agent_name = "script_writer"
    display_name = "Script Writer"
    phase = 2
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
