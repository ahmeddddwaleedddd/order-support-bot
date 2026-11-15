"""Close a session into a case. Facts (outcome, action, order) come from the database;
the LLM only writes issue_type and a short summary."""

import json
import logging

import anthropic

from . import db, llm
from .config import MAX_TOKENS, MODEL, STRUCTURED_SUMMARY
from .prompts import SUMMARY_PROMPT
from .schemas import ISSUE_TYPES, SUMMARY_SCHEMA

log = logging.getLogger(__name__)
FALLBACK = {"issue_type": "other", "summary": "Automatic summary unavailable."}


def parse_summary(text):
    """Tolerant parser: strips code fences / chatter, validates, normalizes enum case."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in summary output")
    data = json.loads(text[start:end + 1])
    issue = str(data.get("issue_type", "")).strip().lower()
    summary = data.get("summary")
    if issue not in ISSUE_TYPES or not isinstance(summary, str) or not summary.strip():
        raise ValueError(f"summary failed validation: {data!r}")
    return {"issue_type": issue, "summary": summary.strip()[:1000]}


def summarize(history, client=None, session_id=""):
    client = client or llm.get_client()
    transcript = f"<transcript>\n{json.dumps(history, indent=1)}\n</transcript>"
    kwargs = {
        "model": MODEL, "max_tokens": MAX_TOKENS, "system": SUMMARY_PROMPT,
        "messages": [{"role": "user", "content": transcript}],
    }
    if STRUCTURED_SUMMARY:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}}
    gen = llm.Generation("case_summary", session_id, kwargs["messages"])
    try:
        response = client.messages.create(**kwargs)
        text = "".join(b.text for b in response.content if b.type == "text")
        gen.end(response, output=text)
        return parse_summary(text)
    except (anthropic.APIError, ValueError):
        log.exception("Summary failed; using fallback so the case is still saved")
        return dict(FALLBACK)


def derive_outcome(session, escalated):
    if not session["verified_order_id"]:
        return "verification_failed"
    if session["action_taken"]:
        return "resolved"
    if escalated or session["last_decision"] == "needs_human":
        return "escalated"
    if session["last_decision"] == "denied":
        return "denied"
    return "informational"


def close_session(session_id, client=None):
    history = db.load_history(session_id)
    if not history:
        return None
    session = db.get_session(session_id)
    summary = summarize(history, client, session_id)
    return db.insert_case(
        session_id=session_id,
        order_id=session["verified_order_id"],
        issue_type=summary["issue_type"],
        action_taken=session["action_taken"],
        outcome=derive_outcome(session, db.has_escalation(session_id)),
        reason=session["last_reason"] or summary["summary"],
    )
