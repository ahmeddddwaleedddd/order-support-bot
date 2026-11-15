import copy
from types import SimpleNamespace as NS

import pytest

from support_bot import db


@pytest.fixture(scope="session")
def database():
    try:
        db.open_pool(wait=True, timeout=3)
    except Exception:
        db.close_pool()
        pytest.skip("PostgreSQL not available (run: docker compose up -d)")
    yield
    db.close_pool()


@pytest.fixture
def fresh_db(database):
    db.init_db(seed=True)


def text(t):
    return NS(type="text", text=t)


def tool(name, inp, id="tu_1"):
    return NS(type="tool_use", id=id, name=name, input=inp)


def msg(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop,
              usage=NS(input_tokens=1, output_tokens=1))


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        return iter([b.text for b in self.message.content if b.type == "text"])

    def get_final_message(self):
        return self.message


class FakeClient:
    """Stands in for anthropic.Anthropic: scripted responses, records every request."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return _Stream(self.scripted.pop(0))

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.scripted.pop(0)
