"""sa-cli — thin client that talks to a running shopping-agent service.

Usage:
  sa-cli chat                       # interactive
  sa-cli chat --text "what's this?" --image /path/to/pantry.jpg
  sa-cli session <session_id>       # show transcript
  sa-cli health                     # probe /readyz
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

app = typer.Typer(help="Shopping Agent CLI (talks to local service).")
console = Console()

DEFAULT_BASE_URL = "http://127.0.0.1:3000"


def _post_chat(
    base_url: str,
    text: str | None,
    image_paths: list[Path],
    audio_path: Path | None,
    session_id: str | None,
) -> dict:
    images = [
        {"kind": "path", "value": str(p.resolve()), "mime_type": "image/jpeg"}
        for p in image_paths
    ]
    audio = (
        {"kind": "path", "value": str(audio_path.resolve()), "mime_type": "audio/wav"}
        if audio_path
        else None
    )
    body = {
        "session_id": session_id,
        "text": text,
        "images": images,
        "audio": audio,
    }
    r = httpx.post(f"{base_url}/chat", json=body, timeout=90.0)
    r.raise_for_status()
    return r.json()


@app.command()
def health(base_url: str = DEFAULT_BASE_URL) -> None:
    """Probe /readyz."""
    r = httpx.get(f"{base_url}/readyz", timeout=5.0)
    console.print(Panel.fit(Pretty(r.json()), title=f"readyz [{r.status_code}]"))


@app.command()
def chat(
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text prompt"),
    image: list[Path] = typer.Option(
        [], "--image", "-i", help="Image file path (repeatable)"
    ),
    audio: Optional[Path] = typer.Option(None, "--audio", "-a", help="Audio file path"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s"),
    base_url: str = DEFAULT_BASE_URL,
    once: bool = typer.Option(False, "--once", help="Send one turn, don't loop"),
) -> None:
    """Send a turn to /chat. Without --once, enters an interactive loop."""
    current_session = session_id

    def one_turn(txt: str | None, imgs: list[Path], aud: Path | None) -> None:
        nonlocal current_session
        try:
            resp = _post_chat(base_url, txt, imgs, aud, current_session)
        except httpx.HTTPError as e:
            console.print(f"[red]request failed:[/red] {e}")
            return
        current_session = resp["session_id"]
        console.print(
            Panel.fit(
                Pretty(resp["understanding"]),
                title=f"understanding  [session={current_session[:8]}  turn={resp['turn_id'][:8]}]",
            )
        )

    if once or text or image or audio:
        one_turn(text, list(image), audio)
        if once:
            return

    console.print(
        "[dim]Interactive mode. Commands:  /image <path>  /audio <path>  /quit[/dim]"
    )
    pending_images: list[Path] = list(image)
    pending_audio: Path | None = audio
    while True:
        try:
            line = console.input("[bold cyan]you> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line.startswith("/image "):
            p = Path(line.split(" ", 1)[1].strip()).expanduser()
            if not p.exists():
                console.print(f"[red]not found:[/red] {p}")
                continue
            pending_images.append(p)
            console.print(f"[dim]attached image: {p}[/dim]")
            continue
        if line.startswith("/audio "):
            p = Path(line.split(" ", 1)[1].strip()).expanduser()
            if not p.exists():
                console.print(f"[red]not found:[/red] {p}")
                continue
            pending_audio = p
            console.print(f"[dim]attached audio: {p}[/dim]")
            continue
        one_turn(line, pending_images, pending_audio)
        pending_images = []
        pending_audio = None


@app.command()
def session(session_id: str, base_url: str = DEFAULT_BASE_URL) -> None:
    """Show a session's turn history."""
    r = httpx.get(f"{base_url}/sessions/{session_id}", timeout=5.0)
    if r.status_code == 404:
        console.print("[red]session not found[/red]")
        raise typer.Exit(1)
    r.raise_for_status()
    console.print(Pretty(r.json()))


def main() -> None:  # entry-point shim for pyproject script
    app()


if __name__ == "__main__":
    main()
