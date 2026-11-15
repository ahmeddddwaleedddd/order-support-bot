from support_bot.policy import ALLOWED, DENIED, NEEDS_HUMAN, check


def order(status="delivered", amount=49.0, days=5):
    return {"status": status, "total_amount": amount, "days_since_delivery": days}


def test_refund_allowed_in_window():
    assert check(order(), "refund").result == ALLOWED


def test_refund_denied_after_30_days():
    d = check(order(days=45), "refund")
    assert d.result == DENIED and "30" in d.reason


def test_refund_boundary_day_30_allowed():
    assert check(order(days=30), "refund").result == ALLOWED


def test_refund_high_value_needs_human():
    assert check(order(amount=249.0), "refund").result == NEEDS_HUMAN


def test_refund_twice_denied():
    assert check(order(status="refunded"), "refund").result == DENIED


def test_cancel_only_processing():
    assert check(order(status="processing", days=None), "cancel").result == ALLOWED
    assert check(order(status="shipped", days=None), "cancel").result == DENIED


def test_unknown_action_needs_human():
    assert check(order(), "reship").result == NEEDS_HUMAN
