"""Terminal interface."""

import json
import sys

from . import db, llm
from .agent import Agent
from .cases import close_session


def init():
    """support-bot-init            schema + DESTRUCTIVE demo seed
    support-bot-init --no-seed  schema only (safe for production)"""
    seed = "--no-seed" not in sys.argv
    db.open_pool()
    try:
        db.init_db(seed=seed)
        print("Database ready." + (" Demo data seeded." if seed else ""))
    finally:
        db.close_pool()


def main():
    debug = "--debug" in sys.argv
    db.open_pool()
    try:
        agent = Agent()
        print(f"Support bot (session {agent.session_id}). Type /done to finish.\n")
        while True:
            try:
                user_input = input("customer> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if user_input == "/done":
                break
            if not user_input:
                continue
            print("agent> ", end="", flush=True)
            for event in agent.send(user_input):
                if event["type"] == "text":
                    print(event["text"], end="", flush=True)
                elif event["type"] == "tool" and debug:
                    print(f"\n  [tool] {event['name']} ok={event['ok']}", flush=True)
            print()

        case = close_session(agent.session_id)
        if case is None:
            print("No conversation to summarize.")
        else:
            print("\n--- Case ---")
            print(json.dumps(case, indent=2))
    finally:
        llm.flush()
        db.close_pool()
