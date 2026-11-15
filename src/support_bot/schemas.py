"""Structured output schema for the end-of-chat summary (LLM-written part only)."""

ISSUE_TYPES = ["order_status", "cancel", "refund", "other"]

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "issue_type": {"type": "string", "enum": ISSUE_TYPES},
        "summary": {"type": "string"},
    },
    "required": ["issue_type", "summary"],
    "additionalProperties": False,
}
