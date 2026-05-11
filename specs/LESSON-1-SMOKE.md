# Lesson 1 — Smoke Test Harness (Tier 2)

**Status:** draft v1 · **Owner:** PM + platform team
**Related specs:** LESSON-1-M0-MODEL-GATEWAY, LESSON-1-M3-ENVELOPE, LESSON-1-M4-SPECIALIST-REGISTRY

---

## 1. Purpose

Unit tests (Tier 1) verify code correctness with mocks. They prove the
adapter, parser, and event bus work the way code says they do. They do
**not** catch:

- Prompt regressions — a wording change that makes Omni misclassify.
- NIM behavior drift — NVIDIA updates a model and outputs change.
- Auth / quota / latency issues that only appear live.
- Vertical-specific failure modes (e.g. "pantry works, food_label
  returns garbage").

Smoke tests (Tier 2) close those gaps. They hit the **running service**
with **curated real inputs**, save the **full response to disk**, and
emit a **human-readable digest** so a PM or engineer can scan results
at a glance.

Eval harness (Tier 3) — golden outputs, graded scoring, LLM-as-judge —
is a future lesson. Smoke is the prerequisite: you need captured
outputs before you can grade them.

## 2. Domain Generality Analysis

This smoke harness is **domain-generic**, with the domain surface
expressed entirely as fixture folders. Fashion-testable: drop a
`smoke/fixtures/fashion/` image and it runs. Cosmetics-honest: the
`cosmetics/` folder can stay empty in Phase 1 and still shows up
in reports as "0 fixtures" rather than being ignored.

| Aspect             | Shape                                 | Grocery Phase 1 | Fashion (future) | Cosmetics (future) |
| ------------------ | ------------------------------------- | --------------- | ---------------- | ------------------ |
| fixture taxonomy   | `fixtures/<perception_type>/*`        | pantry, shopping_list, food_label populated | fashion populated | cosmetics populated |
| prompt per fixture | optional sidecar `.txt` next to image | optional        | optional         | optional           |
| output schema      | whatever `/chat` returns              | same            | same             | same               |
| grading            | out of scope here                     | -               | -                | -                  |

No vertical branching in the code. Adding fashion fixtures later is a
mkdir, not a code change.

## 3. Fixture Taxonomy

```
smoke/fixtures/
  pantry/                ingredient / fridge / pantry photos
    <name>.{jpg,jpeg,png,webp}
    <name>.txt           [optional] text prompt for this fixture
  shopping_list/         handwritten or printed lists
  food_label/            nutrition panels, ingredient lists
  fashion/               clothing, shoes, accessories
  cosmetics/             skincare, makeup, fragrance
  unknown/               negative-case images (landscapes, pets, etc.)
```

**Rules:**

- Folder name **must** match a valid `perception_type`. Unknown folders
  are skipped with a warning.
- A fixture is any file with a recognized image extension (`.jpg`,
  `.jpeg`, `.png`, `.webp`).
- If `fixture.jpg` has a sibling `fixture.txt`, that file's content is
  the text prompt sent alongside the image. Otherwise a sensible
  default prompt is used per perception_type.
- Empty folders are fine — the harness reports "0 fixtures" for them,
  which is honest and matches our cosmetics-in-Phase-1 discipline.

## 4. Driver: `run_smoke.py`

A Python script (installed as `sa-smoke` console entry point) that:

1. **Discovers fixtures** under `smoke/fixtures/<perception_type>/`.
2. **Filters** per `--perception` / `--fixture` args.
3. **Creates a timestamped run folder** `smoke/runs/<ISO8601>/`.
4. **For each fixture:**
   - Load the image.
   - Load the sidecar text prompt if present; else use a per-type default.
   - POST to the live `/chat` endpoint.
   - Save full JSON response to `runs/<ts>/<perception_type>__<name>.json`.
   - Capture duration, status, classified `perception_type`, error (if any).
5. **Write `summary.md`** — a markdown table of all runs plus aggregate
   stats (count, errors, classification accuracy vs folder expectation).
6. **Print rich-formatted summary** to terminal.

### CLI surface

```
sa-smoke                           run every fixture
sa-smoke --perception pantry       only that folder
sa-smoke --fixture Ingredients2    substring match on filename
sa-smoke --base-url http://x:8000  override service URL
sa-smoke --timeout 120             per-request timeout (default 90s)
sa-smoke compare --left RUN --right RUN   diff two runs
```

### Exit codes

- `0` — all fixtures returned 2xx.
- `1` — at least one fixture failed (non-2xx, timeout, parse error).
- `2` — setup error (service unreachable, no fixtures, etc.).

## 5. Output Structure

```
smoke/runs/2026-05-11T19-45-33Z/
  pantry__Ingredients2.jpeg.json   full /chat response body
  pantry__Ingredients1.png.json
  summary.md                        human digest
  manifest.json                     machine-readable run index
```

### `summary.md` shape

```
# Smoke Run 2026-05-11T19:45:33Z

**Base URL:** http://localhost:8000
**Total:** 2 fixtures · **Passed:** 2 · **Failed:** 0

| Fixture | Expected | Got | Conf | Duration | Status |
|---------|----------|-----|------|----------|--------|
| pantry/Ingredients2.jpeg | pantry | pantry | 0.88 | 14.2s | ✓ |
| pantry/Ingredients1.png  | pantry | pantry | 0.76 | 38.1s | ✓ |

## Per-fixture highlights

### pantry/Ingredients2.jpeg → pantry (0.88)
- scene_summary: "..."
- items detected: 6
- notable_gaps: ["bread", "oil"]
```

### `manifest.json` shape

```json
{
  "run_id": "2026-05-11T19-45-33Z",
  "base_url": "http://localhost:8000",
  "started_at": "...",
  "finished_at": "...",
  "fixtures": [
    {
      "path": "pantry/Ingredients2.jpeg",
      "expected_type": "pantry",
      "actual_type": "pantry",
      "perception_confidence": 0.88,
      "duration_ms": 14203,
      "status_code": 200,
      "response_file": "pantry__Ingredients2.jpeg.json",
      "error": null
    }
  ]
}
```

## 6. Compare: `sa-smoke compare`

Given two run IDs (or paths), emit:

- Fixtures only in left / only in right (drift in fixture set).
- Per-fixture classification drift (`pantry → unknown`, conf change).
- Latency delta per fixture.

No semantic diff of response bodies in v1 — that's Tier 3 territory.

## 7. What Smoke Does NOT Do

Intentional non-goals for Phase 1:

- **No graded accuracy scoring.** The harness reports "expected vs got"
  based on folder name; it does not grade the typed payload contents.
- **No LLM-as-judge.** Tier 3, future.
- **No CI integration.** Smoke is run-on-demand; wiring to CI waits
  until test stability is proven.
- **No golden-output assertions.** Outputs are captured but not
  diffed against a canonical. Once we have 30+ fixture runs and stable
  classification, we pick "the good ones" and promote them to golden.
- **No mocking.** This is the live-call tier. If NVIDIA is down, smoke
  fails — that's the signal, not a bug.

## 8. Relationship to Other Test Tiers

| Tier | Tool     | Network | Determinism | Cost     | When                          |
| ---- | -------- | ------- | ----------- | -------- | ----------------------------- |
| 1    | pytest   | none    | full        | free     | every code change             |
| 2    | sa-smoke | live    | none        | tokens   | before push, after prompt change |
| 3    | (future) | live    | graded      | tokens+judge | CI, every deploy          |

## 9. Open Questions

- **Q-SMOKE-1:** Should responses be scrubbed of PII before being saved?
  Phase 1 fixtures are all synthetic / owned by us → **no** for now.
  Revisit when real user uploads enter a fixture set.
- **Q-SMOKE-2:** Do we commit `summary.md` from canonical runs?
  Leaning **no** — nondeterministic outputs pollute git history.
  Revisit once golden outputs exist.
- **Q-SMOKE-3:** Should fashion/cosmetics fixtures run even when Phase 1
  has no specialist? **Yes** — classification is in scope for Role 1
  from day one; only downstream routing is phased.

## 10. Implementation Notes

- Entry point: `sa-smoke` console script (added to pyproject.toml).
- Module: `src/shopping_agent/clients/smoke.py`.
- Deps: only `httpx`, `rich`, `typer` — already in the project.
- Runs gitignored under `smoke/runs/**`.
- Fixtures committed under `smoke/fixtures/**`.
