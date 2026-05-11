"""FastAPI app construction."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shopping_agent import __version__
from shopping_agent.api.routes import chat, debug, fixtures, health, sessions, ui

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
    app.include_router(fixtures.router)
    app.include_router(ui.router)
    # Mount static files at /ui/static so index.html can reference
    # /ui/static/app.js and /ui/static/styles.css.
    if STATIC_DIR.exists():
        app.mount(
            "/ui/static",
            StaticFiles(directory=str(STATIC_DIR)),
            name="ui_static",
        )
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
