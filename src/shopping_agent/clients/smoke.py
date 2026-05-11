"""Smoke test harness — Tier 2 tests.

Hits the running shopping-agent service with curated fixture inputs
under smoke/fixtures/<perception_type>/ and captures full responses
to disk for inspection and comparison.

See specs/LESSON-1-SMOKE.md for the design.

Usage:
    sa-smoke                                  # run every fixture
    sa-smoke --perception pantry              # filter
    sa-smoke --fixture Ingredients2           # substring match
    sa-smoke --base-url http://host:8000      # override URL
    sa-smoke promote <run_id> <tag>           # bless a run
    sa-smoke compare <left> <right>           # diff two runs
"""

from __future__ import annotations

import base64
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

VALID_PERCEPTIONS = {
    "pantry", "shopping_list", "food_label",
    "fashion", "cosmetics", "unknown",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_PROMPTS = {
    "pantry": "What do I have here? What can I make? What am I missing?",
    "shopping_list": "Transcribe this shopping list and normalize the items.",
    "food_label": "Extract the product information from this label.",
    "fashion": "Describe this clothing item.",
    "cosmetics": "What product is this?",
    "unknown": "What is this?",
}
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}

app = typer.Typer(help="Smoke test harness for the retail shopping agent.")
console = Console()

# Project root resolved relative to this file: src/shopping_agent/clients/smoke.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = PROJECT_ROOT / "smoke" / "fixtures"
RUNS_DIR = PROJECT_ROOT / "smoke" / "runs"
CANONICAL_DIR = PROJECT_ROOT / "smoke" / "canonical"


def _discover_fixtures(perception_filter=None, fixture_filter=None):
    """Walk smoke/fixtures/ and return list of (perception_type, path) tuples."""
    out = []
    if not FIXTURES_DIR.exists():
        return out
    for ptype_dir in sorted(FIXTURES_DIR.iterdir()):
        if not ptype_dir.is_dir():
            continue
        ptype = ptype_dir.name
        if ptype not in VALID_PERCEPTIONS:
            console.print(f"[yellow]skip unknown folder:[/] {ptype}")
            continue
        if perception_filter and ptype != perception_filter:
            continue
        for f in sorted(ptype_dir.iterdir()):
            if f.suffix.lower() not in IMAGE_EXTS:
                continue
            if fixture_filter and fixture_filter not in f.name:
                continue
            out.append((ptype, f))
    return out


def _load_prompt(image_path: Path, ptype: str) -> str:
    """Sidecar .txt next to image takes precedence; else default per type."""
    sidecar = image_path.with_suffix(".txt")
    if sidecar.exists():
        return sidecar.read_text(encoding="utf-8").strip()
    return DEFAULT_PROMPTS.get(ptype, "Describe what you see.")


def _encode_image(image_path: Path) -> tuple[str, str]:
    """Return (base64_data_url_value, mime_type). Uses 'base64' kind."""
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = MIME_BY_EXT.get(image_path.suffix.lower(), "image/jpeg")
    return b64, mime


def _run_one(client, base_url, ptype, image_path, timeout):
    """Run one fixture. Returns a dict result."""
    prompt = _load_prompt(image_path, ptype)
    b64, mime = _encode_image(image_path)
    payload = {
        "session_id": f"smoke-{ptype}",
        "text": prompt,
        "images": [{"kind": "base64", "value": b64, "mime_type": mime}],
    }
    started = datetime.now(timezone.utc)
    try:
        resp = client.post(f"{base_url}/chat", json=payload, timeout=timeout)
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
        return {
            "path": f"{ptype}/{image_path.name}",
            "expected_type": ptype,
            "actual_type": (body or {}).get("perception_type") if body else None,
            "perception_confidence": (body or {}).get("perception_confidence") if body else None,
            "duration_ms": duration_ms,
            "status_code": resp.status_code,
            "body": body,
            "error": None if resp.status_code == 200 else f"http_{resp.status_code}",
        }
    except httpx.TimeoutException as e:
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"path": f"{ptype}/{image_path.name}", "expected_type": ptype,
                "actual_type": None, "perception_confidence": None,
                "duration_ms": duration_ms, "status_code": None,
                "body": None, "error": f"timeout: {e}"}
    except Exception as e:  # noqa: BLE001
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"path": f"{ptype}/{image_path.name}", "expected_type": ptype,
                "actual_type": None, "perception_confidence": None,
                "duration_ms": duration_ms, "status_code": None,
                "body": None, "error": f"{type(e).__name__}: {e}"}


def _write_results(run_dir: Path, base_url: str, results: list[dict],
                   started_at: str, finished_at: str):
    """Save per-fixture JSON bodies, manifest.json, and summary.md."""
    run_dir.mkdir(parents=True, exist_ok=True)

    # Per-fixture response bodies.
    for r in results:
        safe = r["path"].replace("/", "__")
        body_path = run_dir / f"{safe}.json"
        body_path.write_text(
            json.dumps(r["body"] or {"error": r["error"]}, indent=2),
            encoding="utf-8",
        )

    # manifest.json
    manifest = {
        "run_id": run_dir.name,
        "base_url": base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "fixtures": [
            {k: r[k] for k in ("path", "expected_type", "actual_type",
                               "perception_confidence", "duration_ms",
                               "status_code", "error")}
            | {"response_file": r["path"].replace("/", "__") + ".json"}
            for r in results
        ],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # summary.md
    passed = sum(1 for r in results if r["error"] is None)
    failed = len(results) - passed
    lines = [
        f"# Smoke Run {run_dir.name}",
        "",
        f"**Base URL:** {base_url}",
        f"**Total:** {len(results)} fixtures · **Passed:** {passed} · **Failed:** {failed}",
        "",
        "| Fixture | Expected | Got | Conf | Duration | Status |",
        "|---------|----------|-----|------|----------|--------|",
    ]
    for r in results:
        conf = (f"{r['perception_confidence']:.2f}"
                if r.get("perception_confidence") is not None else "-")
        status = "✓" if r["error"] is None else f"✗ {r['error']}"
        dur = f"{r['duration_ms']/1000:.1f}s"
        lines.append(
            f"| {r['path']} | {r['expected_type']} | "
            f"{r.get('actual_type') or '-'} | {conf} | {dur} | {status} |"
        )

    # Per-fixture highlights for passed runs.
    lines += ["", "## Per-fixture highlights", ""]
    for r in results:
        if r["error"] or not r.get("body"):
            continue
        body = r["body"]
        lines.append(f"### {r['path']} → {r.get('actual_type')} "
                     f"({r.get('perception_confidence')})")
        if body.get("scene_summary"):
            lines.append(f"- **scene_summary:** {body['scene_summary']}")
        if body.get("user_intent_hint"):
            lines.append(f"- **user_intent_hint:** {body['user_intent_hint']}")
        lines.append(f"- **detected_items:** {len(body.get('detected_items') or [])}")
        # Typed payload highlight.
        ptype = r.get("actual_type")
        typed = body.get(ptype) if ptype else None
        if isinstance(typed, dict):
            if typed.get("items"):
                lines.append(f"- **{ptype}.items:** {len(typed['items'])}")
            if typed.get("notable_gaps"):
                lines.append(f"- **notable_gaps:** {typed['notable_gaps']}")
            if typed.get("suggested_recipe_hints"):
                lines.append(f"- **suggested_recipe_hints:** {typed['suggested_recipe_hints']}")
        lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _print_summary(results: list[dict], run_dir: Path):
    table = Table(title=f"smoke run → {run_dir.name}")
    table.add_column("fixture")
    table.add_column("expected")
    table.add_column("got")
    table.add_column("conf", justify="right")
    table.add_column("dur", justify="right")
    table.add_column("status")
    for r in results:
        conf = (f"{r['perception_confidence']:.2f}"
                if r.get("perception_confidence") is not None else "-")
        status = "[green]✓[/]" if r["error"] is None else f"[red]✗ {r['error']}[/]"
        table.add_row(
            r["path"], r["expected_type"], r.get("actual_type") or "-",
            conf, f"{r['duration_ms']/1000:.1f}s", status,
        )
    console.print(table)
    console.print(f"[dim]results in:[/] {run_dir}")


@app.command("run")
def run_cmd(
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    perception: str = typer.Option(None, "--perception",
                                   help="Filter to one perception_type folder."),
    fixture: str = typer.Option(None, "--fixture",
                                help="Substring match on fixture filename."),
    timeout: int = typer.Option(120, "--timeout",
                                help="Per-request timeout in seconds."),
):
    """Run the smoke suite and save outputs to smoke/runs/<timestamp>/."""
    if perception and perception not in VALID_PERCEPTIONS:
        console.print(f"[red]invalid --perception:[/] {perception}")
        raise typer.Exit(2)

    fixtures = _discover_fixtures(perception, fixture)
    if not fixtures:
        console.print("[yellow]no fixtures matched.[/]")
        raise typer.Exit(2)

    # Sanity: is the service up?
    try:
        r = httpx.get(f"{base_url}/readyz", timeout=5)
        if r.status_code != 200:
            console.print(f"[red]service not ready:[/] {r.status_code}")
            raise typer.Exit(2)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]service unreachable at {base_url}:[/] {e}")
        raise typer.Exit(2) from e

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = RUNS_DIR / ts
    started_at = datetime.now(timezone.utc).isoformat()
    console.print(f"[cyan]running {len(fixtures)} fixture(s) → {run_dir}[/]")

    results = []
    with httpx.Client() as client:
        for ptype, image_path in fixtures:
            console.print(f"  [dim]→[/] {ptype}/{image_path.name}")
            results.append(_run_one(client, base_url, ptype, image_path, timeout))

    finished_at = datetime.now(timezone.utc).isoformat()
    _write_results(run_dir, base_url, results, started_at, finished_at)
    _print_summary(results, run_dir)

    failed = sum(1 for r in results if r["error"] is not None)
    raise typer.Exit(1 if failed else 0)


@app.command("promote")
def promote_cmd(
    run_id: str = typer.Argument(..., help="Run folder name under smoke/runs/"),
    tag: str = typer.Argument(..., help="Canonical tag, e.g. 'baseline-v1'"),
):
    """Copy an exploratory run into smoke/canonical/<tag>/ for git commit."""
    src = RUNS_DIR / run_id
    if not src.is_dir():
        console.print(f"[red]run not found:[/] {src}")
        raise typer.Exit(2)
    dst = CANONICAL_DIR / tag
    if dst.exists():
        console.print(f"[red]canonical tag already exists:[/] {dst}")
        console.print("[yellow]pick a new tag, or remove the existing folder first.[/]")
        raise typer.Exit(2)
    shutil.copytree(src, dst)
    console.print(f"[green]promoted[/] {run_id} → canonical/{tag}")
    console.print(f"[dim]commit with:[/] git add smoke/canonical/{tag} && git commit")


@app.command("compare")
def compare_cmd(
    left: str = typer.Argument(..., help="Run ID or canonical tag"),
    right: str = typer.Argument(..., help="Run ID or canonical tag"),
):
    """Diff two runs on classification + latency."""
    def _resolve(ref: str) -> Path:
        for base in (RUNS_DIR, CANONICAL_DIR):
            p = base / ref
            if (p / "manifest.json").exists():
                return p
        console.print(f"[red]can't find run:[/] {ref}")
        raise typer.Exit(2)

    lpath = _resolve(left)
    rpath = _resolve(right)
    lm = json.loads((lpath / "manifest.json").read_text())
    rm = json.loads((rpath / "manifest.json").read_text())
    lfix = {f["path"]: f for f in lm["fixtures"]}
    rfix = {f["path"]: f for f in rm["fixtures"]}
    all_keys = sorted(set(lfix) | set(rfix))

    table = Table(title=f"compare: {left} vs {right}")
    table.add_column("fixture")
    table.add_column(f"{left}")
    table.add_column(f"{right}")
    table.add_column("Δ latency", justify="right")
    for k in all_keys:
        l = lfix.get(k); r = rfix.get(k)
        lc = l["actual_type"] if l else "(missing)"
        rc = r["actual_type"] if r else "(missing)"
        if l and r:
            dlat = f"{(r['duration_ms'] - l['duration_ms'])/1000:+.1f}s"
        else:
            dlat = "-"
        same = lc == rc
        lcol = lc if same else f"[yellow]{lc}[/]"
        rcol = rc if same else f"[yellow]{rc}[/]"
        table.add_row(k, str(lcol), str(rcol), dlat)
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
