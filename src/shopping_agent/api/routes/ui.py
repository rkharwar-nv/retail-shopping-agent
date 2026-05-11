"""Serves the dev inspector UI at /ui.

Static assets live at src/shopping_agent/static/ and are bundled
with the package. No build step, no framework — one HTML, one JS,
one CSS.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

router = APIRouter(tags=["ui"])


@router.get("/ui", include_in_schema=False)
def ui_index():
    """Serve the inspector SPA shell."""
    return FileResponse(STATIC_DIR / "index.html")


# The static mount is registered separately in app.py (StaticFiles
# can't be attached to an APIRouter, only to the FastAPI app).
