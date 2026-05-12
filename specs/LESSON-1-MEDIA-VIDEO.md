# Lesson 1 — Video Intake (MP4 → Omni)

**Status:** draft v1
**Owner:** PM + platform team
**Related specs:** LESSON-1-M0-MODEL-GATEWAY, LESSON-1-UI v2

## 1. Purpose

Let a user attach a short MP4 video to a chat turn and have Nemotron 3
Nano Omni reason over it the same way it does over an image. The
target use case is grocery / pantry video walkthroughs: "here's what's
in my fridge, what should I cook?" — a single 10–30 second clip is
richer signal than any one still frame.

We ship Pattern A: **server-side decode**. The composer base64-encodes
the MP4 and we hand the encoded blob to the NIM endpoint as a data URL.
vLLM, configured with
`--media-io-kwargs '{"video": {"fps": 2, "num_frames": 256}}'`, samples
frames upstream. We do **not** ship a client-side or gateway-side
frame extractor in Phase 1.

## 2. Scope (Phase 1 + grocery)

- Single MP4 video per turn, mixed with optional text.
- Wire through the existing `/chat` Role 1 path — no new endpoint.
- Show the submitted video back in the user's chat bubble.
- Reuse the existing perception classifier; the same five
  `perception_type` verticals apply, just sourced from video frames.
- Surface video metadata (count, byte size) in `/debug/trace` next to
  the existing image/audio metrics.

## 3. Out of scope

- Multi-video turns (>1 video per request → 4xx).
- Audio extraction from the MP4 audio track. Until the audio adapter
  open question is resolved (see M0 spec), the audio stream is
  effectively discarded by the model.
- Live camera capture in the browser (Phase 2).
- Client-side frame sampling or transcoding.
- HLS / DASH / streaming inputs. MP4 only.

## 4. Request shape (POST /chat with videos)

The existing JSON envelope grows one optional field:

```json
{
  "session_id": "sess-…",
  "text": "what's in my fridge?",
  "images": [],
  "videos": [
    {
      "kind": "base64",
      "value": "<base64 of MP4 bytes, no data: prefix>",
      "mime_type": "video/mp4"
    }
  ]
}
```

`videos` is a list to mirror `images`, but the API rejects requests
where `len(videos) > 1` with `ModelRequestError`. `kind: "url"` and
`kind: "path"` are accepted for parity with `ImageRef` but the UI only
emits `base64`.

## 5. Wire format to Nemotron Omni (content blocks)

The Role 1 adapter assembles the OpenAI-style `messages[].content`
list for the user turn in this order:

1. `{"type": "text", "text": "<user text>"}` — if any.
2. One `{"type": "image_url", "image_url": {"url": …}}` block per image.
3. One `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}` block per video.
4. An optional audio placeholder text block (unchanged, see M0 spec
   open question).

The `video_url` content type follows NVIDIA NIM convention as of
the docs we have; the *exact* contract on
`integrate.api.nvidia.com/v1` is unverified — see §9.

## 6. Limits & guards

- 1 video per turn — enforced in `role1_omni.py` before any upstream
  call. Returning `ModelRequestError` keeps this in the
  not-retried, 4xx-class branch.
- 25 MB max base64-**decoded** size per video. Enforced
  server-side. The client mirrors the same cap so the rejection is
  caught before bytes leave the browser.
- Format: `video/mp4` is the only accepted MIME at the UI layer. The
  backend `VideoRef.mime_type` defaults to `video/mp4` but does not
  hard-validate — that's the UI's job.
- Server-side sampling: NIM is launched with `fps=2`,
  `num_frames=256`. Effective max useful duration is
  `256 / 2 = 128 seconds`. Clips beyond that get truncated upstream;
  we don't reject them at our boundary, we just log it.

## 7. Failure modes & user feedback

| Failure | Where caught | User-visible result |
|---------|--------------|---------------------|
| File > 25 MB | Client (before read) | Status: "video too large (max 25 MB)". No POST issued. |
| Wrong MIME (e.g. .mov) | Client (file picker) | Status: "unsupported file type". No attachment set. |
| >1 video in payload | API (role1_omni) | 4xx; UI renders red error card. |
| Decoded > 25 MB at server | API (role1_omni) | 4xx; UI renders red error card. |
| Endpoint rejects `video_url` | Upstream 4xx/5xx | Red error card: "Video reasoning failed: <err>. The endpoint may not yet support video input — try an image instead." |
| Long-running call (30–90s normal) | UI status line only | "calling /chat (Omni — video reasoning, 30-90s)…" |

## 8. Domain Generality Analysis

Each vertical is asked: *does the video pathway add signal the still
pathway didn't already give us?* If the answer is "marginal at best,"
we don't promote video as a first-class flow for that vertical even
though it's structurally accepted.

| Vertical | Adds signal? | Why | Phase 1 promotion |
|----------|--------------|-----|-------------------|
| pantry | **Yes — strong** | Multi-shelf walkthrough captures more than one still: occlusions resolve, fridge interior + door visible together. | Yes — primary use case. |
| shopping_list | No | A list is a still image. A waving phone over a list adds noise, not signal. | No — keep image-only in UI hints. |
| food_label | Marginal | A panning shot might cover front + nutrition label, but stills do this with less risk of motion blur. | Optional — accept, but don't recommend. |
| fashion | **Yes — moderate** | Video shows drape, fit, and movement; a still flattens texture and silhouette. | Yes — Phase 1 acceptable. |
| cosmetics | No | Phase 1 cosmetics is identity-only (`product_type` + `brand` + notes). A video adds no extraction signal until we build true cosmetics analysis. | No — accept, but don't surface in UI prompts. |

Conclusion: pantry and fashion benefit. Shopping-list and cosmetics
are tolerated but not promoted in the UI's example prompts.

## 9. Risks & open questions

- API contract on `integrate.api.nvidia.com` unverified for the
  `video_url` content type — ship with loud failure, iterate from
  logs. We accept the chance that the first production call fails
  with a 4xx and we have to flip to `media_url`, `input_video`, or a
  separate endpoint. Fix is one adapter edit.
- Latency: each call is 30–90s depending on clip length and
  `num_frames`. Existing per-call timeout in `ModelRoleConfig` may
  need to be widened. Default in config today is too low for the
  upper end. Tracked as a follow-up to this spec.
- Decoded-byte guard uses `len(base64.b64decode(...))`; pathological
  base64 padding edge cases could mis-count by a few bytes. Not a
  security concern at the 25 MB scale, just a precision footnote.
- No virus / content scan on uploaded video. Same posture as for
  images today. Re-evaluate if we ever persist videos beyond the
  in-memory turn.

## 10. Future work (Phase 2)

- Frame-sampling fallback in the gateway, used if server-side decode
  turns out to be unavailable or too slow. Would extract N frames at
  even intervals and send as a sequence of `image_url` blocks.
- Audio extraction from the MP4 audio track for a separate
  transcription pass once the Role-1 audio open question lands.
- Live camera capture in the UI — `getUserMedia` + MediaRecorder,
  capped to 30s, encoded as fragmented MP4 in-browser.
- Multi-video turns (two videos as a before/after comparison).
- Server-side persistence for replay / debug-trace deep-dives.
