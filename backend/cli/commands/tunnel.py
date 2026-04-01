"""
champmail tunnel — Expose local backend publicly via localtunnel.

  tunnel start [--port 8000] [--subdomain myapp]
  tunnel status

Uses localtunnel (npx localtunnel) — no account needed.
The public URL is written to ~/.champmail/tunnel.json and used by
other CLI commands as the PUBLIC_API_URL.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import click

from cli.context import CliContext
from cli.repl_skin import print_error, print_info, print_kv, print_section, print_success, print_warning
from cli.session import SESSION_DIR


TUNNEL_FILE = SESSION_DIR / "tunnel.json"


def _load_tunnel() -> dict:
    if TUNNEL_FILE.exists():
        try:
            return json.loads(TUNNEL_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_tunnel(data: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    TUNNEL_FILE.write_text(json.dumps(data, indent=2))


@click.group()
def tunnel() -> None:
    """Tunnel local backend to the internet (localtunnel)."""


@tunnel.command("start")
@click.option("--port", default=8000, show_default=True, help="Local port to expose.")
@click.option("--subdomain", default=None, help="Requested subdomain (best-effort).")
@click.option("--wait", default=8, show_default=True, help="Seconds to wait for tunnel URL.")
@click.pass_obj
def start_tunnel(obj, port, subdomain, wait) -> None:
    """Start a localtunnel and store the public URL.

    Requires node/npx to be installed.
    The public URL is saved to ~/.champmail/tunnel.json.
    """
    # Build command
    cmd = ["npx", "--yes", "localtunnel", "--port", str(port)]
    if subdomain:
        cmd += ["--subdomain", subdomain]

    print_info(f"Starting localtunnel on port {port}…")
    print_info(f"Running: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print_error("npx not found. Install Node.js: https://nodejs.org")
        raise SystemExit(1)

    url = None
    deadline = time.time() + wait
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.2)
            continue
        line = line.strip()
        if line:
            print_info(f"  {line}")
        if "https://" in line:
            # localtunnel outputs: "your url is: https://..."
            for token in line.split():
                if token.startswith("https://"):
                    url = token.rstrip(".")
                    break
        if url:
            break

    if not url:
        print_warning("Could not detect tunnel URL from output within timeout.")
        print_info("Check the process output above — copy the https:// URL manually.")
        print_info(f"Tunnel process PID: {proc.pid}")
        _save_tunnel({"pid": proc.pid, "port": port, "url": None})
        if obj.json_output:
            print(json.dumps({"ok": False, "pid": proc.pid, "error": "URL not detected"}))
        raise SystemExit(1)

    _save_tunnel({"pid": proc.pid, "port": port, "url": url})

    # Also update PUBLIC_API_URL in .env for the backend to use
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        text = env_path.read_text()
        if "PUBLIC_API_URL=" in text:
            lines = [f"PUBLIC_API_URL={url}" if l.startswith("PUBLIC_API_URL=") else l for l in text.splitlines()]
            env_path.write_text("\n".join(lines) + "\n")
        else:
            with env_path.open("a") as f:
                f.write(f"\nPUBLIC_API_URL={url}\n")

    if obj.json_output:
        print(json.dumps({"ok": True, "url": url, "port": port, "pid": proc.pid}))
    else:
        print_success(f"Tunnel active: {url}")
        print_kv("Local port", str(port))
        print_kv("PID", str(proc.pid))
        print_info("\nView sent emails at: https://ethereal.email/messages")
        print_info(f"Backend webhook URL: {url}/api/v1/webhooks/email")
        print_info("\nTunnel is running in background. Kill with:")
        print_info(f"  kill {proc.pid}")


@tunnel.command("status")
@click.pass_obj
def tunnel_status(obj, ) -> None:
    """Show saved tunnel info."""
    data = _load_tunnel()

    if not data:
        if obj.json_output:
            print(json.dumps({"ok": False, "error": "No tunnel info found"}))
        else:
            print_warning("No tunnel session found. Run:  champmail tunnel start")
        return

    pid = data.get("pid")
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            alive = False

    if obj.json_output:
        print(json.dumps({"ok": True, **data, "alive": alive}))
    else:
        print_section("Tunnel Status")
        print_kv("URL", data.get("url") or "(unknown)")
        print_kv("Port", str(data.get("port", "")))
        print_kv("PID", str(pid or ""))
        if alive:
            print_success("Process is alive.")
        else:
            print_warning("Process appears to have stopped.")
