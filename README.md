# Retail Shopping Agent — Multimodal, Grocery-First

A multimodal (image + audio + text) retail shopping agent, built
scaffolding-first so the grocery vertical we ship in Phase 1
extends cleanly to fashion, cosmetics, and home goods later.

This repo is spec-driven: what to build lives in `specs/` before
code is written. Phase-1 scope and rationale are in
`PHASE-1-ROADMAP.md`.

## Phase 1 front-end (current state)

The "perception" half of the agent. Runs a FastAPI service that
takes multimodal input (image + text now; audio stubbed) and calls
NVIDIA's Nemotron 3 Nano Omni (Role 1) to produce structured
understanding. Role 2 (reasoning + tool calling) and downstream
modules are scaffolded but not wired yet.

```
  [sa-cli]  --HTTP-->  [FastAPI service]  --NIM API-->  [Nemotron Omni]
                              |
                              v
                      events.jsonl (M-EVENTS)
```

## Layout

```
  specs/                 Spec-first artifacts for M0, M3, M4 (Lesson 1)
  src/shopping_agent/    The platform package
    config.py             M-SEC loader (yaml + env)
    gateway/              M0 adapters (Role 1 live; Role 2/3 stubs)
    events/               M-EVENTS bus + JSONL sink
    conversation/         M1 in-memory session store (stub)
    specialists/          M4 registry (stub)
    api/                  FastAPI app, /chat /healthz /sessions
    clients/cli.py        sa-cli thin client
  clients/               (empty — reserved for future web client)
  tests/                 12 unit tests, all mocked (no network)
  config.example.yaml    copy to config.yaml and adjust
  .env.example           copy to .env and fill in real keys
```

## First run

1. **Install deps** (one-time):

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Create your config and secrets**:

   ```sh
   cp config.example.yaml config.yaml
   cp .env.example .env
   # edit .env and fill in the three NVIDIA_* keys
   ```

3. **Run tests** (sanity check — nothing calls the network):

   ```sh
   pytest
   ```

4. **Start the service** in one terminal:

   ```sh
   set -a; source .env; set +a
   shopping-agent     # equivalent to: uvicorn shopping_agent.api.app:app
   ```

   Service listens on `http://127.0.0.1:8000`. Open `/docs` in a
   browser for the auto-generated OpenAPI/Swagger UI.

5. **Talk to it** from another terminal:

   ```sh
   sa-cli health                                     # probe /readyz
   sa-cli chat --text "hi" --once                    # text only
   sa-cli chat --text "what's this?" --image /path/to/pantry.jpg --once
   sa-cli chat                                       # interactive loop
   sa-cli session <session-id>                       # show transcript
   ```

## Events

Every turn emits events to `./events/events.jsonl` (configurable in
`config.yaml`). Each line is a JSON object with `session_id`,
`turn_id`, and a typed payload. This is the data flywheel — don't
delete it, and don't commit it (already gitignored).

## Phase 1 scope (what's in vs. out)

See `PHASE-1-ROADMAP.md` for the module map. Right now only M0
(Role 1 slot), M-SEC, and M-EVENTS are *live*; everything else is
scaffolded so adding the next lesson means filling in one file.

## Spec-driven discipline

- Every spec has a Domain Generality Analysis (fashion-testable,
  cosmetics-honest).
- Every interface is v1 from day one; breaking changes create v2,
  v1 stays live.
- Every spec lists the events it emits — no module publishes an
  event that doesn't appear in `events/schema.py`.

## Resume state

Day-to-day status, open questions, and next steps live in
`SESSION-NOTES.md`. Check it before starting any new session.
