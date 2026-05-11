# Session Notes — Resume From Here

**Last session:** May 10, 2026
**Project root:** `/home/ubuntu/PRD/` (consider renaming to `retail-shopping-agent/`)
**Goal:** multimodal retail shopping agent, grocery-first, scaffolding extends to fashion/cosmetics/home later.

---

## Where we are

Phase 1 scoping is complete. Roadmap is on disk. Lesson 1 (the three core
platform seams) is drafted. Four more lessons to go in the learning path.

## What's written

```
  README.md
  PHASE-1-ROADMAP.md
  .gitignore
  .env.example
  config.example.yaml
  specs/
    LESSON-1-M0-MODEL-GATEWAY.md
    LESSON-1-M3-RESPONSE-ENVELOPE.md
    LESSON-1-M4-SPECIALIST-REGISTRY.md
```

## What's next (in order)

1. **Git init + first commit** — turn this into a real repo.
2. **Push to GitHub** — private repo, personal or employer org. Deferred
   to you because it needs an account decision.
3. **Lesson 2: M-EVENTS** — event bus spec. Schema, emission points,
   versioning, PII stance. First-class Phase 1 module, not a hook.
4. **Lesson 3: M1 + M2** — conversation state + tool registry.
5. **Lesson 4: GS + T0–T3** — grocery specialist + its tools.
6. **Lesson 5: U1** — response renderer spec.
7. **Lesson 6: J1** — Pantry-to-Plate end-to-end acceptance.

## Key decisions locked

- Three model roles: Nemotron 3 Nano Omni (Role 1), Nemotron 3 Super
  120B A12B (Role 2), llama-3.2-nv-embedqa-1b-v2 (Role 3).
- Role 1 endpoint: `https://integrate.api.nvidia.com/v1` (build.nvidia.com key).
- Role 2 and Role 3 endpoint: `https://inference-api.nvidia.com/v1`
  (separate key from Role 1; Role 2 and Role 3 may share or not).
- All roles reached via HTTP. Local vs. remote is a URL change only.
- Config from `config.yaml` (non-secret) + env vars (secrets). Never hardcoded.
- Pluggability via per-provider adapters. Typed role slots prevent
  wiring into the wrong seam.
- Phase 1 inputs: **image + audio + text** (video deferred).
- Catalog is part of the solution (synthetic + Open Food Facts), ~1000
  products.
- Text-only embeddings in Phase 1.
- Event bus is first-class in Phase 1, not a hook.
- Discipline for every spec: Fashion-Testable, Cosmetics-Honest, with
  a Domain Generality Analysis table.

## Open questions (carried forward)

- Exact Role 1 request body shape for Nemotron Omni — verify on
  first integration call.
- Does `inference-api.nvidia.com/v1` accept OpenAI-style
  `/chat/completions` and `/embeddings` paths? Verify on first call.
- Role 2 tool-call dialect confirmation: assumed OpenAI-style;
  verify when implementing.
- Role 3 and Role 2 key sharing: left to user's discretion. Config
  slots are separate either way.
- GitHub: private repo location (personal account vs. employer org).

## How to resume

1. Read `PHASE-1-ROADMAP.md` first (2 min).
2. Read this file (1 min).
3. Skim the three Lesson 1 specs in `specs/` (5 min).
4. Say "continue Lesson 2" to start M-EVENTS.

## SDD lessons banked so far

- Specs emerge from back-and-forth with a domain expert; a spec
  written top-down in isolation misses real constraints.
- "Pluggable" only works if the seam is named and specified.
- Events are asymmetric — not emitted = data lost forever.
- Scaffolding = empty but named extension points, not vague promises.
- The Fashion-Testable, Cosmetics-Honest check surfaces hidden
  assumptions cheaply.
- Config-first (env + yaml) beats hardcoded endpoints every time.
