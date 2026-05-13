# scripts/ — operational probes

Throwaway-but-useful diagnostic scripts. Not part of the package, not
covered by tests. Each one is self-contained — run with the venv:

    .venv/bin/python scripts/<name>.py

## Video pipeline probes

These exist because we shipped MP4 upload through the UI and the
user-facing symptom ("video isn't being processed") was misleading.
The probes told the truth in 60 seconds.

### probe_video.py
Sends a fixture MP4 through the real Role 1 adapter (`Role1OmniAdapter`)
to `https://integrate.api.nvidia.com/v1` and prints the structured
output. Use this to verify the whole transport path end-to-end:

  fixture file → base64 → VideoRef → adapter → OpenAI client →
  build.nvidia.com NIM → vLLM frame sampling (fps=2, num_frames=256)
  → model → JSON response → adapter parse → StructuredUnderstanding

If this returns sensible scene_summary/detected_items, the pipeline is
working. If it errors, you have a wire-format bug.

### probe_video_http.py
Same call, but monkey-patches `httpx.AsyncClient.send` to capture the
exact HTTP body that goes out and the raw response that comes back
(with base64 redacted to keep printable). Use this when probe_video.py
returns "wrong" output and you need to see whether the issue is on the
request side, the response side, or in our adapter parsing.

### probe_asl.py
Sends a single video to Omni with three different prompts (neutral
description, direct ASL translation request, adversarial "is this sign
language?") and dumps both the model answer AND the reasoning trace.
Built specifically to test whether Nemotron 3 Nano Omni recognizes
American Sign Language.

## What we learned 2026-05-12

Running these probes against `smoke/fixtures/shopping_list/shoppinglist_video1.mp4`
(an 8-second clip of a person signing in ASL at a grocery aisle, with
on-screen "GAZEN MILK" / "G MILK" text overlays):

1. **Video transport works.** MP4 reaches build.nvidia.com NIM. vLLM
   samples frames at fps=2 server-side. Omni reasons over them.

2. **The fixture has NO audio stream.** `ffprobe` confirms zero audio.
   So pipelines that try to extract dialogue from this clip will fail
   regardless — there is nothing there to extract.

3. **Omni describes hand gestures frame-by-frame** (e.g. "She forms an
   'OK' sign with both hands") but does NOT translate ASL into a
   structured grocery list. Even with explicit "the person is signing
   ASL, translate to a list" prompting, the reasoning trace shows the
   model speculating about individual hand shapes ("this is the sign
   for I/me", "this looks like the number 3") rather than fluently
   recognizing signed words.

4. **Conclusion:** Sign-language recognition is NOT a Phase 1 capability
   of Nemotron 3 Nano Omni. The video pipeline is fine. ASL → grocery
   list is a real Phase 2 product feature that needs either:
     - a different model purpose-built for ASL,
     - a sign-language recognition tool the agent can call, or
     - a graceful "I see you're signing — please type or upload a
       written list" fallback.

5. **On-screen text** in video frames DOES come through as
   `detected_items` (Omni OCR'd "gazen milk" and "G milk" from the
   graphics). That's available today if the use case is captioned
   product videos.
