"""Constants and settings. Everything environment-specific comes from env vars."""

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


MODEL = os.environ.get("MODEL", "claude-sonnet-5")
STRICT_TOOLS = _flag("STRICT_TOOLS")              # false for Ollama
STRUCTURED_SUMMARY = _flag("STRUCTURED_SUMMARY")  # false for Ollama
# Output budget per model call. Qwen3 "thinks" first and thinking counts against this
# budget, so local models need more (set MAX_TOKENS=4096 in .env for Ollama).
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))


DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://support:support@localhost:5432/support_bot"
)
API_KEY = os.environ.get("API_KEY", "")

# Policy numbers. policy.py is the only code that interprets them.
REFUND_WINDOW_DAYS = 30
REFUND_HUMAN_THRESHOLD = 200.00
MAX_VERIFY_ATTEMPTS = 3

# Agent safety limit: model calls per customer message before forced escalation.
MAX_TOOL_ROUNDS = 8
