"""The agent loop, independent of any interface. send() yields events:
{"type": "text", "text": ...}, {"type": "tool", "name": ..., "ok": ...}, {"type": "done"}.
CLI, FastAPI and Telegram all consume the same generator."""

import json
import logging
import uuid

from . import db, llm
from .config import MAX_TOKENS, MAX_TOOL_ROUNDS, MODEL
from .prompts import BUDGET_MESSAGE, EMPTY_REPLY_MESSAGE, LOCKED_MESSAGE, SYSTEM_PROMPT
from .tools import TOOLS, run_tool

log = logging.getLogger(__name__)


def _block_to_dict(block):
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump(exclude_none=True)  # e.g. thinking blocks: send back unchanged


class Agent:
    def __init__(self, session_id=None, client=None):
        self.session_id = session_id or str(uuid.uuid4())
        self.client = client or llm.get_client()
        db.get_session(self.session_id)
        self.history = db.load_history(self.session_id)

    def _append(self, role, content):
        api_role = "user" if role == "tool_result" else role
        self.history.append({"role": api_role, "content": content})
        db.insert_message(self.session_id, role, content)

    def send(self, user_text):
        if db.get_session(self.session_id)["locked"]:
            yield {"type": "text", "text": LOCKED_MESSAGE}
            yield {"type": "done"}
            return

        db.bump_user_turn(self.session_id)
        self._append("user", user_text)

        for _ in range(MAX_TOOL_ROUNDS):
            gen = llm.Generation("agent_turn", self.session_id, self.history)
            with self.client.messages.stream(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                messages=self.history, tools=TOOLS,
            ) as stream:
                for chunk in stream.text_stream:
                    yield {"type": "text", "text": chunk}
                final = stream.get_final_message()

            blocks = [_block_to_dict(b) for b in final.content]
            gen.end(final, output=blocks)

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            has_text = any(b.type == "text" and b.text.strip() for b in final.content)
            if not tool_uses and not has_text:
                # The model ended its turn without saying anything (for example, thinking
                # used the whole token budget). Never leave the customer with silence, and
                # never store an empty assistant message in the history.
                log.warning("Model returned no text (stop_reason=%s)", final.stop_reason)
                blocks = [{"type": "text", "text": EMPTY_REPLY_MESSAGE}]
                yield {"type": "text", "text": EMPTY_REPLY_MESSAGE}
            self._append("assistant", blocks)

            if not tool_uses:
                yield {"type": "done"}
                return

            results = []
            for block in tool_uses:
                result, ok = run_tool(self.session_id, block.name, block.input)
                yield {"type": "tool", "name": block.name, "ok": ok}
                results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result), "is_error": not ok,
                })
            self._append("tool_result", results)

        # Budget exhausted: escalate deterministically and close the turn cleanly.
        run_tool(self.session_id, "escalate_to_human",
                 {"reason": "Agent exceeded tool-call budget"})
        self._append("assistant", [{"type": "text", "text": BUDGET_MESSAGE}])
        yield {"type": "text", "text": BUDGET_MESSAGE}
        yield {"type": "done"}