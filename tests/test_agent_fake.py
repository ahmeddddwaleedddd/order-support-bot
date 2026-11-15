import json

from conftest import FakeClient, msg, text, tool

from support_bot import db
from support_bot.agent import Agent
from support_bot.cases import close_session
from support_bot.prompts import EMPTY_REPLY_MESSAGE


def test_failed_tool_is_fed_back_as_error(fresh_db):
    fake = FakeClient([
        msg(tool("lookup_order", {}), stop="tool_use"),
        msg(text("I need your order ID and email first.")),
    ])
    events = list(Agent(client=fake).send("where is my order?"))
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "not verified" in json.loads(tool_result["content"])["error"]
    assert events[-1] == {"type": "done"}


def test_full_happy_path_refund(fresh_db):
    fake = FakeClient([
        msg(tool("verify_customer", {"order_id": "A1002", "contact": "jordan@example.com"},
                 "t1"), stop="tool_use"),
        msg(tool("check_policy", {"action": "refund"}, "t2"), stop="tool_use"),
        msg(text("You're eligible for a $49 refund. Reply yes to confirm.")),
        msg(tool("issue_refund", {}, "t3"), stop="tool_use"),
        msg(text("Done! Your refund is on its way.")),
        msg(text('{"issue_type": "Refund", "summary": "Refund issued for A1002."}')),
    ])
    agent = Agent(client=fake)
    list(agent.send("Refund A1002 please, jordan@example.com"))
    list(agent.send("yes"))
    assert db.refund_exists("A1002")
    case = close_session(agent.session_id, client=fake)
    assert case["outcome"] == "resolved" and case["issue_type"] == "refund"


def test_garbage_summary_still_saves_case(fresh_db):
    fake = FakeClient([msg(text("Hello!")), msg(text("not json at all"))])
    agent = Agent(client=fake)
    list(agent.send("hi"))
    case = close_session(agent.session_id, client=fake)
    assert case["issue_type"] == "other" and case["outcome"] == "verification_failed"

def test_empty_model_reply_gets_fallback(fresh_db):
    fake = FakeClient([msg()])  # the model says nothing at all
    events = list(Agent(client=fake).send("hello"))
    texts = [e["text"] for e in events if e["type"] == "text"]
    assert texts == [EMPTY_REPLY_MESSAGE]
    assert events[-1] == {"type": "done"}