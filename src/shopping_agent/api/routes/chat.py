"""POST /chat — front-end Role 1 turn.

Takes a multimodal input, calls Role 1 (Omni), returns the structured
understanding. No Role 2 / specialist / envelope in Phase 1 front-end.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from shopping_agent.api.dependencies import (
    get_event_bus,
    get_role1,
    get_session_store,
)
from shopping_agent.conversation.state import SessionStore, Turn
from shopping_agent.events.bus import EventBus
from shopping_agent.events.schema import (
    EV_SESSION_START,
    EV_TURN_COMPLETED,
    EV_TURN_RECEIVED,
)
from shopping_agent.gateway.base import (
    AudioRef,
    ImageRef,
    MultimodalInput,
    StructuredUnderstanding,
)
from shopping_agent.gateway.role1_omni import Role1OmniAdapter

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    text: str | None = None
    images: list[ImageRef] = Field(default_factory=list)
    audio: AudioRef | None = None


class ChatResponse(BaseModel):
    session_id: str
    turn_id: str
    understanding: StructuredUnderstanding


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    role1: Role1OmniAdapter = Depends(get_role1),
    store: SessionStore = Depends(get_session_store),
    events: EventBus = Depends(get_event_bus),
) -> ChatResponse:
    session = store.ensure_session(req.session_id)
    is_new = len(session.turns) == 0
    turn_id = uuid4().hex

    if is_new:
        events.publish(
            EV_SESSION_START,
            session_id=session.session_id,
            turn_id=turn_id,
            trace_id=turn_id,
        )

    events.publish(
        EV_TURN_RECEIVED,
        session_id=session.session_id,
        turn_id=turn_id,
        trace_id=turn_id,
        has_text=bool(req.text),
        image_count=len(req.images),
        has_audio=req.audio is not None,
    )

    inp = MultimodalInput(
        session_id=session.session_id,
        turn_id=turn_id,
        text=req.text,
        images=req.images,
        audio=req.audio,
    )

    understanding = await role1.process(inp)

    store.record_turn(
        session,
        Turn(
            turn_id=turn_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            input=inp,
            understanding=understanding,
        ),
    )

    events.publish(
        EV_TURN_COMPLETED,
        session_id=session.session_id,
        turn_id=turn_id,
        trace_id=turn_id,
        detected_items=len(understanding.detected_items),
    )

    return ChatResponse(
        session_id=session.session_id,
        turn_id=turn_id,
        understanding=understanding,
    )
