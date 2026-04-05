from __future__ import annotations
"""Title & Hook Generator — creates episode title, subtitle, and cold open."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("title_hook")


class TitleHookAgent(BaseAgent):
    agent_name = "title_hook"
    display_name = "Title & Hook Generator"
    phase = 2
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
