from __future__ import annotations
"""
Base Agent — all Unified Theory agents inherit from this.
Handles Gemini API calls, context assembly, output parsing, knowledge base writes, and token tracking.
Ported from Muskoid's BaseAgent with image generation removed.
"""
import json
import re
import time
import logging
import concurrent.futures
from datetime import datetime, timezone
from typing import Optional
from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from app.config import GEMINI_API_KEY, AGENT_MODELS, AGENT_TEMPERATURE, AGENT_MAX_TOKENS
from app.models import AgentRun, RunStatus, BibleCategory
from app.bible.knowledge_base import KnowledgeBaseTool, BibleScope

logger = logging.getLogger("unified_theory.base_agent")


class BaseAgent:
    """Base class for all Unified Theory agents."""

    agent_name: str = ""
    display_name: str = ""
    phase: int = 0
    system_prompt: str = ""
    output_schema: dict = {}

    def __init__(self, db: Session, topic_id: int, agent_run: AgentRun):
        self.db = db
        self.topic_id = topic_id
        self.agent_run = agent_run
        self.kb = KnowledgeBaseTool(db, topic_id)
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = AGENT_MODELS.get(self.agent_name, "gemini-2.5-flash")

    def run(self, prior_outputs: dict[str, dict]) -> dict:
        """Execute the agent. Returns parsed JSON output."""
        self.agent_run.status = RunStatus.RUNNING
        self.agent_run.started_at = datetime.now(timezone.utc)
        self.agent_run.model_used = self.model
        self.db.commit()

        try:
            prompt = self._build_prompt(prior_outputs)
            self.agent_run.input_prompt = prompt[:50000]
            self.db.commit()

            response = self._call_gemini(prompt)

            raw_text = response.text or ""
            self.agent_run.output_raw = raw_text
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = response.usage_metadata
                self.agent_run.input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                self.agent_run.output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                self.agent_run.total_tokens = self.agent_run.input_tokens + self.agent_run.output_tokens
                self.agent_run.cost_usd = self._estimate_cost(
                    self.agent_run.input_tokens, self.agent_run.output_tokens
                )
            self.db.commit()

            output = self._parse_json_output(raw_text)

            self._write_kb_entries(output)

            self.agent_run.output_json = output
            self.agent_run.status = RunStatus.COMPLETED
            self.agent_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return output

        except Exception as e:
            self.agent_run.status = RunStatus.FAILED
            self.agent_run.error_message = str(e)
            self.agent_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

    def _build_prompt(self, prior_outputs: dict[str, dict]) -> str:
        """Assemble the full prompt with knowledge base context and prior outputs."""
        sections = []

        # Topic context
        from app.models import Topic
        topic = self.db.query(Topic).filter(Topic.id == self.topic_id).first()
        if topic:
            sections.append("=== TOPIC ===")
            sections.append(f"Topic: {topic.title}")
            if topic.description:
                sections.append(f"Notes: {topic.description}")
            sections.append(f"Target: {topic.page_count} page(s), {topic.script_minutes} minute script, {topic.narrator_count} narrator(s)")
            if topic.narrator_count >= 2:
                expert_g = getattr(topic, 'expert_gender', 'any') or 'any'
                sections.append(f"Expert gender: {expert_g}")
            if topic.narrator_count >= 3:
                everybody_g = getattr(topic, 'everybody_gender', 'any') or 'any'
                sections.append(f"Everybody gender: {everybody_g}")
            if topic.approved_tangents:
                sections.append(f"Approved tangents: {json.dumps(topic.approved_tangents)}")
            sections.append("=== END TOPIC ===\n")

        # Voice & Style Bible (global knowledge)
        global_kb = self.kb.to_prompt_text(BibleScope.GLOBAL)
        sections.append(global_kb)

        # Topic Knowledge Base (accumulated research)
        topic_kb = self.kb.to_prompt_text(BibleScope.TOPIC)
        sections.append(topic_kb)

        # Prior agent outputs
        for agent_name, output in prior_outputs.items():
            sections.append(f"=== OUTPUT FROM: {agent_name.upper()} ===")
            sections.append(json.dumps(output, indent=2, default=str)[:30000])
            sections.append(f"=== END {agent_name.upper()} ===\n")

        # One-time rerun guidance
        if self.agent_run.rerun_guidance:
            sections.append("=== ONE-TIME INSTRUCTION (from user) ===")
            sections.append(self.agent_run.rerun_guidance)
            sections.append("Apply this instruction to your output. This is a one-time directive — prioritize it.")
            sections.append("=== END INSTRUCTION ===\n")

        # Danger mode context
        if topic and topic.danger_mode_edits:
            sections.append("=== DANGER_MODE=true ===")
            sections.append("The user has made editorial edits. Honor their changes.")
            import json as _json
            edits_str = _json.dumps(topic.danger_mode_edits, default=str)
            if len(edits_str) > 15000:
                edits_str = edits_str[:15000] + "...(truncated)"
            sections.append(f"User edits: {edits_str}")
            sections.append("=== END DANGER MODE ===\n")
            sections.append("IMPORTANT: Include inline citations [1], [2], etc. in your output and a 'sources' array with full references.")

        sections.append("=== YOUR TASK ===")
        sections.append("Analyze all the context above and produce your output as valid JSON.")
        sections.append("Follow the instructions in your system prompt exactly.")
        sections.append("Return ONLY valid JSON — no markdown, no explanation, just the JSON object.")

        return "\n\n".join(sections)

    def _call_gemini(self, prompt: str, max_retries: int = 4, timeout: int = 300) -> object:
        """Call Gemini with exponential backoff and timeout."""

        def _do_call():
            config_kwargs = dict(
                system_instruction=self.system_prompt,
                temperature=AGENT_TEMPERATURE,
                max_output_tokens=AGENT_MAX_TOKENS,
                response_mime_type="application/json",
            )
            if self.output_schema:
                config_kwargs["response_schema"] = self.output_schema
            return self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )

        for attempt in range(max_retries + 1):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_do_call)
                    try:
                        response = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        raise TimeoutError(f"Gemini call timed out after {timeout}s")
                return response
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(k in err_str for k in [
                    "429", "503", "rate", "quota", "resource_exhausted", "unavailable", "high demand"
                ])
                if is_rate_limit and attempt < max_retries:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def _parse_json_output(self, text: str) -> dict:
        """Parse JSON from model output with multiple fallback strategies."""
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        # Attempt 1: Direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Attempt 2: Fix unescaped control characters
        def _escape_ctrl(m):
            inner = m.group(1)
            inner = inner.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            return '"' + inner + '"'
        ctrl_fixed = re.sub(r'"((?:[^"\\]|\\.)*)"', _escape_ctrl, cleaned, flags=re.DOTALL)
        ctrl_fixed = re.sub(r",\s*([}\]])", r"\1", ctrl_fixed)
        try:
            return json.loads(ctrl_fixed)
        except json.JSONDecodeError:
            pass

        # Attempt 3: Trailing commas only
        fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Attempt 4: Extract outermost JSON object
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            subset = cleaned[brace_start:brace_end + 1]
            fixed_subset = re.sub(r",\s*([}\]])", r"\1", subset)
            try:
                return json.loads(fixed_subset)
            except json.JSONDecodeError:
                pass

        # Attempt 5: Ask Gemini to fix its own JSON
        logger.warning("JSON parse failed. Attempting Gemini self-repair...")
        repair_response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"The following text was supposed to be valid JSON but has syntax errors. "
                     f"Fix it and return ONLY the corrected JSON, nothing else:\n\n{cleaned[:60000]}",
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=65536,
                response_mime_type="application/json",
            ),
        )
        repaired = repair_response.text.strip()
        repaired = re.sub(r"^```(?:json)?\s*\n?", "", repaired)
        repaired = re.sub(r"\n?```\s*$", "", repaired)
        return json.loads(repaired.strip())

    def _write_kb_entries(self, output: dict):
        """Write any knowledge_base_entries from agent output to the knowledge base."""
        entries = output.get("knowledge_base_entries") or []
        if isinstance(entries, list) and len(entries) > 0:
            try:
                self.kb.add_entries_bulk(entries, source=f"agent:{self.agent_name}")
            except Exception as e:
                logger.warning(f"Failed to write KB entries: {e}")

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        if "pro" in self.model:
            input_cost = (input_tokens / 1_000_000) * 1.25
            output_cost = (output_tokens / 1_000_000) * 10.00
        else:
            input_cost = (input_tokens / 1_000_000) * 0.15
            output_cost = (output_tokens / 1_000_000) * 0.60
        return round(input_cost + output_cost, 4)
