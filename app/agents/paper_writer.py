from __future__ import annotations
"""Paper Writer — writes the blog post using all research."""
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("paper_writer")


class PaperWriterAgent(BaseAgent):
    agent_name = "paper_writer"
    display_name = "Paper Writer"
    phase = 2
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]
