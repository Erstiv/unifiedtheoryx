from __future__ import annotations
"""Tangent Researcher — deep-dives approved tangent topics using Google Search."""
from google.genai import types
from app.agents.base import BaseAgent
from app.agents._load_prompt import load_prompt

_prompt = load_prompt("tangent_researcher")


class TangentResearcherAgent(BaseAgent):
    agent_name = "tangent_researcher"
    display_name = "Tangent Researcher"
    phase = 1
    system_prompt = _prompt["system_prompt"]
    output_schema = _prompt["output_schema"]

    def _call_gemini(self, prompt: str, max_retries: int = 4, timeout: int = 300):
        """Override to use Google Search grounding tool."""
        import time
        import concurrent.futures
        import logging
        log = logging.getLogger("unified_theory.tangent_researcher")

        def _do_call():
            return self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    max_output_tokens=65536,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
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
                    log.warning(f"Rate limit (attempt {attempt + 1}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise
