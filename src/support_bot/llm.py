"""Shared Claude client (lazy) + optional Langfuse tracing.

Anthropic() reads ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL from the environment,
which is how the same code talks to Claude or a local Ollama.
"""

import logging
import os
from functools import cache

from anthropic import Anthropic

from .config import MODEL

log = logging.getLogger(__name__)


@cache
def get_client() -> Anthropic:
    return Anthropic(max_retries=3, timeout=60.0)


@cache
def _langfuse():
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse import get_client as get_langfuse

        return get_langfuse()
    except Exception:
        log.warning("Langfuse unavailable; tracing disabled", exc_info=True)
        return None


class Generation:
    """One traced LLM call. Manual (non-context) observation, so it is safe across
    generator yields and threads (SSE streaming). Tracing errors never break the app."""

    def __init__(self, name: str, session_id: str, messages: list):
        self._obs = None
        lf = _langfuse()
        if lf is None:
            return
        try:
            self._obs = lf.start_observation(
                as_type="generation", name=name, model=MODEL, input=messages,
                metadata={"session_id": session_id},
            )
        except Exception:
            log.warning("Langfuse start failed", exc_info=True)

    def end(self, message, output=None):
        if self._obs is None:
            return
        try:
            usage = message.usage
            self._obs.update(
                output=output,
                usage_details={"input": usage.input_tokens, "output": usage.output_tokens},
            )
            self._obs.end()
        except Exception:
            log.warning("Langfuse end failed", exc_info=True)


def flush():
    lf = _langfuse()
    if lf is not None:
        lf.flush()
