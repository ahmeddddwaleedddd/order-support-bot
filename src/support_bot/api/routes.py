from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from ..agent import Agent
from ..cases import close_session
from .auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None


class ChatOut(BaseModel):
    session_id: str
    reply: str


def _agent(body: ChatIn) -> Agent:
    return Agent(str(body.session_id) if body.session_id else None)


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    agent = _agent(body)
    reply = "".join(e["text"] for e in agent.send(body.message) if e["type"] == "text")
    return ChatOut(session_id=agent.session_id, reply=reply)


@router.post("/chat/stream", response_class=EventSourceResponse)
def chat_stream(body: ChatIn) -> Iterable[ServerSentEvent]:
    agent = _agent(body)
    yield ServerSentEvent(data={"session_id": agent.session_id}, event="session")
    for event in agent.send(body.message):
        yield ServerSentEvent(data=event, event=event["type"])


@router.post("/sessions/{session_id}/close")
def close(session_id: UUID) -> dict:
    case = close_session(str(session_id))
    if case is None:
        raise HTTPException(404, "No conversation for this session")
    return case
