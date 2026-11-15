"""Store policy as plain code. The LLM never decides policy; it only explains this result."""

from dataclasses import dataclass

from .config import REFUND_HUMAN_THRESHOLD, REFUND_WINDOW_DAYS

ALLOWED, DENIED, NEEDS_HUMAN = "allowed", "denied", "needs_human"


@dataclass(frozen=True)
class Decision:
    result: str
    reason: str


def check(order: dict, action: str) -> Decision:
    status = order["status"]

    if action == "cancel":
        if status == "processing":
            return Decision(ALLOWED, "Order has not shipped yet, so it can be cancelled.")
        return Decision(
            DENIED, f"Only orders still processing can be cancelled (status: {status})."
        )
    if action == "refund":
        if status == "refunded":
            return Decision(DENIED, "This order has already been refunded.")
        if status != "delivered":
            return Decision(DENIED, f"Refunds apply to delivered orders only (status: {status}).")
        days = order["days_since_delivery"]
        if days > REFUND_WINDOW_DAYS:
            return Decision(
                DENIED,
                f"Delivered {days} days ago; the refund window is {REFUND_WINDOW_DAYS} days.",
            )
        if order["total_amount"] > REFUND_HUMAN_THRESHOLD:
            return Decision(
                NEEDS_HUMAN,
                f"Refunds above ${REFUND_HUMAN_THRESHOLD:.0f} must be approved by a human.",
            )
        return Decision(
            ALLOWED, f"Delivered {days} days ago, within the {REFUND_WINDOW_DAYS}-day window."
        )

    return Decision(NEEDS_HUMAN, f"No automatic policy for action '{action}'.")
