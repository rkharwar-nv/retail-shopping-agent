# Chat UI — Handoff Note

**Status:** partial. Backbone + HTML shell done. CSS + JS outstanding.
**Date:** 2026-05-12
**Blocker encountered:** model output-token cap on long CSS/JS emissions.

---

## What is already done

### Commit `f2d0188` — UI backbone (pushed)
- `src/shopping_agent/events/broadcaster.py` — `BroadcastSink` wraps any
  inner sink, fans events out to subscribers, keeps per-session replay.
- `src/shopping_agent/events/bus.py` — `build_bus` always wraps inner
  sink; `bus.broadcaster` accessor added.
- `src/shopping_agent/api/routes/events_stream.py` — two new routes,
  both 404 when `config.debug.enabled` is false:
    - `GET /sessions/<sid>/stats` — aggregated counters
    - `GET /events/stream/<sid>`  — Server-Sent Events live feed
- `specs/LESSON-1-UI.md` — rewritten as v2 (chat experience).
- `tests/test_broadcaster.py` — 3 tests for broadcaster + aggregator.
- 25/25 tests green.

### This commit — HTML shell
- `src/shopping_agent/static/index.html` — full chat-experience shell:
  topbar with NVIDIA brand mark, two-column layout (chat left, activity
  panel right), composer with file+text input, activity panel with
  zones for per-turn calls / session totals / agents / sub-agents /
  timeline, collapsible inspector drawer for upstream traces, Open
  Sans + JetBrains Mono fonts pulled from Google Fonts.
- All element IDs used by the future `app.js` are in place — see
  element-id map below.

---

## What is NOT done

### `src/shopping_agent/static/styles.css` — EMPTY/STALE
Needs a full NVIDIA-branded stylesheet:
- Palette: NVIDIA Green `#76B900`, black `#000000`, white `#FFFFFF`,
  light gray `#F7F7F7`, medium gray `#767676`, dark gray `#333333`.
- Fonts: `"Open Sans"` body, `"JetBrains Mono"` for code/traces.
- Top-bar black with green accent square as `.brand-mark`.
- Two-column main: chat flex-1, activity panel ~360px fixed.
- Stacks on <900px viewport.
- Chat bubbles: white cards, 8px radius, subtle shadow, LEFT
  accent border green for agent messages, right-aligned for user.
- Activity panel: light gray bg, sectioned blocks, compact labels
  in medium gray, JetBrains Mono for numbers/latencies.
- Drawer: fixed-right overlay 480px wide, slide-in animation.
- Focus rings + hover accents: NVIDIA green.
- Buttons: green primary, ghost variants for secondary.

### `src/shopping_agent/static/app.js` — EMPTY/STALE
Needs complete vanilla-JS chat logic:
- Session id generation (`sess-` + short UUID) + regeneration on `#new-session`.
- Fixture dropdown: `GET /fixtures/list` → populate `<optgroup>` by
  perception_type. On select → `GET /fixtures/load/...` → preview +
  auto-fill prompt from `default_prompt` if textarea empty.
- File attach: click-to-pick, drag-drop, and paste. FileReader → base64.
  Preview with remove button.
- Submit: `POST /chat` with `{session_id, text, images: [{kind:"base64",
  value, mime_type}]}`. Text alone allowed. Image alone allowed.
- User bubble: right-aligned card with optional image thumbnail + text.
- Agent bubble: left-aligned green-accent card, rendered per
  perception_type:
    - `pantry` → items list, notable gaps, suggested uses
    - `shopping_list` → transcribed list, ambiguous-line callouts
    - `food_label` → nutrition-facts grid, ingredients, allergens
    - `fashion` → garment attributes column
    - `cosmetics` → product identity + attributes
    - `unknown` → scene_summary + detected_items fallback
  Each card has a "show raw JSON" expander.
- Activity panel: on load, `GET /sessions/<sid>/stats` → render.
  Then open `EventSource('/events/stream/<sid>')` and update live
  on each event. Gracefully hide if 404 (debug disabled).
- Drawer: "Expand trace" button → `GET /debug/trace/<sid>` → render
  collapsible sections per entry. Slide-in from right.
- Composer: Enter submits, Shift+Enter newline, textarea auto-grow.
- Status line: "calling /chat (Omni reasoning — can take 10-60s)…"
  during submit; "ok · 14.2s" on success; "HTTP 500" on error.

---

## Element-ID map (already in index.html)

```
Input zone:
  #fixture-select         — dropdown
  #session-id             — readonly session id field
  #new-session            — regenerate button
  #file-input             — hidden <input type=file>
  #attach-btn             — attach button in composer
  #composer               — composer <form>
  #composer-preview       — attachment preview container
  #preview-img            — <img> preview element
  #preview-name           — filename label
  #preview-clear          — remove-attachment button
  #prompt-input           — main textarea
  #send-btn               — submit button
  #status                 — status line below composer
  #messages               — scrollable message list
  #empty-state            — placeholder, hide on first message

Activity panel:
  #act-turn               — this-turn calls zone
  #act-totals             — session-total calls zone
  #act-agents             — agents-active zone (3 static slots pre-seeded)
  #act-subagents          — sub-agents zone (empty today)
  #act-timeline           — per-turn timeline zone

Drawer:
  #drawer                 — the drawer root (hidden by default)
  #drawer-toggle          — button in activity panel that opens it
  #drawer-close           — ✕ button inside drawer
  #drawer-body            — scrollable body
```

---

## Backend contracts the frontend consumes

- `POST /chat` → returns `StructuredUnderstanding` shape, see
  `src/shopping_agent/gateway/base.py`. Key fields: `perception_type`,
  `perception_confidence`, `scene_summary`, `user_intent_hint`,
  `detected_items`, and a typed payload under `body[perception_type]`.
- `GET /fixtures/list` — dev-gated. Shape:
  `{fixtures: {<ptype>: [{name, size_bytes, default_prompt}]}}`
- `GET /fixtures/load/<ptype>/<name>` → `{name, mime_type, size_bytes, base64}`
- `GET /debug/trace/<sid>` — dev-gated. Shape: `{entries: [...]}`
- `GET /sessions/<sid>/stats` — dev-gated. Shape documented in
  `specs/LESSON-1-UI.md §6`.
- `GET /events/stream/<sid>` — dev-gated SSE. Each event is the
  envelope in `src/shopping_agent/events/schema.py`.

All `dev-gated` endpoints 404 when `config.debug.enabled` is false.
`config.yaml` from `config.example.yaml` has `debug.enabled: true`.

---

## How to pick this up next time

1. Switch the coding model to something with a larger per-response
   output cap (Sonnet 4.5 is a good choice) OR delegate to a local
   CLI like `claude-code` or `codex` which have their own budgets.
2. Start from this note + `specs/LESSON-1-UI.md` v2.
3. Write `styles.css` first (pure visual), then `app.js`.
4. After each file, run:
     ```
     cd ~/PRD && .venv/bin/pytest -q
     ```
   Tests must stay 25/25 green (no backend change expected).
5. Verify static serves:
     ```
     cd ~/PRD && .venv/bin/python -c "
     from shopping_agent.api.app import create_app
     from fastapi.testclient import TestClient
     app = create_app()
     c = TestClient(app)
     for p in ['/ui', '/ui/static/index.html', '/ui/static/app.js', '/ui/static/styles.css']:
         r = c.get(p)
         print(p, r.status_code, len(r.content))
     "
     ```
6. Commit with message pattern:
     ```
     ui(chat): NVIDIA-branded chat UI + activity panel + trace drawer
     ```

## Why this kept failing last session

Opus 4.7 has a per-response output-token cap. Long CSS (~180 lines)
plus long JS (~400 lines) plus prose in one turn exceeds it, the
response truncates mid tool-call, and the tool call is rejected.
Delegating to a subagent didn't fix it — subagent used same model,
same cap. The fix is either (a) use a model with a bigger cap for
this kind of emission, or (b) split the work across many small files.
