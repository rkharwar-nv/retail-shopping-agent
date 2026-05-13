"""Probe whether build.nvidia.com Omni accepts video_url content blocks.

This is the test we should have run before the user did. Sends the
real fixture video through the same code path the /chat endpoint
uses, and prints the upstream response in detail.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

# Force project venv imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load .env
import shutil
env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from shopping_agent.config import load_config  # noqa: E402
from shopping_agent.events.bus import build_bus  # noqa: E402
from shopping_agent.gateway.base import (  # noqa: E402
    MultimodalInput,
    VideoRef,
)
from shopping_agent.gateway.role1_omni import Role1OmniAdapter  # noqa: E402


async def main() -> int:
    fixture = ROOT / "smoke/fixtures/shopping_list/shoppinglist_video1.mp4"
    if not fixture.exists():
        print(f"missing fixture: {fixture}", file=sys.stderr)
        return 2

    raw = fixture.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"video: {fixture.name}  size: {len(raw)} bytes  b64: {len(b64)} chars")

    cfg = load_config()
    bus = build_bus(cfg.events)
    adapter = Role1OmniAdapter(cfg=cfg.models.role1, events=bus)

    inp = MultimodalInput(
        session_id="probe-video",
        turn_id="t1",
        text=(
            "There is a handwritten or visible shopping list in this video. "
            "List every item you can read, exactly as written. If you cannot "
            "see anything, say 'no items visible'."
        ),
        videos=[VideoRef(kind="base64", value=b64, mime_type="video/mp4")],
    )

    print("\n--- calling Role 1 Omni with video ---\n")
    try:
        out = await adapter.process(inp)
    except Exception as exc:
        print("ADAPTER RAISED:", type(exc).__name__, exc)
        # Try to dig into upstream HTTP detail if it's a wrapped error
        cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        if cause is not None:
            print("  cause:", type(cause).__name__, cause)
        return 1

    print("\n--- structured output ---\n")
    print("perception_type:", out.perception_type)
    print("perception_confidence:", out.perception_confidence)
    print("transcript:", repr(out.transcript))
    print("scene_summary:", repr(out.scene_summary))
    print("user_intent_hint:", repr(out.user_intent_hint))
    print("\ndetected_items:")
    for item in out.detected_items:
        print(" -", item.model_dump())
    print("\nshopping_list payload:", out.shopping_list)
    print("\nraw_model_metadata keys:", list(out.raw_model_metadata.keys()))

    # Print the most useful raw bits
    rm = out.raw_model_metadata
    if "raw_text" in rm:
        print("\n--- raw_text (first 2000 chars) ---")
        print(rm["raw_text"][:2000])
    for key in ("parse_error", "raw_response", "raw_content", "raw"):
        if key in rm:
            print(f"\n--- {key} ---")
            print(str(rm[key])[:2000])
    if "finish_reason" in rm:
        print("\nfinish_reason:", rm["finish_reason"])
    if "model_id" in rm:
        print("model_id:", rm["model_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
