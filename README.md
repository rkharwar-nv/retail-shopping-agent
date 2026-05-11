# Retail Shopping Agent — Multimodal, Grocery-First

A multimodal (image + audio + text) retail shopping agent, built
scaffolding-first so the grocery vertical we ship in Phase 1
extends cleanly to fashion, cosmetics, and home goods later.

**Status:** Phase 1 scoping complete. Writing specs (Lesson 1 next).

## Models (pluggable, reached via HTTP)

| Role | Purpose | Model |
|------|---------|-------|
| 1 | Multimodal input processing | Nemotron 3 Nano Omni 30B A3B (Reasoning) |
| 2 | Reasoning + tool calling | Nemotron 3 Super 120B A12B |
| 3 | Text embeddings | llama-3.2-nv-embedqa-1b-v2 |

Each role has its own base URL and API key. Configured via
`config.yaml` (non-secret) + environment variables (secrets only).

## Repo layout

```
  PHASE-1-ROADMAP.md     Phase 1 plan, modules, discipline
  specs/                 Module specs, one file per lesson
  config.example.yaml    Config template (copy to config.yaml)
  .env.example           Secret keys template (copy to .env)
  SESSION-NOTES.md       Where we are; resume from here
  SDD-SESSION-LOG.md     Dated session log (what was decided when)
```

## How to read this repo

1. `PHASE-1-ROADMAP.md` — the plan. Start here.
2. `specs/LESSON-*` — the specs, in order. Each one teaches one SDD
   concept and produces one real contract an engineer can build from.
3. `SESSION-NOTES.md` — current state, next step, open questions.

## Conventions

- Every spec is **versioned** (v1, v2…). Breaking changes = new version.
- Every spec includes **Events Emitted**, **Failure Modes**, and a
  **Domain Generality Analysis** (the fashion/cosmetics check).
- Model IDs, endpoints, and API keys live in config/env — never
  hardcoded in specs or code.
- The NVIDIA PRD this is based on is CONFIDENTIAL and is gitignored.
