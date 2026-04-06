"""The Grand Unified Theory of X — Configuration"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'unified_theory.db'}")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8016"))

TOPICS_DIR = BASE_DIR / "topics"
TOPICS_DIR.mkdir(exist_ok=True)

# Gemini model configuration per agent
_FLASH = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
_PRO = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")

AGENT_MODELS = {
    # Phase 1: Research
    "deep_researcher": _FLASH,          # Flash — uses Google Search grounding
    "tangent_finder": _FLASH,            # Flash — proposes related topics
    "tangent_researcher": _FLASH,        # Flash — uses Google Search grounding
    # Phase 2: Writing
    "paper_writer": _PRO,                # Pro — long-form quality writing
    "script_writer": _PRO,               # Pro — creative script writing
    "title_hook": _FLASH,                # Flash — title/hook generation
    # Phase 3: Polish
    "editor": _PRO,                      # Pro — voice consistency + refinement
    "show_notes": _FLASH,                # Flash — metadata generation
}

AGENT_TEMPERATURE = 0.8  # Slightly higher than Muskoid for creative writing
AGENT_MAX_TOKENS = 65536

# Easter egg: Dr. Pope cameo citation in every episode. Set to False to disable.
DR_POPE_MODE = True
