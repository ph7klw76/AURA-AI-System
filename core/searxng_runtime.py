"""
AURA SearXNG runtime bootstrap — mirrors the Ollama readiness pattern in
core/runtime.py but for a self-hosted SearXNG instance.

Public API
----------
    get_searxng_url() -> str
    check_searxng_health(...) -> dict
    ensure_searxng_ready(...) -> dict
    start_docker_desktop_if_needed(...) -> bool
    start_searxng_container_if_needed(...) -> bool
    start_searxng_compose_stack_if_configured(...) -> bool

All functions are safe to call on Linux/macOS; Windows-specific paths
(Docker Desktop launch) are gated on sys.platform.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REQUESTS_AVAILABLE = False

import config


# Headers sent with every SearXNG request.
# X-Forwarded-For / X-Real-IP are required by SearXNG's botdetection module
# when the instance is accessed directly (without an nginx reverse proxy).
# Sending 127.0.0.1 is correct for local Docker use.
_SEARXNG_HEADERS = {
    "X-Forwarded-For": "127.0.0.1",
    "X-Real-IP": "127.0.0.1",
}


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def get_searxng_url() -> str:
    """Return the configured SearXNG base URL."""
    return config.SEARXNG_URL


def _parse_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _tcp_reachable(url: str, timeout: float = 2.0) -> bool:
    host, port = _parse_host_port(url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def check_searxng_health(
    base_url: str | None = None,
    health_query: str | None = None,
    timeout: int | None = None,
) -> dict:
    """Send GET /search?q=<health_query>&format=json and return diagnostics.

    Return dict fields:
        reachable        : bool  — TCP + HTTP reachable
        json_api_enabled : bool  — 200 with valid JSON search body
        status_code      : int | None
        endpoint         : str
        message          : str   — human-readable summary
    """
    url = base_url or config.SEARXNG_URL
    query = health_query or config.SEARXNG_JSON_HEALTH_QUERY
    t = timeout if timeout is not None else config.SEARXNG_TIMEOUT_SECONDS
    endpoint = f"{url.rstrip('/')}/search"

    if not _REQUESTS_AVAILABLE:
        return {
            "reachable": False,
            "json_api_enabled": False,
            "status_code": None,
            "endpoint": endpoint,
            "message": "The 'requests' library is not installed (pip install requests).",
        }

    if not _tcp_reachable(url, timeout=2.0):
        return {
            "reachable": False,
            "json_api_enabled": False,
            "status_code": None,
            "endpoint": endpoint,
            "message": f"TCP connection refused at {url} — SearXNG is not running.",
        }

    try:
        resp = _requests.get(
            endpoint,
            params={"q": query, "format": "json"},
            headers=_SEARXNG_HEADERS,
            timeout=t,
        )
        status = resp.status_code

        if status == 200:
            try:
                data = resp.json()
            except ValueError:
                return {
                    "reachable": True,
                    "json_api_enabled": False,
                    "status_code": 200,
                    "endpoint": endpoint,
                    "message": (
                        "SearXNG is reachable but returned non-JSON for format=json. "
                        "Enable JSON output in settings.yml → formats: [html, json]"
                    ),
                }
            # Accept any of the known top-level keys a healthy response carries.
            if any(k in data for k in ("results", "answers", "query", "number_of_results")):
                return {
                    "reachable": True,
                    "json_api_enabled": True,
                    "status_code": 200,
                    "endpoint": endpoint,
                    "message": "SearXNG is healthy and the JSON API is enabled.",
                }
            return {
                "reachable": True,
                "json_api_enabled": False,
                "status_code": 200,
                "endpoint": endpoint,
                "message": (
                    "SearXNG responded with 200 but the JSON body has an unexpected "
                    "structure (no 'results', 'answers', or 'query' key)."
                ),
            }

        if status == 403:
            return {
                "reachable": True,
                "json_api_enabled": False,
                "status_code": 403,
                "endpoint": endpoint,
                "message": (
                    "SearXNG returned HTTP 403 for format=json. "
                    "JSON output is not enabled in settings.yml. "
                    "Add 'json' to the formats list: formats: [html, json]"
                ),
            }

        return {
            "reachable": True,
            "json_api_enabled": False,
            "status_code": status,
            "endpoint": endpoint,
            "message": f"SearXNG returned unexpected HTTP {status}.",
        }

    except Exception as exc:  # network timeouts, SSL errors, etc.
        return {
            "reachable": False,
            "json_api_enabled": False,
            "status_code": None,
            "endpoint": endpoint,
            "message": f"Request to SearXNG failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_subprocess(cmd: list[str], timeout: float = 15.0) -> tuple[bool, str]:
    """Run *cmd* and return (success, stdout_or_stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        output = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        return False, output
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]!r}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout:.0f}s"
    except Exception as exc:
        return False, f"Subprocess error: {exc}"


# ---------------------------------------------------------------------------
# Docker daemon
# ---------------------------------------------------------------------------

def _docker_daemon_responsive(timeout: float = 3.0) -> bool:
    ok, _ = _run_subprocess(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        timeout=timeout,
    )
    return ok


def _wait_until(check_fn, timeout_s: float, poll_interval: float = 1.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if check_fn():
            return True
        time.sleep(poll_interval)
    return False


# ---------------------------------------------------------------------------
# Docker Desktop (Windows-only)
# ---------------------------------------------------------------------------

def start_docker_desktop_if_needed(
    wait_timeout_s: float = 60.0,
    on_status=None,
) -> bool:
    """Attempt to launch Docker Desktop on Windows if the daemon is not up.

    On non-Windows platforms this is a no-op that returns whether the Docker
    daemon is already responsive.

    Returns True when the Docker daemon is responsive after the call.
    """
    say = on_status or (lambda _: None)

    if _docker_daemon_responsive():
        return True

    if not sys.platform.startswith("win"):
        say("Docker daemon is not responsive (non-Windows: auto-start skipped).")
        return False

    say("Docker daemon not responsive. Attempting to start Docker Desktop...")

    # Candidate paths for Docker Desktop on Windows
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker Desktop.exe"),
        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
    ]
    binary = next((c for c in candidates if os.path.isfile(c)), None)

    if binary:
        try:
            subprocess.Popen(
                [binary],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                close_fds=True,
            )
        except OSError as exc:
            say(f"Failed to launch Docker Desktop at {binary!r}: {exc}")
            return False
    else:
        # Fall back to Start-Menu launch via PowerShell
        ok, err = _run_subprocess(
            ["powershell", "-NoProfile", "-Command", "Start-Process 'Docker Desktop'"],
            timeout=15,
        )
        if not ok:
            say(f"Could not locate or launch Docker Desktop: {err}")
            return False

    say(f"Docker Desktop launch initiated; waiting up to {wait_timeout_s:.0f}s for daemon…")
    ready = _wait_until(_docker_daemon_responsive, timeout_s=wait_timeout_s, poll_interval=3.0)
    if ready:
        say("Docker daemon is responsive.")
    else:
        say(
            f"Docker daemon did not become responsive within {wait_timeout_s:.0f}s. "
            "Open Docker Desktop manually and retry."
        )
    return ready


# ---------------------------------------------------------------------------
# SearXNG container / compose stack startup
# ---------------------------------------------------------------------------

def start_searxng_compose_stack_if_configured(on_status=None) -> bool:
    """Run 'docker compose up -d' if a compose file or project directory is set.

    Returns True on success, False if not configured or if the command fails.
    """
    say = on_status or (lambda _: None)
    compose_file = config.SEARXNG_DOCKER_COMPOSE_FILE
    project_dir = config.SEARXNG_DOCKER_PROJECT_DIR

    if not compose_file and not project_dir:
        return False

    cmd = ["docker", "compose"]
    if compose_file:
        cmd += ["-f", compose_file]
    if project_dir:
        cmd += ["--project-directory", project_dir]
    cmd += ["up", "-d"]

    say(f"Starting SearXNG compose stack: {' '.join(cmd)}")
    ok, out = _run_subprocess(cmd, timeout=120.0)
    if ok:
        say("docker compose up -d succeeded.")
    else:
        say(f"docker compose up -d failed: {out}")
    return ok


def start_searxng_container_if_needed(on_status=None) -> bool:
    """Attempt to start a named Docker container for SearXNG.

    Uses the container name from SEARXNG_CONTAINER_NAME.
    Returns True on success.
    """
    say = on_status or (lambda _: None)
    name = config.SEARXNG_CONTAINER_NAME
    say(f"Trying to start Docker container '{name}'…")
    ok, out = _run_subprocess(["docker", "container", "start", name], timeout=30.0)
    if ok:
        say(f"Container '{name}' started.")
    else:
        say(f"Could not start container '{name}': {out}")
    return ok


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_searxng_ready(
    timeout_s: float | None = None,
    on_status=None,
) -> dict:
    """Ensure SearXNG is running and the JSON API is enabled.

    Workflow
    --------
    1. Health-check → if healthy, return immediately.
    2. If reachable but JSON disabled → return failure with clear instructions.
    3. If not reachable and SEARXNG_AUTO_START=1:
        a. On Windows, optionally start Docker Desktop first.
        b. Try docker compose up -d (if configured), then docker container start.
        c. Poll until healthy or timeout.
    4. Never hang indefinitely.

    Return dict fields:
        ok      : bool
        message : str
        health  : dict  (from check_searxng_health)
    """
    say = on_status or (lambda _: None)
    t = float(timeout_s if timeout_s is not None else config.SEARXNG_TIMEOUT_SECONDS)

    # Fast path
    health = check_searxng_health()
    if health["reachable"] and health["json_api_enabled"]:
        return {"ok": True, "message": health["message"], "health": health}

    # Reachable but JSON API disabled — auto-start cannot fix a config issue.
    if health["reachable"] and not health["json_api_enabled"]:
        return {"ok": False, "message": health["message"], "health": health}

    # Not reachable — check auto-start policy.
    if not config.SEARXNG_AUTO_START:
        return {
            "ok": False,
            "message": (
                f"SearXNG not reachable and SEARXNG_AUTO_START=0. "
                f"Start it manually at {config.SEARXNG_URL}. "
                f"Detail: {health['message']}"
            ),
            "health": health,
        }

    say("SearXNG not reachable — attempting auto-start…")

    # Step 1: ensure Docker daemon is responsive.
    if not _docker_daemon_responsive():
        if config.SEARXNG_AUTO_START_DOCKER_DESKTOP and sys.platform.startswith("win"):
            docker_ok = start_docker_desktop_if_needed(
                wait_timeout_s=min(t, 90.0),
                on_status=say,
            )
        else:
            docker_ok = False

        if not docker_ok:
            return {
                "ok": False,
                "message": (
                    "Docker daemon is not responsive. "
                    "Start Docker Desktop and retry, or start SearXNG manually."
                ),
                "health": health,
            }

    # Step 2: start SearXNG (compose preferred; named-container fallback).
    started = start_searxng_compose_stack_if_configured(on_status=say)
    if not started:
        started = start_searxng_container_if_needed(on_status=say)

    if not started:
        return {
            "ok": False,
            "message": (
                f"Could not start SearXNG container '{config.SEARXNG_CONTAINER_NAME}'. "
                "Run 'docker container start searxng' manually, or configure "
                "SEARXNG_DOCKER_COMPOSE_FILE / SEARXNG_DOCKER_PROJECT_DIR."
            ),
            "health": health,
        }

    # Step 3: poll until healthy or timeout.
    say(f"Waiting up to {t:.0f}s for SearXNG to become healthy…")
    poll_start = time.time()
    while time.time() - poll_start < t:
        health = check_searxng_health()
        if health["reachable"] and health["json_api_enabled"]:
            say("SearXNG is healthy.")
            return {"ok": True, "message": health["message"], "health": health}
        if health["reachable"] and not health["json_api_enabled"]:
            # Config issue discovered during startup — cannot recover automatically.
            return {"ok": False, "message": health["message"], "health": health}
        time.sleep(2.0)

    health = check_searxng_health()
    return {
        "ok": False,
        "message": (
            f"SearXNG did not become healthy within {t:.0f}s. "
            f"Last status: {health['message']}"
        ),
        "health": health,
    }
