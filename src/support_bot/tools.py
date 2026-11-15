"""Tools: the agent's only way to touch the world. Every handler takes session_id first;
identity, verification and confirmation are read from the server-side session row."""

import logging

from . import db, policy
from .config import MAX_VERIFY_ATTEMPTS, STRICT_TOOLS

log = logging.getLogger(__name__)


class ToolFailure(Exception):
    """Expected failure. The message is safe to show the model so it can recover."""


def _tool(name, description, properties=None, required=None):
    spec = {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        },
    }
    if STRICT_TOOLS:
        spec["strict"] = True
    return spec


TOOLS = [
    _tool("verify_customer",
          "Verify the customer owns an order. Required before any other order tool.",
          {"order_id": {"type": "string", "description": "e.g. A1002"},
           "contact": {"type": "string", "description": "Email or phone on the order"}},
          ["order_id", "contact"]),
    _tool("lookup_order", "Get status, items, dates and amount of the verified order."),
    _tool("check_policy",
          "Check whether an action is allowed for the verified order. Returns "
          "allowed, denied or needs_human with a reason.",
          {"action": {"type": "string", "enum": ["cancel", "refund"]}}, ["action"]),
    _tool("cancel_order",
          "Cancel the verified order. Only after check_policy returned allowed for cancel "
          "AND the customer confirmed in a later message."),
    _tool("issue_refund",
          "Refund the verified order in full. Only after check_policy returned allowed for "
          "refund AND the customer confirmed in a later message."),
    _tool("escalate_to_human", "Hand the conversation to a human agent.",
          {"reason": {"type": "string"}}, ["reason"]),
]


def _verified(session):
    if session["locked"]:
        raise ToolFailure("Session is locked after failed verification. Offer nothing further.")
    if not session["verified_order_id"]:
        raise ToolFailure("Customer is not verified. Ask for order ID and email/phone, "
                          "then call verify_customer.")
    return session["verified_order_id"]


def _confirmed(session, action):
    if session["pending_action"] != action:
        raise ToolFailure(f"Call check_policy for '{action}' first; it must return allowed.")
    if session["user_turns"] <= session["pending_turn"]:
        raise ToolFailure("The customer has not confirmed yet. Ask them to confirm and wait "
                          "for their reply before calling this tool.")


def verify_customer(session_id, order_id, contact):
    s = db.get_session(session_id)
    if s["locked"]:
        raise ToolFailure("Session is locked after failed verification.")
    found = db.find_order_id(order_id.strip(), contact.strip())
    if found is None:
        r = db.record_failed_attempt(session_id, MAX_VERIFY_ATTEMPTS)
        if r["locked"]:
            db.create_escalation(session_id, None, "Verification failed too many times")
            raise ToolFailure("Verification failed too many times. The session is now locked "
                              "and a human agent will follow up. Do not reveal anything.")
        left = MAX_VERIFY_ATTEMPTS - r["failed_attempts"]
        raise ToolFailure(f"Verification failed: order ID and contact do not match. "
                          f"{left} attempt(s) left.")
    db.update_session(session_id, verified_order_id=found, pending_action=None, pending_turn=None)
    return {"verified": True, "order_id": found}


def lookup_order(session_id):
    order = db.get_order(_verified(db.get_session(session_id)))
    return {k: order[k] for k in
            ("order_id", "status", "total_amount", "placed_at", "delivered_at", "items")}


def check_policy(session_id, action):
    s = db.get_session(session_id)
    order = db.get_order(_verified(s))
    d = policy.check(order, action)
    allowed = d.result == policy.ALLOWED
    db.update_session(
        session_id, last_decision=d.result, last_reason=d.reason,
        pending_action=action if allowed else None,
        pending_turn=s["user_turns"] if allowed else None,
    )
    result = {"action": action, "decision": d.result, "reason": d.reason}
    if allowed:
        result["amount"] = order["total_amount"]
        result["next_step"] = "Ask the customer to explicitly confirm. Wait for their reply."
    return result


def _execute(session_id, action):
    s = db.get_session(session_id)
    order_id = _verified(s)
    _confirmed(s, action)
    order = db.get_order(order_id)
    d = policy.check(order, action)  # re-check: state may have changed since check_policy
    if d.result != policy.ALLOWED:
        db.update_session(session_id, pending_action=None, pending_turn=None)
        raise ToolFailure(f"Policy no longer allows this: {d.reason}")
    if action == "refund":
        result = db.refund_order(session_id, order_id, order["total_amount"])
    else:
        result = db.cancel_order(order_id)
    db.update_session(session_id, action_taken=action, pending_action=None, pending_turn=None)
    return result


def cancel_order(session_id):
    return _execute(session_id, "cancel")


def issue_refund(session_id):
    return _execute(session_id, "refund")


def escalate_to_human(session_id, reason):
    s = db.get_session(session_id)
    ticket = db.create_escalation(session_id, s["verified_order_id"], reason[:500])
    return {"escalated": True, "ticket_id": ticket}


_HANDLERS = {
    "verify_customer": verify_customer,
    "lookup_order": lookup_order,
    "check_policy": check_policy,
    "cancel_order": cancel_order,
    "issue_refund": issue_refund,
    "escalate_to_human": escalate_to_human,
}


def run_tool(session_id, name, tool_input):
    """Run one tool. Returns (result, ok). Never raises: failures become results the
    model can read, so the loop recovers instead of crashing."""
    handler = _HANDLERS.get(name)
    tool_input = tool_input or {}
    if handler is None:
        result, ok = {"error": f"Unknown tool {name}"}, False
    else:
        try:
            result, ok = handler(session_id, **tool_input), True
        except ToolFailure as e:
            result, ok = {"error": str(e)}, False
        except TypeError:
            log.exception("Bad arguments for %s: %r", name, tool_input)
            result, ok = {"error": f"Invalid arguments for {name}."}, False
        except Exception:
            log.exception("Tool %s crashed", name)
            result, ok = {"error": "Internal error. Apologize and offer a human agent."}, False
    try:
        db.log_action(session_id, name, tool_input, result, ok)
    except Exception:
        log.exception("Audit log write failed")
    return result, ok
