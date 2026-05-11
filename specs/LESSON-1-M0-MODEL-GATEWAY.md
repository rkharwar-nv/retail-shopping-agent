# M0 — Model Gateway (Spec v1)

**Lesson 1, part 1 of 3.** Platform module. Audience: engineer
implementing the platform.

## Purpose

M0 is the single boundary between the rest of the agent and any
external model. It defines a uniform interface so Role 1, Role 2,
and Role 3 can each be swapped independently without changing
callers.

## Scope

**In scope:** synchronous HTTP calls to chat, embedding, and
multimodal endpoints. Per-provider adapters. Credential handling
via M-SEC. Timeout, retry, and error normalization.

**Out of scope (Phase 1):** streaming responses, response caching,
rate-limit coordination, model A/B testing, fine-tuning hooks.

## Concepts

```
  ModelGateway
  ├── role1: InputProcessingAdapter     (multimodal → structured)
  ├── role2: ReasoningAdapter           (text + tools → response/tool calls)
  └── role3: EmbeddingAdapter           (text → vector)
```

Each adapter implements one interface. Callers hold a typed
reference to exactly one role; an adapter wired into the wrong
slot is a compile/startup error, not a runtime surprise.

## Interfaces (v1)

### InputProcessingAdapter (Role 1)

```
  process(input: MultimodalInput) -> StructuredUnderstanding

  MultimodalInput {
    images:  ImageRef[]        # 0..N, URLs or base64
    audio:   AudioRef?         # optional
    text:    string?           # optional user utterance
    session_id: string
    turn_id:    string
  }

  StructuredUnderstanding {
    schema_version: 1
    transcript:     string?         # ASR output if audio present
    detected_items: DetectedItem[]  # from images
    scene_summary:  string?         # free-text scene description
    user_intent_hint: string?       # model's best guess at intent
    raw_model_metadata: object      # provider-specific, opaque
  }
```

### ReasoningAdapter (Role 2)

```
  reason(ctx: ReasoningContext) -> ReasoningStep

  ReasoningContext {
    schema_version:  1
    understanding:   StructuredUnderstanding
    conversation:    Turn[]        # prior turns, trimmed to context window
    tools:           ToolSchema[]  # registered tools (see M2)
    profile:         Profile       # from H3 hook (empty in Phase 1)
    session_id:      string
    turn_id:         string
  }

  ReasoningStep =
    | { kind: "tool_call", calls: ToolCall[] }
    | { kind: "final",     response: ResponseEnvelope }   # see M3
```

Role 2 speaks a neutral tool-call dialect. The adapter translates
to/from the provider's native dialect (OpenAI-style is the common
case). Callers never see provider-specific shapes.

### EmbeddingAdapter (Role 3)

```
  embed(texts: string[]) -> Vector[]

  Vector = float[]     # length = model's embedding dimension

  Invariant: all vectors used in a single index MUST come from
  the same embedding model. Switching Role 3's model requires
  re-indexing the catalog (M7). This is enforced by M6 tagging
  each index with the embedding model_id that produced it.
```

## Configuration

Non-secret fields come from `config.yaml`; secrets come from
environment variables. Each role has an independent config block
(see `config.example.yaml`). Loader rules:

- Fail fast at startup if any required API key env var is unset.
- Never log key values, never include them in events.
- Values in env override values in file (standard precedence).
- Role 2 and Role 3 may share a key value via env; the code must
  still treat them as separate credentials (no global singleton).

## Failure modes

| Condition | Behavior |
|-----------|----------|
| Missing API key at startup | Hard fail with explicit message |
| Network timeout | Retry per `max_retries`, then raise `ModelTimeoutError` |
| 4xx from provider | No retry. Raise `ModelRequestError` with redacted detail |
| 5xx from provider | Retry with backoff, then raise `ModelProviderError` |
| Malformed provider response | Raise `ModelResponseError`, include raw metadata |
| Wrong adapter in slot | Startup error, not runtime |

## Events Emitted

All events carry `session_id`, `turn_id`, `trace_id`,
`schema_version`.

| Event | When |
|-------|------|
| `model.call.started` | Just before HTTP request |
| `model.call.succeeded` | On 2xx with parseable body |
| `model.call.failed` | On any terminal failure |
| `model.call.retried` | On each retry attempt |

All events include `role` (1/2/3), `provider`, `model_id`, and
`duration_ms`. Events never include: prompt text, response text,
API keys, raw images/audio.

## Domain Generality Analysis

| Aspect | Grocery (now) | Fashion (check) | Cosmetics (honest) |
|--------|---------------|-----------------|--------------------|
| Role 1 multimodal input | image + audio + text | same | same |
| Role 2 reasoning + tools | same | same | same |
| Role 3 text embeddings | same | same (text) | same (text) |
| Image embeddings later | deferred | likely needed (visual search) | likely needed (shade match) — TBD |
| Provider diversity | 3 NVIDIA | may add vision specialists | may add domain-tuned — TBD |

The adapter pattern generalizes. Adding image embeddings later
means a new `ImageEmbeddingAdapter` slot on the gateway — same
shape, new role. No existing interface changes.

## Phase-1 reference implementation notes

- One Python/Node module per adapter file. No shared base class
  with provider-specific branches — that's how adapters get dirty.
- Adapters are constructed once at startup from the resolved
  config and injected into the gateway. No ambient globals.
- HTTP client: any OpenAI-compatible SDK works for Role 2 and
  Role 3. Role 1 (Omni) may need a custom client for the
  multimodal request body — verify on first call.

## Open questions

- Exact request body shape for Nemotron 3 Nano Omni: verify
  against NVIDIA's NIM docs on first integration.
- Does `inference-api.nvidia.com/v1` accept the OpenAI
  `/chat/completions` and `/embeddings` paths as-is, or does
  it require provider-specific paths? Verify on first call.
- Retry backoff policy: exponential vs. fixed? Phase 1 default:
  exponential, 250ms → 500ms → 1000ms.
