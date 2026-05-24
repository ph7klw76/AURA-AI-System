"""
AURA runtime bootstrap — optional Ollama readiness helper.

Provides:
    ensure_ollama_ready(timeout_s=30, pull_if_missing=False, on_status=None,
                        model_name=None)
        Start Ollama daemon if not already running and ensure the specified
        model is installed.  Raises RuntimeError on failure.

This module is called automatically by main.py when the user chooses a local
model (one that contains a colon).  The interactive path calls it through
_bootstrap_ollama(model_name=…) and the deep-research CLI also calls it when
a local model is requested.

It can also be invoked by scripts (e.g. diagnostics) or by setting
AURA_USE_OLLAMA_BOOTSTRAP=1, although that variable is not used by main.py.

Kept here for backward compatibility and for users who want to enforce
a local-only workflow.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import config


_OLLAMA_DEFAULT_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _ollama_port_open(host_port: str = _OLLAMA_DEFAULT_HOST, timeout: float = 1.0) -> bool:
    """Return True if something is listening on Ollama's port."""
    if "://" in host_port:
        host_port = host_port.split("://", 1)[1]
    if "/" in host_port:
        host_port = host_port.split("/", 1)[0]
    if ":" not in host_port:
        host, port_s = host_port, "11434"
    else:
        host, port_s = host_port.rsplit(":", 1)
    try:
        port = int(port_s)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ollama_api_responsive(timeout: float = 2.0) -> bool:
    """Return True if /api/tags answers (a stronger check than just the TCP port)."""
    try:
        import ollama
        # ollama.list() throws if the daemon is down or upgrading
        ollama.list()
        return True
    except Exception:
        return False


def _model_present(model_name: str) -> bool:
    """Return True if `model_name` is in `ollama list`."""
    try:
        import ollama
        result = ollama.list()
        # ollama-python returns either {'models': [...]} or a ListResponse object
        models = getattr(result, "models", None)
        if models is None and isinstance(result, dict):
            models = result.get("models", [])
        if not models:
            return False
        names: set[str] = set()
        for m in models:
            # accept both dict and ListResponse.Model
            name = getattr(m, "model", None) or (m.get("model") if isinstance(m, dict) else None)
            if not name:
                name = getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None)
            if name:
                names.add(name)
        return model_name in names
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _find_ollama_binary() -> str | None:
    """Locate the ollama executable. Returns None if not on PATH or in the
    standard Windows / macOS / Linux install paths."""
    found = shutil.which("ollama")
    if found:
        return found

    # Common Windows install locations
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
        # macOS
        Path("/Applications/Ollama.app/Contents/MacOS/ollama"),
        # Linux
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _start_ollama_background(binary: str) -> None:
    """Launch the Ollama serve daemon detached from this Python process."""
    is_windows = sys.platform.startswith("win")
    if is_windows:
        # CREATE_NO_WINDOW = 0x08000000, DETACHED_PROCESS = 0x00000008
        creationflags = 0x08000000 | 0x00000008
        subprocess.Popen(
            [binary, "serve"],
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    else:
        subprocess.Popen(
            [binary, "serve"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )


def _wait_until(check_fn, timeout_s: float, poll_interval: float = 0.5) -> bool:
    """Poll check_fn() until it returns True or `timeout_s` elapses."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if check_fn():
            return True
        time.sleep(poll_interval)
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_ollama_ready(
    timeout_s: float = 30.0,
    pull_if_missing: bool = False,
    on_status=None,
    model_name: str | None = None,
) -> None:
    """Ensure Ollama is running and the specified *model_name* is installed.

    If *model_name* is None or empty, the active model from `config.get_model_name()`
    is used.

    1. If Ollama is already responsive → return.
    2. Otherwise, locate the `ollama` binary and start `ollama serve` in the
       background.
    3. Wait up to `timeout_s` for the daemon to become responsive.
    4. Verify the model is installed. If not, raise RuntimeError
       with a one-line `ollama pull <model>` instruction (or pull it
       automatically when `pull_if_missing=True`).

    Optional `on_status(message: str)` callback receives human-friendly status
    strings — main.py uses it to print rich-coloured lines.
    """
    say = on_status or (lambda _msg: None)
    name = model_name or config.get_model_name()

    # Fast path — daemon already responding
    if _ollama_api_responsive():
        if not _model_present(name):
            _handle_missing_model(name, pull_if_missing, say)
        return

    say(f"Ollama not responding on {_OLLAMA_DEFAULT_HOST}. Starting it...")
    binary = _find_ollama_binary()
    if not binary:
        raise RuntimeError(
            "Ollama is not installed or not on PATH. Install it from "
            "https://ollama.com/download and re-run."
        )

    _start_ollama_background(binary)
    say(f"Launched {binary}; waiting up to {timeout_s:.0f}s for it to come up...")

    # Wait for the API to actually answer (port open is not enough — Ollama
    # sometimes restarts mid-request when an upgrade is pending)
    if not _wait_until(_ollama_api_responsive, timeout_s=timeout_s):
        raise RuntimeError(
            f"Ollama did not become responsive within {timeout_s:.0f}s. "
            "It may be upgrading itself; wait 30s and retry, or run "
            "`ollama serve` in another terminal to see the log."
        )
    say("Ollama is up.")

    if not _model_present(name):
        _handle_missing_model(name, pull_if_missing, say)


def _handle_missing_model(model_name: str, pull_if_missing: bool, say) -> None:
    if pull_if_missing:
        say(f"Model {model_name!r} missing — running `ollama pull {model_name}` (this may take several minutes)...")
        try:
            import ollama
            ollama.pull(model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Could not pull {model_name!r}: {exc}. "
                f"Run `ollama pull {model_name}` manually."
            ) from exc
        say(f"Pulled {model_name}.")
        return

    raise RuntimeError(
        f"Required model {model_name!r} is not installed in Ollama. "
        f"Run:  ollama pull {model_name}"
    )
