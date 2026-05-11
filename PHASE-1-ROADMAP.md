# Phase 1 Roadmap — Multimodal Retail Shopping Agent

**Status:** Draft · **Date:** May 2026 · **Owner:** (you)
**Source PRD:** `/home/ubuntu/PRD/Retail_Shopping_Agent_PRD.docx`

---

## 1. Goal

Build a scaffolding + one vertical (grocery) that proves the pattern
and extends to fashion/cosmetics/home later without rewrite.

**Phase 1 acceptance:** the *Pantry-to-Plate* journey works end-to-end.

Emily takes 1–3 photos of her pantry/fridge (images), asks "what
can I make?" (audio or text), agent returns recipe ideas and a gap
list, she adds missing items to cart (voice or tap).

> Phase 1 inputs: **image + audio + text**. Video deferred —
> images give the same demo value with a fraction of the
> engineering. Adding video later is a Role 1 adapter change,
> nothing else.

## 2. Non-goals (Phase 1)

- Fine-tuning any model
- Fashion, cosmetics, home goods verticals
- Returns, substitution, proactive re-order, snap-and-swap
- Real retailer catalog integration
- Production guardrails / events / profile / consent (hooks only)
- Image embeddings (text-only in Phase 1)

## 3. Architecture (three model roles + scaffolding)

```
 Consumer (video/audio/text)
        |
   ROLE 1: Multimodal Input Adapter    [swappable, HTTP]
        |  (structured understanding)
        v
   ROLE 2: Reasoning + Tool-Calling    [swappable, HTTP]
        |        |
     tools    response
        |        |
        v        v
    Tools      Response Renderer (U1)
        |
        v
   catalog_search -> ROLE 3b: Query Embed -> Vector Store
                                                 ^
                                                 |
         ROLE 3a: Index Embed  <--- Catalog Ingest (offline)
```

All three roles are swappable via per-provider **adapters**. All
reached over HTTP (local or remote, same code path).

## 4. Modules (Phase 1)

### Platform (build)
| ID | Name | Purpose |
|----|------|---------|
| M0 | Model Gateway | Role 1 & 2 adapter interface |
| M1 | Conversation State | turn history, context window mgmt |
| M2 | Tool Registry | define/register/call tools by JSON schema |
| M3 | Response Envelope | canonical output shape any specialist returns |
| M4 | Specialist Registry | how a vertical plugs in (grocery now, fashion later) |
| M5 | Embedding Gateway | Role 3 adapter (same-model invariant) |
| M6 | Vector Store Interface | pgvector default, swappable |
| M7 | Catalog Ingest Pipeline | offline: embed + index catalog |
| M8 | Product Store | canonical Product schema at rest |
| M-SEC | Secrets Config | env var in Phase 1, Vault-ready interface |
| M-EVENTS | Event Bus | real module, not a hook — see §4.1 |

### M-EVENTS — Event Bus (first-class in Phase 1)

Events are the data flywheel. Sessions run without events = training
data lost forever. Spec'd properly now, not retrofitted later.

- **Schema:** versioned (`schema_version: 1`), all 7 PRD §12 layers
  defined up front even if unused
- **Named emission points:** `session_start`, `turn_received`,
  `tool_called`, `tool_returned`, `response_sent`, `session_end`,
  `consent_requested`, `error`
- **Interface:** `publish(event)` only. Phase 1 impl appends JSONL
  to a file; same interface swaps to Kafka/PubSub/Kinesis later
- **Correlation IDs:** every event carries `session_id + turn_id +
  trace_id`. Non-negotiable.
- **PII stance:** raw PII never in events. Schema decides per-field
  what is hashed / redacted / dropped. Decided once, in Phase 1.
- **Non-blocking:** bus failure never blocks a turn. Buffered or
  dropped with a counter.
- **Every module spec includes an "Events Emitted" section**
  listing which events fire from that module and when.

### Empty hooks (design-now-implement-later)
| ID | Name | Phase 1 impl |
|----|------|--------------|
| H1 | Guardrails Hook | no-op pass-through |
| H3 | Profile Hook | returns empty profile |
| H4 | Consent Hook | always "granted" |

### Grocery tenant (first specialist)
| ID | Name |
|----|------|
| GS | Grocery Specialist (implements M4) |
| T0 | catalog_search (uses M5 + M6) |
| T1 | pantry_state |
| T2 | recipe_lookup |
| T3 | cart_ops |

### UI + Data + Journey
| ID | Name |
|----|------|
| U1 | Response Renderer (renders any M3 payload) |
| D1 | Seed Catalog (Open Food Facts + synthetic, ~1000 items) |
| J1 | Pantry-to-Plate end-to-end acceptance |

## 5. Dependency graph

```
  M-SEC --> M0, M5
  M0 --> M1, M2, M3
  M3 --> M4 --> GS
  M6, M5, M8 --> M7 --> D1
  M2 + T0..T3 --> GS
  H1..H4 attach at M0/M3 boundaries
  GS + U1 + D1 --> J1 (the demo)
```

## 6. Pluggability matrix

| Role | Swap mechanism | Runtime-swappable? |
|------|----------------|---------------------|
| Role 1 (multimodal) | provider adapter + URL + key | yes |
| Role 2 (reasoning) | provider adapter + URL + key | yes |
| Role 3 (embedding) | provider adapter | **no — requires re-index** |
| Vector DB (M6) | driver swap | config-time (data migration) |
| Specialist (M4) | registry | runtime (add vertical = add specialist) |

## 7. Discipline: Fashion-Testable, Cosmetics-Honest

Every spec must include a **Domain Generality Analysis** table:

| Aspect | Grocery (now) | Fashion (check) | Cosmetics (honest) |
|--------|---------------|-----------------|--------------------|
| ... | concrete | must-also-work | mark TBD if unknown |

Three extension patterns allowed:
1. **Open map** — `attributes: { ... }` for bag-of-stuff fields
2. **Tagged union** — `{ domain: "grocery", ... }` when shapes differ
3. **Named hook** — empty extension point for cross-cutting concerns

If a spec can't pass the fashion test, it's not done. If cosmetics
is unknown, mark it TBD with an escape hatch — don't guess.

## 8. Learning path (6 lessons)

| # | Spec | Teaches |
|---|------|---------|
| 1 | M0 + M3 + M4 | spec-as-contract, extension points, fashion test |
| 2 | M-EVENTS | event schema, emission points, versioning, PII |
| 3 | M1 + M2 | stateful systems, tool schemas |
| 4 | GS + T0-T3 | plug-in within platform, domain split |
| 5 | U1 | consumer-visible render contract |
| 6 | J1 | system-level end-to-end acceptance |

## 9. Open questions

- Role 2 model pick (Claude? GPT? Llama Nemotron? Mistral?)
  → affects tool-call dialect (OpenAI-style vs Anthropic-style)
- Deployment target (local dev only? cloud? on-prem?)
- Demo deadline (if any)
- Who reviews specs besides you

## 10. Explicit deferrals

Guardrails impl · Profile impl · Consent impl ·
Substitution engine · Proactive re-order · Returns · Three other
verticals · Image embeddings · Fine-tuning · Snap-and-swap ·
Real retailer catalog integration

## 11. Interface versioning policy

- All module interfaces and event schemas are versioned (v1, v2…).
- Phase 1 ships v1 of everything.
- Breaking changes require a new version; old version stays live
  until all callers migrate.
- Every spec includes: (a) current version, (b) an "Events Emitted"
  section, (c) a "Failure Modes" section.
