from __future__ import annotations
"""Tangent Finder — proposes related/overlapping topics."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("tangent_finder")


class TangentFinderAgent(BaseAgent):
    agent_name = "tangent_finder"
    display_name = "Tangent Finder"
    phase = 1
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
