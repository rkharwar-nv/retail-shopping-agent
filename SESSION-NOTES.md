# Session Notes — Resume From Here

**Last session:** May 11, 2026
**Project root:** `/home/ubuntu/PRD/`  (rename to `retail-shopping-agent` later if desired)
**Goal:** multimodal retail shopping agent, grocery-first, scaffolding extends to fashion/cosmetics/home later.

---

## Where we are

Phase 1 *front-end* is coded. FastAPI service + thin CLI client
exercises the Role 1 (Nemotron Omni) input pipeline end-to-end.
Role 2, Role 3, specialists, catalog, UI renderer: scaffolded but
not wired.

Spec coverage: M0, M3, M4, M-SEC are spec'd. M-EVENTS has a Phase-1
implementation ahead of its formal spec — Lesson 2 will write that
spec and retroactively align code to it.

## What's on disk

```
  /home/ubuntu/PRD/
  ├── specs/LESSON-1-M0-MODEL-GATEWAY.md
  ├── specs/LESSON-1-M3-RESPONSE-ENVELOPE.md
  ├── specs/LESSON-1-M4-SPECIALIST-REGISTRY.md
  ├── src/shopping_agent/...    (code, see README for layout)
  ├── tests/                    (12 tests, all pass, all mocked)
  ├── PHASE-1-ROADMAP.md
  ├── README.md                 (run instructions)
  ├── pyproject.toml
  ├── config.example.yaml
  ├── .env.example
  └── .gitignore
```

Published: https://github.com/rkharwar-nv/retail-shopping-agent

## To run the service for the first time

1. `cd /home/ubuntu/PRD`
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -e ".[dev]"`
4. `pytest`  (should be 12 passed)
5. `cp config.example.yaml config.yaml`
6. `cp .env.example .env`
7. Fill in the three NVIDIA keys in `.env`
8. `set -a; source .env; set +a`
9. `shopping-agent`  (uvicorn on http://127.0.0.1:8000)
10. In another terminal:
    - `sa-cli health`
    - `sa-cli chat --text "hello" --once`
    - `sa-cli chat --text "what's this?" --image /path/to/pantry.jpg --once`
    - `sa-cli chat`  (interactive loop)

## What's next (in order)

1. **Live Role 1 smoke test** — first real NIM call. Expect to debug:
   - Exact Nemotron Omni request body (the TODO in role1_omni.py)
   - Audio input shape (stubbed now; live data later)
2. **Lesson 2: M-EVENTS spec** — formalize the schema the code
   already uses (EV_* constants in events/schema.py). Taxonomy,
   PII policy, versioning mechanics.
3. **Lesson 3: M1 + M2** — conversation state (real, not in-memory
   placeholder) + tool registry for Role 2.
4. **Role 2 adapter (Super)** — once M2 is spec'd.
5. **Lesson 4: Grocery specialist + tools.**
6. **Lesson 5: U1 renderer.**
7. **Lesson 6: Pantry-to-Plate end-to-end.**

## Key decisions locked

- Three model roles: Nemotron 3 Nano Omni (Role 1), Nemotron 3 Super
  120B A12B (Role 2), llama-3.2-nv-embedqa-1b-v2 (Role 3).
- Role 1 endpoint: `https://integrate.api.nvidia.com/v1` (build.nvidia.com key).
- Role 2 + Role 3 endpoint: `https://inference-api.nvidia.com/v1`
  (separate key from Role 1; each role has its own env-var slot).
- All roles reached via HTTP via OpenAI-compatible client (OpenAI SDK).
- Config from `config.yaml` (non-secret) + env vars (secrets). Never hardcoded.
- Pluggability via per-provider adapters; typed role slots.
- Phase 1 inputs: image + audio + text (video deferred).
- Catalog: synthetic + Open Food Facts, ~1000 products (not yet built).
- Text-only embeddings in Phase 1.
- Event bus first-class in Phase 1 (JSONL file sink now,
  swappable later).
- API-first architecture — every Lesson 1 spec maps to an endpoint.

## Open questions (live)

- **Nemotron Omni request body** — first NIM call will reveal
  whether our OpenAI-compatible multimodal content blocks work
  as-is. Currently we fall back to raw text if JSON parse fails.
- **Omni audio input shape** — stubbed with a text placeholder.
  Fix after first successful image-only call.
- **Role 2 tool-call dialect** — assumed OpenAI-style; will verify
  when Role 2 adapter lands.

## Discovered / validated this session

- YAML `null` parses to Python `None`, not the string `"null"` —
  config literal value needs quoting in YAML. Caught by tests.
- openai>=1.30 AsyncOpenAI works with NIM's base_url and OpenAI-
  compatible content-block schema (library-level, not yet
  live-verified against NIM).
- FastAPI's dependency-injection (`lru_cache`) is the clean way
  to keep adapter singletons without globals.

## SDD lessons banked so far

- Specs emerge from back-and-forth with a domain expert.
- "Pluggable" only works if the seam is named and specified.
- Events are asymmetric — not emitted = data lost forever.
- Scaffolding = empty but named extension points, not vague promises.
- Fashion-Testable + Cosmetics-Honest check surfaces hidden
  assumptions cheaply.
- Config-first (env + yaml) beats hardcoded endpoints every time.
- API-first means every future surface (CLI, web, mobile,
  telemetry dashboard) is additive — not a rewrite.
- Tests first catch YAML-vs-Python literal mismatches before
  they reach production configuration.
