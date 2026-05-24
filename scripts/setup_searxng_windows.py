"""
AURA SearXNG one-time setup helper.

Supported platforms: Windows (primary), macOS / Linux (basic checks only).

What this script does
---------------------
1. Verifies that Docker CLI is on PATH.
2. Checks that Docker daemon is responsive.
3. Validates (or creates) the deployment/searxng/settings.yml file, ensuring
   the JSON output format is enabled.
4. Optionally generates a random secret key in settings.yml and
   docker-compose.yml (safer than the placeholder).
5. Prints ready-to-run commands for the first startup.
6. Prints the exact .env lines to add to AURA.

What this script does NOT do
-----------------------------
- It does NOT install Docker Desktop.  That requires a user download from
  https://www.docker.com/products/docker-desktop/ and WSL 2 integration.
- It does NOT start Docker Desktop (use the runtime auto-start for that).
- It does NOT pull the SearXNG image (docker compose up -d handles that).

Usage
-----
    python scripts/setup_searxng_windows.py [--gen-secret] [--dry-run]

Flags
-----
--gen-secret   Generate a fresh random secret key and write it to
               settings.yml and docker-compose.yml.
--dry-run      Print what would be changed without writing files.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to repo root, which is one level above scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DEPLOY_DIR = REPO_ROOT / "deployment" / "searxng"
COMPOSE_FILE = DEPLOY_DIR / "docker-compose.yml"
SETTINGS_FILE = DEPLOY_DIR / "settings.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

PLACEHOLDER_SECRET = "change_me_to_a_random_secret_key_at_least_32_chars"

# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def _info(msg: str) -> None:
    print(f"  [  ] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}", file=sys.stderr)


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ---------------------------------------------------------------------------
# Docker checks
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: float = 10.0) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())
    except FileNotFoundError:
        return False, f"{cmd[0]!r} not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as exc:
        return False, str(exc)


def check_docker_cli() -> bool:
    _section("Docker CLI check")
    ok, out = _run(["docker", "--version"])
    if ok:
        _ok(f"Docker CLI found: {out}")
        return True
    _err(
        "Docker CLI not found on PATH.\n"
        "  Install Docker Desktop from https://www.docker.com/products/docker-desktop/\n"
        "  Then re-run this script."
    )
    return False


def check_docker_daemon() -> bool:
    _section("Docker daemon check")
    ok, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if ok:
        _ok(f"Docker daemon responsive (server version: {out})")
        return True
    _warn(
        "Docker daemon is not running.\n"
        "  On Windows: open Docker Desktop from the Start Menu.\n"
        "  Wait until the whale icon in the taskbar shows 'Docker Desktop is running'.\n"
        "  Then re-run this script (or just run 'docker compose up -d' and AURA will\n"
        "  auto-start Docker Desktop for you if SEARXNG_AUTO_START_DOCKER_DESKTOP=1)."
    )
    return False


# ---------------------------------------------------------------------------
# Settings file validation / generation
# ---------------------------------------------------------------------------

def _has_json_format(content: str) -> bool:
    """Return True if the settings.yml text already enables json format."""
    # Match 'json' appearing under a `formats:` block.
    in_formats = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("formats:"):
            in_formats = True
            continue
        if in_formats:
            if stripped.startswith("-"):
                if "json" in stripped:
                    return True
            elif stripped and not stripped.startswith("#"):
                in_formats = False  # exited the formats block
    return False


def check_settings_yml(dry_run: bool = False) -> bool:
    _section("SearXNG settings.yml check")

    if not SETTINGS_FILE.exists():
        _warn(f"settings.yml not found at {SETTINGS_FILE}")
        _info("The deployment/searxng/settings.yml file ships with the repository.")
        _info("Make sure you have run 'git pull' and the file is present.")
        return False

    content = SETTINGS_FILE.read_text(encoding="utf-8")

    if _has_json_format(content):
        _ok("JSON output format is enabled in settings.yml.")
    else:
        _warn("JSON output format is NOT enabled in settings.yml.")
        _warn(
            "AURA's health check will receive HTTP 403 for format=json "
            "and will refuse to use SearXNG."
        )
        _info("Fix: open deployment/searxng/settings.yml and ensure:")
        _info("  formats:")
        _info("    - html")
        _info("    - json")
        return False

    if PLACEHOLDER_SECRET in content:
        _warn(
            "settings.yml still contains the placeholder secret key.\n"
            "  Run with --gen-secret to replace it, or set a unique value manually.\n"
            "  A weak secret key is a security risk if SearXNG is exposed beyond localhost."
        )

    return True


# ---------------------------------------------------------------------------
# Secret key generation
# ---------------------------------------------------------------------------

def generate_secret_key(dry_run: bool = False) -> str:
    key = secrets.token_hex(32)
    _section("Generating random secret key")
    _info(f"New key: {key}")

    for fpath in (SETTINGS_FILE, COMPOSE_FILE):
        if not fpath.exists():
            _warn(f"File not found, skipping: {fpath}")
            continue
        content = fpath.read_text(encoding="utf-8")
        if PLACEHOLDER_SECRET not in content:
            _info(f"Placeholder not found in {fpath.name} — no change needed.")
            continue
        new_content = content.replace(PLACEHOLDER_SECRET, key)
        if dry_run:
            _info(f"[dry-run] Would update secret key in {fpath.name}")
        else:
            fpath.write_text(new_content, encoding="utf-8")
            _ok(f"Updated secret key in {fpath.name}")

    return key


# ---------------------------------------------------------------------------
# Docker compose check
# ---------------------------------------------------------------------------

def check_compose_file() -> bool:
    _section("Docker Compose file check")
    if not COMPOSE_FILE.exists():
        _err(f"docker-compose.yml not found at {COMPOSE_FILE}")
        return False
    _ok(f"docker-compose.yml found at {COMPOSE_FILE}")
    return True


# ---------------------------------------------------------------------------
# Image pull check (informational)
# ---------------------------------------------------------------------------

def check_image_pulled() -> bool:
    _section("SearXNG Docker image check")
    ok, out = _run(["docker", "images", "-q", "searxng/searxng:latest"])
    if ok and out.strip():
        _ok("searxng/searxng:latest image is already present locally.")
        return True
    _info("searxng/searxng:latest image is not yet pulled.")
    _info("It will be pulled automatically when you run 'docker compose up -d'.")
    return False


# ---------------------------------------------------------------------------
# Final instructions
# ---------------------------------------------------------------------------

def print_next_steps(daemon_ok: bool) -> None:
    _section("Next steps")

    if not daemon_ok:
        _info("1. Start Docker Desktop.")
        _info("2. Wait until Docker Desktop shows 'Engine running'.")
        _info("3. Then:")
    else:
        _info("Docker daemon is running. Run:")

    rel = DEPLOY_DIR.relative_to(REPO_ROOT)
    print(f"\n    cd {rel}")
    print("    docker compose up -d\n")
    print("  Then add to your .env:\n")
    print("    SEARXNG_ENABLED=1")
    print("    SEARXNG_URL=http://localhost:8080")
    print("    SEARXNG_AUTO_START=1")
    print("    SEARXNG_AUTO_START_DOCKER_DESKTOP=1")
    print(f"    SEARXNG_DOCKER_PROJECT_DIR={rel}")
    print()
    print("  Verify JSON API:")
    print('    curl "http://localhost:8080/search?q=test&format=json"')
    print()
    print("  Then start AURA as normal:")
    print("    python main.py")
    print()
    _info(
        "AURA will call ensure_searxng_ready() when Deep Research is invoked.\n"
        "  If SearXNG is not running it will attempt to start the container "
        "automatically."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AURA SearXNG one-time setup helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gen-secret",
        action="store_true",
        help="Generate a random secret key and write it to settings.yml and docker-compose.yml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files",
    )
    args = parser.parse_args()

    print("\nAURA SearXNG Setup Helper")
    print("-" * 60)

    if sys.platform.startswith("win"):
        _info("Platform: Windows — Docker Desktop with WSL 2 / Linux containers expected.")
    elif sys.platform == "darwin":
        _info("Platform: macOS — Docker Desktop or OrbStack expected.")
    else:
        _info(f"Platform: {sys.platform} — Docker Engine (server) expected.")

    cli_ok = check_docker_cli()
    if not cli_ok:
        return 1

    daemon_ok = check_docker_daemon()
    compose_ok = check_compose_file()
    settings_ok = check_settings_yml(dry_run=args.dry_run)

    if daemon_ok:
        check_image_pulled()

    if args.gen_secret:
        generate_secret_key(dry_run=args.dry_run)

    all_ok = cli_ok and compose_ok and settings_ok
    _section("Summary")
    if all_ok:
        _ok("All checks passed.")
    else:
        _warn("Some checks failed — see details above.")

    if not args.gen_secret and SETTINGS_FILE.exists():
        content = SETTINGS_FILE.read_text(encoding="utf-8")
        if PLACEHOLDER_SECRET in content:
            _info("Tip: run with --gen-secret to replace the placeholder secret key.")

    print_next_steps(daemon_ok)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
