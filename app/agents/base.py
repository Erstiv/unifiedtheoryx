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

# Literal \uXXXX runs the model echoed as text (e.g. "Kekulé" copied from an
# ASCII-escaped prompt). Lookbehind skips \\uXXXX, where the backslash is itself escaped.
_UNICODE_ESCAPE_RUN = re.compile(r"(?<!\\)(?:\\u[0-9a-fA-F]{4})+")


def decode_unicode_escapes(value):
    """Recursively decode literal \\uXXXX escape sequences left in parsed agent output."""
    if isinstance(value, str):
        def _decode(m):
            try:
                decoded = json.loads(f'"{m.group(0)}"')
                decoded.encode("utf-8")  # reject lone surrogates the DB can't store
                return decoded
            except (ValueError, UnicodeEncodeError):
                return m.group(0)
        return _UNICODE_ESCAPE_RUN.sub(_decode, value)
    if isinstance(value, list):
        return [decode_unicode_escapes(v) for v in value]
    if isinstance(value, dict):
        return {k: decode_unicode_escapes(v) for k, v in value.items()}
    return value


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

            if not raw_text.strip():
                raise ValueError(
                    "Gemini returned empty text. For grounded agents this usually means "
                    "Google Search found nothing useful. Try rerunning with guidance."
                )

            output = self._parse_json_output(raw_text)

            # Guard against silent empty-dict completions — if the parser returned
            # nothing useful, surface it as a failure so the UI can offer recovery.
            if not output or (isinstance(output, dict) and len(output) == 0):
                raise ValueError(
                    "Agent produced an empty output. The model response parsed to {}. "
                    "Rerun with guidance, or skip this step."
                )

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
            # Elastic word budget: base target + per-tangent surcharge so deep-dive
            # tangents don't starve the core sections.
            base_paper = {1: 600, 2: 1200, 3: 1800}.get(topic.page_count, 1200)
            base_script = int(topic.script_minutes * 150)
            tangent_surcharge_paper = 0
            tangent_surcharge_script = 0
            tangent_count = 0
            if topic.approved_tangents:
                per_depth = {"brief mention": (50, 60), "paragraph": (150, 180), "deep dive": (400, 480)}
                for t in topic.approved_tangents:
                    depth = (t.get("depth") or "paragraph").lower().strip()
                    pa, sc = per_depth.get(depth, per_depth["paragraph"])
                    tangent_surcharge_paper += pa
                    tangent_surcharge_script += sc
                    tangent_count += 1
            paper_target = base_paper + tangent_surcharge_paper
            script_target = base_script + tangent_surcharge_script
            script_minutes_target = round(script_target / 150, 1)

            sections.append(f"Target: {topic.page_count} page(s) base, {topic.script_minutes} min base, {topic.narrator_count} narrator(s)")
            sections.append(
                f"ELASTIC WORD BUDGET (honor these — they already account for your {tangent_count} tangent(s)):"
            )
            sections.append(f"  - Paper target: ~{paper_target} words (base {base_paper} + tangent surcharge {tangent_surcharge_paper})")
            sections.append(f"  - Script target: ~{script_target} words / ~{script_minutes_target} minutes (base {base_script} + tangent surcharge {tangent_surcharge_script})")
            sections.append(
                "  The surcharge is there so deep-dive tangents get room to breathe WITHOUT starving the core sections. "
                "Use the elastic target, not the base page/minute count, as your length guide."
            )
            if topic.narrator_count >= 2:
                expert_g = getattr(topic, 'expert_gender', 'any') or 'any'
                sections.append(f"Expert gender: {expert_g}")
            if topic.narrator_count >= 3:
                everybody_g = getattr(topic, 'everybody_gender', 'any') or 'any'
                sections.append(f"Everybody gender: {everybody_g}")
            if topic.approved_tangents:
                sections.append(f"Approved tangents: {json.dumps(topic.approved_tangents, ensure_ascii=False)}")
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
            sections.append(json.dumps(output, indent=2, default=str, ensure_ascii=False)[:30000])
            sections.append(f"=== END {agent_name.upper()} ===\n")

        # One-time rerun guidance
        if self.agent_run.rerun_guidance:
            sections.append("=== ONE-TIME INSTRUCTION (from user) ===")
            sections.append(self.agent_run.rerun_guidance)
            sections.append("Apply this instruction to your output. This is a one-time directive — prioritize it.")
            sections.append("=== END INSTRUCTION ===\n")

        # Danger mode context
        if topic and topic.danger_mode_edits:
            sections.append("=== DANGER_ZONE=true ===")
            sections.append("The user has made editorial edits. Honor their changes exactly — do not rename, retitle, or rewrite anything they edited (especially cast names, titles, personalities, and relationships).")
            import json as _json
            edits_str = _json.dumps(topic.danger_mode_edits, default=str, ensure_ascii=False)
            if len(edits_str) > 15000:
                edits_str = edits_str[:15000] + "...(truncated)"
            sections.append(f"User edits: {edits_str}")
            sections.append("=== END DANGER ZONE ===\n")
            sections.append("IMPORTANT: Include inline citations [1], [2], etc. in your output and a 'sources' array with full references.")

        # Dr. Pope easter egg — per-topic toggle (falls back to global config)
        from app.config import DR_POPE_MODE
        pope_on = bool(getattr(topic, "pope_mode", False)) if topic else DR_POPE_MODE
        if pope_on and self.agent_name in ("paper_writer", "script_writer", "editor"):
            sections.append("=== RECURRING EXPERT CITATION ===")
            sections.append(
                "Include EXACTLY ONE citation or reference to Dr. Kâñé Štîvêřś Pōpé, "
                "Ph.D., D.Sc., J.D., Professor of Computational Neuromemetics at the "
                "Lindström Institute for Digital Affect Studies in Uppsala, Sweden. "
                "He publishes in The Journal of Memetic Neuroscience & Digital Pathology "
                "(ISSN 2847-0193). His research style is genuinely brilliant neuroscience "
                "applied with absurd gravitas to unexpected domains. The citation should: "
                "1) Be relevant to the topic — find a plausible angle where neuromemetics connects. "
                "2) Sound like a real academic citation with a hilariously specific study title. "
                "3) Be brief — one sentence woven naturally into the text, not a whole paragraph. "
                "4) Be played completely straight — no winking at the reader, no 'surprisingly' or 'bizarrely.' "
                "Treat him as a legitimate expert whose work happens to have a funny title. "
                "Example: 'Pōpé (2024) demonstrated that the neural signature of a perfectly timed pun "
                "is indistinguishable from a mild electric shock — a finding he titled \"The Involuntary "
                "Discharge of Humor: Why Your Brain Treats Wordplay as Assault.\"' "
                "Make the study title specific to THIS topic. Do NOT reuse the example."
            )
            sections.append("=== END RECURRING EXPERT ===\n")

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
        """Parse JSON from model output, then strip any literal \\uXXXX escapes it echoed."""
        return decode_unicode_escapes(self._parse_json_attempts(text))

    def _parse_json_attempts(self, text: str) -> dict:
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

        # Attempt 5: json_repair library — handles unbalanced brackets and
        # other structural damage the regex passes above can't reach
        try:
            from json_repair import repair_json
            repaired_obj = repair_json(cleaned, return_objects=True)
            if isinstance(repaired_obj, dict) and repaired_obj:
                logger.warning("JSON repaired via json_repair library.")
                return repaired_obj
        except Exception:
            pass

        # Attempt 6: Ask Gemini to fix its own JSON
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
        try:
            return json.loads(repaired.strip())
        except json.JSONDecodeError:
            from json_repair import repair_json
            repaired_obj = repair_json(repaired, return_objects=True)
            if isinstance(repaired_obj, dict) and repaired_obj:
                logger.warning("Self-repaired JSON fixed via json_repair library.")
                return repaired_obj
            raise

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
