import uuid

from support_bot import db, tools


def sid():
    return str(uuid.uuid4())


def test_lookup_before_verify_is_refused(fresh_db):
    result, ok = tools.run_tool(sid(), "lookup_order", {})
    assert not ok and "not verified" in result["error"]


def test_wrong_email_and_unknown_order_look_identical(fresh_db):
    a, _ = tools.run_tool(sid(), "verify_customer", {"order_id": "A1002", "contact": "x@y.com"})
    b, _ = tools.run_tool(sid(), "verify_customer", {"order_id": "Z9999", "contact": "x@y.com"})
    assert a == b


def test_phone_verification_works(fresh_db):
    _, ok = tools.run_tool(sid(), "verify_customer",
                           {"order_id": "a1002", "contact": "+1 (555) 123-4567"})
    assert ok


def test_three_failures_lock_and_escalate(fresh_db):
    s = sid()
    for _ in range(3):
        tools.run_tool(s, "verify_customer", {"order_id": "A1002", "contact": "bad@x.com"})
    _, ok = tools.run_tool(s, "verify_customer",
                           {"order_id": "A1002", "contact": "jordan@example.com"})
    assert not ok and db.get_session(s)["locked"] and db.has_escalation(s)


def test_refund_requires_confirmation_in_later_turn(fresh_db):
    s = sid()
    db.get_session(s)
    tools.run_tool(s, "verify_customer", {"order_id": "A1002", "contact": "jordan@example.com"})
    tools.run_tool(s, "check_policy", {"action": "refund"})
    result, ok = tools.run_tool(s, "issue_refund", {})
    assert not ok and "not confirmed" in result["error"]
    assert not db.refund_exists("A1002")


def test_refund_is_idempotent(fresh_db):
    s = sid()
    tools.run_tool(s, "verify_customer", {"order_id": "A1002", "contact": "jordan@example.com"})
    tools.run_tool(s, "check_policy", {"action": "refund"})
    db.bump_user_turn(s)  # customer said "yes"
    _, ok = tools.run_tool(s, "issue_refund", {})
    assert ok
    _, ok_again = tools.run_tool(s, "issue_refund", {})
    assert not ok_again
    assert db.refund_order(s, "A1002", 49.0)["already_refunded"] is True


def test_denied_refund_outside_window(fresh_db):
    s = sid()
    tools.run_tool(s, "verify_customer", {"order_id": "A1003", "contact": "maria@example.com"})
    result, _ = tools.run_tool(s, "check_policy", {"action": "refund"})
    assert result["decision"] == "denied"
