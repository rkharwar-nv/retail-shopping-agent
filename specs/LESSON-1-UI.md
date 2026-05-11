# Lesson 1 — Dev Inspector UI

**Status:** draft v1 · **Owner:** PM + platform team
**Related specs:** LESSON-1-M0-MODEL-GATEWAY, LESSON-1-SMOKE

---

## 1. Purpose

A single-page developer inspector served by the FastAPI service at
`/ui`. Purposes, in priority order:

1. **Working tool while tuning** — load an image, submit a prompt,
   see perception_type + typed payload + raw Omni response without
   leaving the browser.
2. **Demoable surface** — share a screen / URL to show stakeholders
   the system in motion without building a product UI prematurely.
3. **Trace browser** — inspect `/debug/trace/<session>` entries next
   to the parsed response, so prompt regressions are visible live.

This is **not** the end-user product UI. The shopper-facing
conversational experience is a future lesson; building it now would
couple the UI to a backend that is still growing specialists, cart,
and catalog pieces.

## 2. Domain Generality Analysis

The inspector renders **structurally** from the response JSON. New
perception types or new typed fields appear in the UI without code
changes because the renderer walks the object. Fashion-testable,
cosmetics-honest by construction.

| Aspect                | Shape                              | Grocery Phase 1 | Fashion (future) | Cosmetics (future) |
| --------------------- | ---------------------------------- | --------------- | ---------------- | ------------------ |
| payload rendering     | generic JSON walker with section   | pantry/list/label render    | fashion renders   | cosmetics renders |
| fixture dropdown      | reads `/fixtures/list` route       | populated       | populated when added | populated when added |
| trace panel           | reads `/debug/trace/<session_id>`  | same            | same             | same               |

## 3. Scope — IN / OUT

**IN v1:**
- Drag-drop or file-picker for one image
- Free-text prompt input
- Session-id field (auto-generated UUID, editable)
- "Run fixture" dropdown populated from `smoke/fixtures/*/`
- Submit button posts to `/chat`
- Parsed response panel (perception_type, confidence, typed payload,
  detected_items, scene_summary, user_intent_hint)
- Trace panel: collapsible sections for system prompt, raw upstream
  response, usage, finish_reason, duration
- Loading indicator (Omni is slow; ~10-60s per call)
- Non-2xx status surfaced clearly

**OUT v1:**
- Multi-turn / conversation history
- Audio upload
- Event-stream sidebar (events.jsonl live tail)
- Promote-to-canonical button (sa-smoke CLI covers this)
- Product cards, recipe cards, cart, checkout
- Authentication / multi-user (localhost-only assumption)

## 4. Endpoints used / added

| Method | Path                          | New? | Purpose                          |
| ------ | ----------------------------- | ---- | -------------------------------- |
| GET    | `/ui`                         | new  | Serves `index.html`              |
| GET    | `/ui/static/*`                | new  | Serves static assets             |
| GET    | `/fixtures/list`              | new  | Lists smoke fixtures             |
| GET    | `/fixtures/load/<type>/<name>`| new  | Returns base64 of a fixture      |
| POST   | `/chat`                       | exist| Main call                        |
| GET    | `/debug/trace/<session_id>`   | exist| Upstream call capture            |

`/fixtures/*` is dev-only: gated off `config.debug.enabled` like the
trace route. Returns 404 when debug is disabled so the endpoint
doesn't leak in prod.

## 5. File layout

```
src/shopping_agent/
  api/routes/
    ui.py                   # 2 routes: /ui, /ui/static/*
    fixtures.py             # GET /fixtures/list, /fixtures/load/...
  static/
    index.html
    app.js
    styles.css
```

Static files are packaged with the wheel via `package_data` — when
the service is installed, `/ui` works out of the box.

## 6. Renderer design — structural, not typed

```javascript
renderPayload(body) {
  // 1. Always show: perception_type, confidence, scene_summary,
  //    user_intent_hint, detected_items count.
  // 2. Look at body[body.perception_type] — if present, render its
  //    fields generically (section per key, list rendering for
  //    arrays, key/value grid for objects).
  // 3. Unknown keys appear at the bottom under "other fields" —
  //    visible but not prominent.
}
```

A new field on `pantry` (say, `dietary_flags`) appears automatically.
A new perception type (say, `cosmetics`) renders via the same walker
once the backend starts populating it. UI does not need to know the
schema ahead of time.

## 7. Open questions

- **Q-UI-1:** Should the inspector persist recent runs to localStorage?
  Leaning **yes** — cheap, lets you compare "this run" vs "previous"
  without backend state. v2.
- **Q-UI-2:** Should fixture image preview render inline?
  Leaning **yes** for v1 — part of the input panel.
- **Q-UI-3:** Do we auto-refresh the trace panel after submit?
  Yes — fetch trace in the same tick we render the chat response.

## 8. Non-goals (explicit)

This UI is **not**:
- A replacement for `sa-smoke` (batch + scripted)
- A replacement for the FastAPI `/docs` Swagger (API contract viewer)
- A production surface (no auth, no CSRF, localhost scope)
