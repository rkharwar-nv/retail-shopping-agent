"""Probe what HTTP request actually gets sent to build.nvidia.com when
we call Role 1 Omni with a video. We monkey-patch httpx so we can
inspect the request body before send and the raw response after.

Usage: .venv/bin/python scripts/probe_video_http.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

import httpx  # noqa: E402

# Patch httpx so we capture the outgoing request body BEFORE it's sent
# and the raw response BEFORE it's parsed.
_orig_send = httpx.AsyncClient.send

CAPTURE: dict = {}


async def _spy_send(self, request, **kw):
    CAPTURE["request_method"] = request.method
    CAPTURE["request_url"] = str(request.url)
    body = request.content or b""
    try:
        parsed = json.loads(body)
        # Redact base64 video for printability, keep length
        msgs = parsed.get("messages") or []
        for m in msgs:
            c = m.get("content")
            if isinstance(c, list):
                for part in c:
                    for k in ("image_url", "video_url", "audio_url"):
                        if k in part:
                            url = (part[k] or {}).get("url", "")
                            if url.startswith("data:"):
                                head = url.split(",", 1)[0]
                                body_part = url.split(",", 1)[1] if "," in url else ""
                                part[k]["url"] = (
                                    f"{head},<{len(body_part)} chars base64 redacted>"
                                )
        CAPTURE["request_body_redacted"] = parsed
    except Exception as e:
        CAPTURE["request_body_parse_error"] = str(e)
        CAPTURE["request_body_len"] = len(body)
    resp = await _orig_send(self, request, **kw)
    CAPTURE["response_status"] = resp.status_code
    try:
        # peek; we still want the caller to be able to read it
        text = resp.text
        CAPTURE["response_text_first_4000"] = text[:4000]
        try:
            CAPTURE["response_json_keys"] = list(json.loads(text).keys())
        except Exception:
            pass
    except Exception as e:
        CAPTURE["response_read_error"] = str(e)
    return resp


httpx.AsyncClient.send = _spy_send

from shopping_agent.config import load_config  # noqa: E402
from shopping_agent.events.bus import build_bus  # noqa: E402
from shopping_agent.gateway.base import (  # noqa: E402
    MultimodalInput,
    VideoRef,
)
from shopping_agent.gateway.role1_omni import Role1OmniAdapter  # noqa: E402


async def main() -> int:
    fixture = ROOT / "smoke/fixtures/shopping_list/shoppinglist_video1.mp4"
    raw = fixture.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"video: {fixture.name}  size: {len(raw)} bytes")

    cfg = load_config()
    bus = build_bus(cfg.events)
    adapter = Role1OmniAdapter(cfg=cfg.models.role1, events=bus)

    inp = MultimodalInput(
        session_id="probe-video",
        turn_id="t1",
        text=(
            "There is a handwritten or visible shopping list in this video. "
            "List every item you can read, exactly as written. Be thorough."
        ),
        videos=[VideoRef(kind="base64", value=b64, mime_type="video/mp4")],
    )

    try:
        out = await adapter.process(inp)
        print("\n--- Adapter returned: perception_type =", out.perception_type)
        print("scene_summary:", repr(out.scene_summary)[:500])
    except Exception as e:
        print("ADAPTER ERR:", type(e).__name__, e)

    print("\n=== HTTP request that was sent ===")
    print("URL:", CAPTURE.get("request_url"))
    rb = CAPTURE.get("request_body_redacted")
    if rb is not None:
        print(json.dumps(rb, indent=2)[:6000])

    print("\n=== HTTP response ===")
    print("status:", CAPTURE.get("response_status"))
    txt = CAPTURE.get("response_text_first_4000")
    if txt:
        print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
