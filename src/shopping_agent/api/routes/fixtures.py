"""Dev-only fixture listing + loading.

Gated on config.debug.enabled — returns 404 when debug is off so the
routes don't leak in production.

Used by the /ui inspector to populate the fixture dropdown and to
load a fixture image as base64 for submission to /chat.
"""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from shopping_agent.api.dependencies import get_trace_buffer_dep
from shopping_agent.debug.trace import DebugTraceBuffer

# Repo-root resolved from this file: src/shopping_agent/api/routes/fixtures.py
# up 4 levels: routes -> api -> shopping_agent -> src -> <repo>
PROJECT_ROOT = Path(__file__).resolve().parents[4]
FIXTURES_DIR = PROJECT_ROOT / "smoke" / "fixtures"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}
VALID_PERCEPTIONS = {
    "pantry", "shopping_list", "food_label",
    "fashion", "cosmetics", "unknown",
}

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def _require_debug(buf: DebugTraceBuffer):
    """Fixture routes are dev-only; hide them when debug is disabled."""
    if not buf.enabled:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/list")
def list_fixtures(buf: DebugTraceBuffer = Depends(get_trace_buffer_dep)):
    _require_debug(buf)
    out: dict[str, list[dict]] = {k: [] for k in VALID_PERCEPTIONS}
    if not FIXTURES_DIR.exists():
        return {"fixtures": out}
    for ptype_dir in sorted(FIXTURES_DIR.iterdir()):
        if not ptype_dir.is_dir() or ptype_dir.name not in VALID_PERCEPTIONS:
            continue
        for f in sorted(ptype_dir.iterdir()):
            if f.suffix.lower() not in IMAGE_EXTS:
                continue
            sidecar = f.with_suffix(".txt")
            out[ptype_dir.name].append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "mime_type": MIME_BY_EXT.get(f.suffix.lower(), "image/jpeg"),
                "has_prompt": sidecar.exists(),
                "default_prompt": (
                    sidecar.read_text(encoding="utf-8").strip()
                    if sidecar.exists() else None
                ),
            })
    return {"fixtures": out}


@router.get("/load/{perception_type}/{name}")
def load_fixture(
    perception_type: str,
    name: str,
    buf: DebugTraceBuffer = Depends(get_trace_buffer_dep),
):
    _require_debug(buf)
    if perception_type not in VALID_PERCEPTIONS:
        raise HTTPException(status_code=404, detail="unknown perception_type")
    # Guard against path traversal: only basenames, must be a real file
    # directly inside the perception_type folder.
    fpath = (FIXTURES_DIR / perception_type / name).resolve()
    try:
        fpath.relative_to((FIXTURES_DIR / perception_type).resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid path") from e
    if not fpath.is_file() or fpath.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(status_code=404, detail="fixture not found")
    data = fpath.read_bytes()
    return {
        "name": fpath.name,
        "perception_type": perception_type,
        "mime_type": MIME_BY_EXT.get(fpath.suffix.lower(), "image/jpeg"),
        "size_bytes": len(data),
        "base64": base64.b64encode(data).decode("ascii"),
    }
