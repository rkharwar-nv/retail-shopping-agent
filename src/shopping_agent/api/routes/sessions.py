"""GET /sessions/:id and GET /sessions — convenience for debugging/demos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from shopping_agent.api.dependencies import get_session_store
from shopping_agent.conversation.state import SessionStore

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
def list_sessions(store: SessionStore = Depends(get_session_store)) -> dict:
    return {"sessions": store.list_sessions()}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> dict:
    s = store.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session_id": s.session_id,
        "created_at": s.created_at,
        "turn_count": len(s.turns),
        "turns": [
            {
                "turn_id": t.turn_id,
                "created_at": t.created_at,
                "text": t.input.text,
                "image_count": len(t.input.images),
                "has_audio": t.input.audio is not None,
                "understanding": (
                    t.understanding.model_dump() if t.understanding else None
                ),
            }
            for t in s.turns
        ],
    }
