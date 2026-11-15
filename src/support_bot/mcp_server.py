"""MCP server exposing the order tools over stdio (MCP Python SDK v2).

Deliberately exposes read tools + policy + escalation, NOT cancel/refund: write actions
stay behind this app's confirmation flow. session_id is the trust boundary here, so only
connect hosts you trust.
"""

from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import db, tools

mcp = MCPServer(
    "order-support",
    instructions="Verify the customer with verify_customer before using any other tool.",
)


def _call(session_id: str, name: str, args: dict) -> dict:
    result, ok = tools.run_tool(session_id, name, args)
    if not ok:
        raise ToolError(result["error"])  # model sees this message and can recover
    return result


@mcp.tool()
def verify_customer(session_id: str, order_id: str, contact: str) -> dict:
    """Verify the customer owns the order (contact = email or phone)."""
    return _call(session_id, "verify_customer", {"order_id": order_id, "contact": contact})


@mcp.tool()
def lookup_order(session_id: str) -> dict:
    """Get the verified order's status, items, dates and amount."""
    return _call(session_id, "lookup_order", {})


@mcp.tool()
def check_policy(session_id: str, action: Literal["cancel", "refund"]) -> dict:
    """Deterministic store policy for the verified order."""
    return _call(session_id, "check_policy", {"action": action})


@mcp.tool()
def escalate_to_human(session_id: str, reason: str) -> dict:
    """Hand the case to a human agent."""
    return _call(session_id, "escalate_to_human", {"reason": reason})


def main():
    db.open_pool()
    try:
        mcp.run()  # stdio by default
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
