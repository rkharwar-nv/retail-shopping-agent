# Session Notes — Resume From Here

**Last updated:** May 10, 2026
**Status:** Lesson 1 specs written (M0, M3, M4). Pre-git-init.

## Where we are

Phase 1 scoping is complete and the first three platform specs
(M0 Model Gateway, M3 Response Envelope, M4 Specialist Registry)
are drafted and on disk. Next lesson is M-EVENTS.

## What exists on disk

```
  /home/ubuntu/PRD/
  ├── PHASE-1-ROADMAP.md            ← the plan
  ├── README.md                      ← entry point for repo
  ├── .gitignore                     ← PRD + secrets excluded
  ├── .env.example                   ← 3 API key slots
  ├── config.example.yaml            ← 3 role config blocks
  ├── SESSION-NOTES.md               ← this file
  └── specs/
      ├── LESSON-1-M0-MODEL-GATEWAY.md
      ├── LESSON-1-M3-RESPONSE-ENVELOPE.md
      └── LESSON-1-M4-SPECIALIST-REGISTRY.md
```

Not yet on disk:
- Git repo init + first commit
- SDD-SESSION-LOG.md (dated decisions log — optional)

## Locked decisions

- **Phase 1 scope:** grocery only; scaffolding extensible to
  fashion / cosmetics / home.
- **Phase 1 inputs:** image + audio + text (video deferred).
- **Phase 1 journey:** Pantry-to-Plate.
- **No fine-tuning.** Integration only, via HTTP.
- **Three model roles**, each with its own config block and
  API key slot:
  - Role 1 — Nemotron 3 Nano Omni 30B A3B (Reasoning) —
    multimodal input → structured understanding.
    Base: `https://integrate.api.nvidia.com/v1`
  - Role 2 — Nemotron 3 Super 120B A12B — reasoning + tools.
    Base: `https://inference-api.nvidia.com/v1`
  - Role 3 — llama-3.2-nv-embedqa-1b-v2 — text embeddings.
    Base: `https://inference-api.nvidia.com/v1`
- **Config discipline:** non-secret values in `config.yaml`,
  secrets in env vars. Model IDs are config, not spec-hardcoded.
- **Tool-call dialect:** neutral internal; adapter translates
  to provider-native (OpenAI-style is the typical target).
- **Wire format for specs:** JSON Schema–shaped pseudo-types.
- **Vector store:** pgvector default, swappable at config time.
- **Catalog:** part of the solution; seeded from Open Food Facts
  + synthetic additions (~1000 items for Phase 1).
- **Pluggability:** Role 1 and Role 2 runtime-swappable; Role 3
  config-time-swappable (embedding swap = re-index).
- **Events:** M-EVENTS is a first-class platform module, not a
  hook. Every spec has an "Events Emitted" section.
- **Versioning policy:** every spec has `schema_version`.
  Breaking changes bump the version; old versions stay live until
  callers migrate.

## Discipline rules adopted

1. **Fashion-testable, cosmetics-honest.** Every spec includes a
   Domain Generality Analysis table. If it fails the fashion
   check, it isn't done. Unknown for cosmetics = mark TBD with
   escape hatch, never guess.
2. **Three extension patterns** are the only sanctioned shapes:
   open map, tagged union, named hook.
3. **"Manage diligently" on secrets.** Each role has an
   independent credential slot. No sharing via code. Keys never
   logged, never in events, never in `config.yaml`.
4. **Ship the hook before the feature.** Empty hooks for
   guardrails, profile, consent are Phase 1 deliverables.
   Implementations come later without interface churn.

## Open questions carried forward

- **Role 1 multimodal request shape.** Verify Nemotron Omni's
  expected request body against NVIDIA NIM docs on first
  integration. Spec says "may need a custom client."
- **OpenAI-path compatibility** of `inference-api.nvidia.com/v1`
  for `/chat/completions` and `/embeddings`. Verify on first call.
- **`loading` envelope use in Phase 1.** M3 allows it; Phase 1
  implementation may skip sending them (whole-envelope only).
- **Role 3 key sharing with Role 2.** Config allows separate
  values; may be identical in practice. Document in your real
  `.env`.
- **GitHub remote.** Deferred per session decision; local git
  only tonight.

## Learning path progress

```
  Lesson 1  M0 + M3 + M4         ✓ written
  Lesson 2  M-EVENTS              ← next
  Lesson 3  M1 + M2               pending
  Lesson 4  GS + T0-T3            pending
  Lesson 5  U1                    pending
  Lesson 6  J1 end-to-end         pending
```

## How to resume tomorrow

1. Read this file first.
2. Skim `PHASE-1-ROADMAP.md` §4 (module list) and §8 (learning
   path) to reload the plan.
3. Skim the three Lesson 1 spec files if you want to push back
   on them before continuing.
4. Tell the agent: "resume SDD session — continue with Lesson 2
   (M-EVENTS)." That's enough context to start.

## Next session starting move

Write `specs/LESSON-2-M-EVENTS.md`. Expected contents: event
envelope schema (v1 with all 7 PRD §12 layers defined), named
emission points list, `publish(event)` interface, JSONL file
sink implementation, correlation ID rules, PII redaction rules,
non-blocking buffer behavior, failure modes.

Then optionally commit + push to GitHub (deferred from tonight).
