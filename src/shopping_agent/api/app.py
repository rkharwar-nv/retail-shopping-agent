"""FastAPI app construction."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from shopping_agent import __version__
from shopping_agent.api.routes import chat, debug, health, sessions

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Shopping Agent",
        version=__version__,
        description="Multimodal retail shopping agent — Phase 1 front-end (Role 1 only).",
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(debug.router)
    return app


app = create_app()


def main() -> None:
    """Entry point for `shopping-agent` console script."""
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "shopping_agent.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
