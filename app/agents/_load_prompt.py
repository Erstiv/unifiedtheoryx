"""Dynamic prompt loader — imports prompt modules by agent name."""
import importlib


def load_prompt(agent_name: str) -> dict:
    """Load a prompt module from the prompts package.

    Returns a dict with 'system_prompt' and optionally 'output_schema'.
    """
    MODULE_MAP = {
        "deep_researcher": "01_deep_researcher",
        "tangent_finder": "02_tangent_finder",
        "tangent_researcher": "03_tangent_researcher",
        "paper_writer": "04_paper_writer",
        "script_writer": "05_script_writer",
        "title_hook": "06_title_hook",
        "editor": "07_editor",
        "show_notes": "08_show_notes",
    }

    module_name = MODULE_MAP.get(agent_name, agent_name)
    module = importlib.import_module(f"prompts.{module_name}")

    return {
        "system_prompt": getattr(module, "SYSTEM_PROMPT", ""),
        "output_schema": getattr(module, "OUTPUT_SCHEMA", {}),
    }
