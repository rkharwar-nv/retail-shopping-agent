"""ASL capability probe — sends shoppinglist_video1.mp4 to Omni
with three different prompts, dumps raw model text + reasoning."""

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

# We bypass the structured-JSON adapter and call the OpenAI client
# directly so the model is free to answer in plain text and we can
# also see its reasoning trace.
from openai import AsyncOpenAI  # noqa: E402

from shopping_agent.config import load_config  # noqa: E402

PROBES = [
    (
        "P1_neutral",
        "Describe everything you see in this video, including any hand "
        "gestures, facial expressions, body language, signs, on-screen "
        "text, and what the person appears to be doing. Be exhaustive."
    ),
    (
        "P2_direct_ASL",
        "The person in this video is using American Sign Language to "
        "list grocery items they want to buy. Translate the signs they "
        "make, in order, into a written list of grocery items. If you "
        "are not sure of a sign, say so explicitly. Do not skip any sign."
    ),
    (
        "P3_adversarial",
        "Look carefully at the person's hands and face in this video. "
        "Are they using a sign language? If yes, which sign language "
        "do you believe it is, and what do you think they are "
        "communicating? If you cannot tell, say 'I cannot tell.' Do "
        "not guess."
    ),
]


async def run_probe(client, model_id, b64, prompt):
    msg_content = [
        {"type": "text", "text": prompt},
        {
            "type": "video_url",
            "video_url": {"url": f"data:video/mp4;base64,{b64}"},
        },
    ]
    resp = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": msg_content}],
        max_tokens=4000,
        temperature=0.2,
    )
    choice = resp.choices[0]
    text = (choice.message.content or "").strip()
    reasoning = getattr(choice.message, "reasoning", None) or ""
    return {
        "text": text,
        "reasoning": reasoning,
        "finish_reason": choice.finish_reason,
        "model": resp.model,
    }


async def main():
    fixture = ROOT / "smoke/fixtures/shopping_list/shoppinglist_video1.mp4"
    raw = fixture.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"video: {fixture.name}  size: {len(raw)} bytes\n")

    cfg = load_config()
    role1 = cfg.models.role1
    api_key = os.environ.get(role1.api_key_env or "", "")
    if not api_key:
        print(f"missing API key in env var: {role1.api_key_env}", file=sys.stderr)
        return 2

    client = AsyncOpenAI(api_key=api_key, base_url=role1.base_url, timeout=180)

    for name, prompt in PROBES:
        print("=" * 72)
        print(name)
        print("=" * 72)
        print("PROMPT:", prompt[:200], "...\n" if len(prompt) > 200 else "\n")
        try:
            r = await run_probe(client, role1.model_id, b64, prompt)
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}\n")
            continue
        print("--- model answer ---")
        print(r["text"][:2500])
        if r["reasoning"]:
            print("\n--- reasoning trace (first 4000 chars) ---")
            print(str(r["reasoning"])[:4000])
        print(f"\nfinish_reason: {r['finish_reason']}    model: {r['model']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
