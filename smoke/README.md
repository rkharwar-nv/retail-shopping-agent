# Smoke Test Harness

Live-call tests against the running shopping-agent service. See
`specs/LESSON-1-SMOKE.md` for the full design.

## Quick start

The service must be running first:

    set -a; source .env; set +a
    shopping-agent   # starts at http://localhost:8000

In another terminal:

    sa-smoke                           # run every fixture
    sa-smoke --perception pantry       # filter to one folder
    sa-smoke --fixture Ingredients2    # substring match
    sa-smoke --timeout 180             # bump per-request timeout

## Folder layout

    smoke/
      fixtures/             <-- inputs, committed to git
        pantry/
          Ingredients2.jpeg
          Ingredients2.txt  <-- [optional] sidecar prompt for this image
        shopping_list/
        food_label/
        fashion/
        cosmetics/
        unknown/
      runs/                 <-- outputs, GITIGNORED (exploratory)
        2026-05-11T19-45-33Z/
          pantry__Ingredients2.jpeg.json  <-- full /chat response
          manifest.json                    <-- machine index
          summary.md                       <-- human digest
      canonical/            <-- blessed runs, COMMITTED to git
        baseline-v1/        <-- same shape as runs/<ts>/

## Adding a fixture

1. Drop an image file into `smoke/fixtures/<perception_type>/`.
   Extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
2. Folder name must be one of: pantry, shopping_list, food_label,
   fashion, cosmetics, unknown.
3. (Optional) Add a sidecar `.txt` file with the same basename to
   override the default text prompt for that fixture:

       Ingredients2.jpeg        <- image
       Ingredients2.txt         <- prompt text (any length)

## Blessing a good run (canonical snapshots)

When you want a run on record — after improving a prompt, after
switching model versions, etc. — promote it:

    sa-smoke promote 2026-05-11T19-45-33Z baseline-v1

Then commit:

    git add smoke/canonical/baseline-v1
    git commit -m "smoke: capture baseline-v1"

## Comparing runs

    sa-smoke compare 2026-05-11T19-45-33Z 2026-05-12T10-00-00Z
    sa-smoke compare baseline-v1 2026-05-12T10-00-00Z

Emits a table of per-fixture classification changes and latency deltas.

## Exit codes

- `0` — all fixtures returned 200 with no parse errors.
- `1` — at least one fixture failed.
- `2` — setup error (service unreachable, no fixtures match).

## Not in scope (Phase 1)

- No graded accuracy scoring.
- No LLM-as-judge.
- No CI integration.
- No golden-output assertions.

Those belong to Tier 3 (future).
