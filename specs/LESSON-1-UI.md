# Lesson 1 — Dev Inspector UI (v2: Chat Experience)

**Status:** draft v2 (supersedes v1 inspector-only design)
**Owner:** PM + platform team
**Related specs:** LESSON-1-M0-MODEL-GATEWAY, LESSON-1-SMOKE

---

## 1. Purpose

A single-page chat experience at `/ui` that:

1. **Looks like a chat** — bubble-style message list, composer with
   file + text input. Stakeholders recognize it as a chatbot.
2. **Renders each perception type richly** — pantry, shopping_list,
   food_label, fashion, cosmetics, unknown each get a purpose-built
   card, not a generic JSON dump.
3. **Shows the agent working** — a live "Agent Activity" panel
   displays LLM calls per model, tokens, latency, agents/sub-agents
   active, and a per-turn timeline. The panel is DESIGNED to grow
   as Role 2 + specialists come online.
4. **Preserves debuggability** — the old inspector (system prompt,
   raw upstream response, trace) is accessible as a drawer from
   the chat UI, not a separate route.

The UI is NVIDIA-branded (green #76B900 / black / white / gray
palette) using Open Sans + JetBrains Mono. It is NOT a product UI
for end shoppers; it is a technical demo + working dev tool.

## 2. Domain Generality Analysis

| Aspect              | Shape                                      | Grocery Phase 1 | Fashion (future) | Cosmetics (future) |
| ------------------- | ------------------------------------------ | --------------- | ---------------- | ------------------ |
| message rendering   | one card component per perception_type     | 3 cards live    | 1 card ready     | 1 card ready       |
| fixture dropdown    | reads `/fixtures/list` (dev-gated)          | pantry/list/label fixtures | fashion fixtures drop in | cosmetics fixtures drop in |
| activity panel      | reads events + SSE stream, renders slots   | Role 1 only     | adds fashion specialist | adds cosmetics specialist |
| agent roster        | list of active agents + sub-agents         | Role 1          | + Role 2 + specialists | + Role 2 + specialists |

## 3. Scope — v2 IN / OUT

**IN v2 (this push):**
- Chat-bubble layout, multi-turn backbone (SessionStore-backed)
- Image + text input (image alone allowed; text alone allowed)
- Per-perception-type rich card renderers
- Activity panel: per-turn + session-aggregate counters
- Live updates via SSE (`/events/stream/<session_id>`)
- Inspector drawer (trace view of last upstream call)
- NVIDIA brand colors + typography
- Fixture dropdown (dev-only, from /fixtures/list)

**DEFERRED:**
- Audio upload (will land after chat is solid — user's sequencing)
- Video upload (Phase 2 of PRD)
- Agent decision loop (question-router) — Lesson 2
- Role 2 reasoning — Lesson 3
- Catalog resolution / product cards — Lesson N
- Authentication — production concern

## 4. Multi-turn semantics (v2)

For v2 the UI renders conversation structure and SessionStore
persists prior turns, but Role 1 (perception) does not reason
over history. Why:

- Role 1 is a perception model; conversation is Role 2's job.
- Wiring the **history delivery backbone** now means when Role 2
  lands, it just reads `session.turns` — no UI or storage change.
- Each Role 1 call still acts on the new image+text. Previous
  turns are included as a "session summary" prefix in the system
  prompt (not as full conversation context).

This is deliberately limited and documented so it doesn't
surprise downstream lessons.

## 5. Endpoints used / added

| Method | Path                                | Status   | Purpose                          |
| ------ | ----------------------------------- | -------- | -------------------------------- |
| GET    | `/ui`                               | existing | Chat shell (redesigned)          |
| GET    | `/ui/static/*`                      | existing | Static assets                    |
| POST   | `/chat`                             | existing | Message submission               |
| GET    | `/sessions/{sid}`                   | existing | Full turn history                |
| GET    | `/sessions/{sid}/stats`             | **new**  | Aggregated counters (calls, tokens, latency) |
| GET    | `/events/stream/{sid}`              | **new**  | Server-Sent Events for live UI   |
| GET    | `/fixtures/list`                    | existing | Dev fixture browser              |
| GET    | `/fixtures/load/...`                | existing | Load fixture as base64           |
| GET    | `/debug/trace/{sid}`                | existing | Raw upstream call capture        |

`/sessions/{sid}/stats` and `/events/stream/{sid}` are both
dev-gated off `config.debug.enabled` like the trace route.

## 6. Activity panel data contract

The panel reads from `/sessions/{sid}/stats` on load and then
subscribes to `/events/stream/{sid}` for live updates. Shape:

```json
{
  "session_id": "sess-abc123",
  "turns": 2,
  "calls_by_model": {
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {
      "calls": 3,
      "prompt_tokens": 1204,
      "completion_tokens": 3841,
      "reasoning_tokens": 2106,
      "total_latency_ms": 42600
    }
  },
  "calls_by_role": {
    "role1": 3
  },
  "agents_active": ["role1"],
  "sub_agents": [],
  "timeline": [
    {"t_ms": 0,     "event": "user.submit",       "turn_id": "t-1"},
    {"t_ms": 120,   "event": "role1.start",       "turn_id": "t-1"},
    {"t_ms": 14320, "event": "role1.done",        "turn_id": "t-1",
     "duration_ms": 14200}
  ]
}
```

Schema is additive. Fields that don't exist yet (Role 2 aggregates,
specialist rollups) just appear when those roles come online.

## 7. SSE event stream contract

`GET /events/stream/<sid>` emits Server-Sent Events. Each event
is a JSON object matching one of the existing bus event types
(EV_MODEL_CALL_STARTED, EV_MODEL_CALL_SUCCEEDED, EV_MODEL_CALL_FAILED,
EV_TURN_STARTED, EV_TURN_COMPLETED). The stream is scoped to the
session — events from other sessions are filtered server-side.

Client reconnection is handled by the browser natively; no replay
on reconnect in v2 (last-event-id is v3 work).

## 8. Renderer design — per-perception cards

Each perception type has its own renderer function. Dispatch:

```javascript
const RENDERERS = {
  pantry:        renderPantryCard,
  shopping_list: renderShoppingListCard,
  food_label:    renderFoodLabelCard,
  fashion:       renderFashionCard,
  cosmetics:     renderCosmeticsCard,
  unknown:       renderUnknownCard,
};
```

Each renderer takes the typed payload + common fields (scene_summary,
user_intent_hint) and returns a DOM fragment shaped for that domain:

- pantry: items list + "what's missing" section + suggested uses
- shopping_list: transcribed list + ambiguous lines called out
- food_label: nutrition-facts-style grid + ingredients list +
  allergens callout
- fashion: garment attributes column + style descriptors
- cosmetics: product identity + attributes
- unknown: scene summary prominent + raw detected_items list

Each card has a small "show raw JSON" expander at the bottom so
nothing is hidden.

## 9. NVIDIA branding

Colors:
- NVIDIA Green `#76B900` — primary, accents, CTAs
- Black `#000000` — top nav, emphasis text
- White `#FFFFFF` — card surfaces
- Light gray `#F7F7F7` — app background
- Medium gray `#767676` — secondary text
- Dark gray `#333333` — body text

Typography:
- Open Sans (public web fallback for NVIDIA Sans)
- JetBrains Mono for code, traces, timestamps

No actual NVIDIA logo asset bundled. A styled green accent square
(CSS-only) signals the brand.

## 10. Open questions

- **Q-UI-4:** Where does the "new turn" boundary get drawn when
  the user uploads a new image mid-conversation? Leaning: every
  submit = a new turn.
- **Q-UI-5:** Should the inspector drawer close on new turn or
  persist?  Leaning: persist; user explicitly closes it.
- **Q-UI-6:** SSE vs WebSocket — SSE is simpler and fits one-way
  server→client. Going SSE for v2; revisit if we need bidirectional
  (cancellation, user-side streams) later.

