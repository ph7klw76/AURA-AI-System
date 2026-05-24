"""
Verify SearXNG is reachable and JSON-enabled, then run a real patent query.

This is a step-by-step diagnostic — when something is off, the script
tells you EXACTLY what to fix instead of failing with an opaque error.

Usage
-----
    python scripts/verify_searxng.py

    # Override the URL one-off:
    python scripts/verify_searxng.py http://localhost:8888

Exit codes
----------
    0  Fully working (HTTP 200 + JSON format + at least one patent URL)
    1  Container reachable but JSON disabled  — see fix instructions
    2  Container not reachable                — see fix instructions
    3  AURA env not configured                — see fix instructions
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _print(label: str, value: str) -> None:
    print(f"  {label:<26} {value}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    url_override = argv[1] if len(argv) > 1 else None

    print("=" * 72)
    print("SearXNG verification")
    print("=" * 72)

    # ---- 1. Environment ----------------------------------------------------
    enabled = os.getenv("SEARXNG_ENABLED", "0").strip()
    url = url_override or os.getenv("SEARXNG_URL", "http://localhost:8080")
    aura_provider = os.getenv("AURA_PATENT_SEARCH_PROVIDER", "auto")
    print("\n[1/4] AURA environment")
    _print("SEARXNG_ENABLED", repr(enabled))
    _print("SEARXNG_URL", url)
    _print("AURA_PATENT_SEARCH_PROVIDER", repr(aura_provider))

    if enabled != "1":
        print(
            "\n⚠  SEARXNG_ENABLED is not '1'.  AURA will skip SearXNG even if\n"
            "   the container is running.  Fix (PowerShell, permanent):\n"
            "      [Environment]::SetEnvironmentVariable("
            "\"SEARXNG_ENABLED\", \"1\", \"User\")\n"
            "   Then close ALL terminals and re-open one."
        )
        # Continue anyway — we still want to test connectivity.

    # ---- 2. Docker container check ----------------------------------------
    print("\n[2/4] Docker container (best-effort)")
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=8,
        )
        lines = [l for l in out.stdout.splitlines() if "searxng" in l.lower()]
        if lines:
            for l in lines:
                _print("running", l)
        else:
            print(
                "  ⚠  No SearXNG container visible in `docker ps`.\n"
                "     If you started it via Docker Desktop, check the\n"
                "     Containers tab.  Otherwise:\n"
                "       cd deployment/searxng\n"
                "       docker compose up -d"
            )
    except FileNotFoundError:
        print("  (`docker` CLI not on PATH — skipping container check)")
    except Exception as exc:
        print(f"  (docker ps failed: {exc!s} — skipping container check)")

    # ---- 3. Plain HTTP reachability ----------------------------------------
    print(f"\n[3/4] HTTP reachability  ({url}/search?q=test)")
    try:
        import requests
    except ImportError:
        print("  ❌ `requests` library not installed.  pip install requests")
        return 3
    try:
        r = requests.get(
            f"{url.rstrip('/')}/search",
            params={"q": "test"},
            headers={
                "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1",
            },
            timeout=10,
        )
    except requests.exceptions.ConnectionError as exc:
        print(f"  ❌ Connection refused: {exc.__class__.__name__}")
        print(
            "\n   Fixes:\n"
            "     1. Container not running?  docker ps  (see step 2)\n"
            f"     2. Wrong URL?  Currently SEARXNG_URL={url!r}\n"
            "        Try `docker ps` and confirm the published port.\n"
            "     3. Container bound to 127.0.0.1 but you're behind\n"
            "        WSL2/Hyper-V?  Switch to 0.0.0.0:8080 in compose."
        )
        return 2
    except Exception as exc:
        print(f"  ❌ Request error: {exc.__class__.__name__}: {exc}")
        return 2

    _print("HTTP status", str(r.status_code))
    _print("Body size", f"{len(r.text)} bytes")
    if r.status_code != 200:
        print(
            f"\n   Unexpected status.  Container is reachable but not serving\n"
            f"   /search successfully.  Inspect: docker logs <container>"
        )
        return 2

    # ---- 4. JSON endpoint check -------------------------------------------
    print(f"\n[4/4] JSON endpoint  ({url}/search?q=test&format=json)")
    try:
        r = requests.get(
            f"{url.rstrip('/')}/search",
            params={"q": "test", "format": "json"},
            headers={
                "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1",
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"  ❌ Request error: {exc.__class__.__name__}: {exc}")
        return 2

    _print("HTTP status", str(r.status_code))
    if r.status_code == 403:
        print(
            "\n   ❌ HTTP 403 on format=json — JSON output is DISABLED in\n"
            "   your SearXNG settings.yml.  Fix:\n"
            "     1. Find settings.yml — usually one of:\n"
            "          deployment/searxng/searxng/settings.yml\n"
            "          (or wherever your docker-compose.yml mounts it)\n"
            "     2. Edit and add `- json` under `search.formats`:\n\n"
            "        search:\n"
            "          formats:\n"
            "            - html\n"
            "            - json     ← add this\n\n"
            "     3. Restart the container:\n"
            "          docker compose -f deployment/searxng/docker-compose.yml restart\n"
            "     4. Re-run this script.\n"
        )
        return 1
    if r.status_code != 200:
        print(f"  ❌ Got HTTP {r.status_code} — inspect with curl manually.")
        return 1

    try:
        data = r.json()
    except Exception as exc:
        print(f"  ❌ Response was not JSON: {exc.__class__.__name__}: {exc}")
        return 1

    results = data.get("results") or []
    unresponsive = data.get("unresponsive_engines") or []
    _print("Total results", str(len(results)))
    _print("Unresponsive engines", str(len(unresponsive)))
    if results:
        _print("First result", str(results[0].get("title", ""))[:60])
        _print("  URL", str(results[0].get("url", ""))[:80])

    # If every engine failed, surface WHY — this is the diagnostic that
    # tells you "engines blocked" vs "container has no internet".
    if not results and unresponsive:
        print("\n  ⚠  Every engine returned an error.  Top failures:")
        # Show up to 10 distinct error reasons + which engines reported them.
        seen_reasons: dict[str, list[str]] = {}
        for entry in unresponsive:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                eng, reason = str(entry[0]), str(entry[1])[:120]
            else:
                eng, reason = str(entry), "(no reason)"
            seen_reasons.setdefault(reason, []).append(eng)
        for reason, engs in list(seen_reasons.items())[:10]:
            example = ", ".join(engs[:5])
            extra = f" (+{len(engs) - 5} more)" if len(engs) > 5 else ""
            print(f"    [{reason}]")
            print(f"      affects: {example}{extra}")
        print()
        _print_engine_failure_guidance(reasons=list(seen_reasons.keys()))

    # ---- 4b. Engine inventory -----------------------------------------------
    print(f"\n[4b/4] Engine inventory  ({url}/config)")
    try:
        c = requests.get(
            f"{url.rstrip('/')}/config",
            headers={
                "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1",
            },
            timeout=10,
        )
        if c.status_code == 200:
            cfg = c.json()
            engines = cfg.get("engines", []) or []
            enabled = [e for e in engines if not e.get("disabled", False)]
            general = [
                e for e in enabled
                if "general" in (e.get("categories") or [])
            ]
            _print("Engines total", str(len(engines)))
            _print("Engines enabled", str(len(enabled)))
            _print("General-search enabled", str(len(general)))
            if general:
                names = sorted(e.get("name", "?") for e in general[:12])
                _print("  examples", ", ".join(names))
            if len(general) < 3:
                print(
                    "\n  ⚠  Only "
                    f"{len(general)} general-search engine(s) enabled.\n"
                    "     A 'test' query returned only 1 result because most\n"
                    "     engines are disabled in your settings.yml.  See the\n"
                    "     ENGINES FIX block below."
                )
        else:
            print(f"  (could not read /config: HTTP {c.status_code})")
    except Exception as exc:
        print(f"  (could not read /config: {exc})")

    # ---- 5. Real patent query through AURA's SearXNG provider --------------
    print("\n[5/4] Patent-targeted query through AURA's SearXNG provider")
    from integrations.patent_web.search_providers import (
        SearXNGPatentSearchProvider,
    )
    provider = SearXNGPatentSearchProvider(base_url=url, timeout=15)
    pq = 'site:patents.google.com "TADF" OLED emitter'
    resp = provider.search(pq, limit=8)
    _print("Query", pq)
    _print("Success", str(resp.success))
    _print("Results", str(len(resp.results)))
    if resp.failure_reason:
        _print("Failure", resp.failure_reason)
    if resp.results:
        for i, r in enumerate(resp.results[:5], start=1):
            print(f"    [{i}] {r.title[:70]}")
            print(f"        {r.url}")

    # ---- 6. Container internet reachability (if step 5 returned 0) -------
    if not resp.results:
        print("\n[6/6] Container internet reachability probe")
        try:
            import subprocess
            for cmd, label in [
                (["docker", "exec", "searxng", "wget", "-qO-",
                  "--timeout=5", "https://www.google.com/generate_204"],
                 "wget https://www.google.com/generate_204"),
                (["docker", "exec", "searxng", "wget", "-qO-",
                  "--timeout=5", "https://en.wikipedia.org/"],
                 "wget https://en.wikipedia.org/"),
            ]:
                try:
                    # Capture bytes — Wikipedia's HTML contains UTF-8
                    # that cp1252 can't decode on Windows.  We only
                    # care about the return code anyway.
                    r2 = subprocess.run(
                        cmd, capture_output=True, timeout=12,
                    )
                    ok = r2.returncode == 0
                    _print(label, "OK" if ok else f"FAIL (rc={r2.returncode})")
                    if not ok and r2.stderr:
                        try:
                            stderr_text = r2.stderr.decode(
                                "utf-8", errors="replace",
                            ).strip()[:120]
                            _print("  stderr", stderr_text)
                        except Exception:
                            pass
                except FileNotFoundError:
                    print("  (docker CLI not on PATH — skipping)")
                    break
                except subprocess.TimeoutExpired:
                    _print(label, "TIMEOUT")
        except Exception as exc:
            print(f"  (probe failed: {exc})")

    print("\n" + "=" * 72)
    if resp.success and resp.results:
        print("✅ SearXNG is fully working.  Set in env permanently:")
        print(
            "   PowerShell:\n"
            "     [Environment]::SetEnvironmentVariable("
            "\"SEARXNG_ENABLED\", \"1\", \"User\")\n"
            "     [Environment]::SetEnvironmentVariable("
            "\"AURA_PATENT_SEARCH_PROVIDER\", \"searxng\", \"User\")"
        )
        return 0

    # Distinguish three failure modes from earlier step outcomes.
    # ``results`` here is from the step-4 generic query; ``resp`` is
    # from the step-5 patent query.
    if results and not resp.results:
        # Generic query works (10+ results), patent query doesn't.
        # This is the well-documented "Google rejects site:-restricted
        # queries from SearXNG" pattern — engines are fine, but Google
        # silently drops site:-restricted queries and SearXNG's fallback
        # engines (DDG/Bing/Brave) don't honour site: either.
        print(
            "⚠  Generic queries work ({} results) but patent-targeted "
            "site:-restricted queries return 0.".format(len(results))
        )
        print(
            "\nROOT CAUSE: in 2025-2026 Google rejects ``site:`` queries\n"
            "from SearXNG-style scrapers.  Other engines (DDG, Bing,\n"
            "Brave) either don't honour the ``site:`` operator the same\n"
            "way OR return generic hits that AURA then filters out as\n"
            "off-domain.  This is NOT an engines-disabled problem.\n"
        )
        print(
            "WORKAROUNDS:\n"
            "  1. AURA's patent provider already plans a CROSS-DOMAIN\n"
            "     fallback query (no ``site:`` filter, then client-side\n"
            "     URL filter for patent hosts).  Make sure you're on the\n"
            "     latest patent_intelligence module — restart AURA.\n"
            "  2. For ad-hoc queries, drop the ``site:`` prefix.  Try:\n"
            "       python scripts\\verify_searxng.py\n"
            "       (the patent probe runs ONLY the site:-restricted query;\n"
            "        AURA itself also runs the cross-domain fallback.)\n"
            "  3. If you specifically want patent-host coverage and don't\n"
            "     mind it being heuristic, raise the patent-web fetch cap:\n"
            "         PATENT_WEB_MAX_RESULTS_PER_QUERY=20\n"
            "         PATENT_WEB_MAX_PAGES_TO_FETCH=40"
        )
        return 1

    if not results and unresponsive:
        # All engines threw errors — root cause printed earlier.
        print(
            "⚠  Generic query also returned 0 — engines are unreachable.\n"
            "   See the per-engine failure breakdown earlier in this output\n"
            "   and apply the root-cause fix it printed."
        )
        return 1

    if not results:
        print(
            "⚠  Generic query returned 0 results with no engine errors.\n"
            "   This is unusual — likely your settings.yml has nearly all\n"
            "   engines disabled.\n"
        )
        print(_ENGINES_FIX_TEXT)
        return 1

    # Fallback (shouldn't reach here).
    print("⚠  SearXNG is reachable + JSON-enabled but returned 0 patent URLs.")
    return 1


def _print_engine_failure_guidance(*, reasons: list[str]) -> None:
    """When all engines fail, point at the most-likely root cause."""
    reasons_joined = " | ".join(reasons).lower()

    if any(k in reasons_joined for k in (
        "name or service not known", "nodename nor servname",
        "getaddrinfo", "temporary failure in name resolution",
        "could not resolve host",
    )):
        print(
            "  → ROOT CAUSE: the SearXNG container cannot resolve DNS.\n"
            "    Fix on Windows + Docker Desktop:\n"
            "      docker exec searxng nslookup www.google.com\n"
            "    If that fails too, Docker Desktop's networking is broken.\n"
            "    Try:\n"
            "      1. Settings → Resources → Network → reset DNS to 'Automatic'\n"
            "      2. Quit Docker Desktop fully + relaunch\n"
            "      3. If using WSL2 backend, run:  wsl --shutdown  then relaunch."
        )
        return

    if any(k in reasons_joined for k in (
        "connection refused", "no route to host",
        "network is unreachable",
    )):
        print(
            "  → ROOT CAUSE: the SearXNG container has no outbound network.\n"
            "    Verify from inside the container:\n"
            "      docker exec searxng wget -qO- https://www.google.com\n"
            "    If that fails, Docker's bridge network is misconfigured.\n"
            "    Fix:  in docker-compose.yml ensure no custom 'network_mode',\n"
            "    or run  docker network prune  + restart the container."
        )
        return

    if any(k in reasons_joined for k in (
        "ssl", "certificate", "cert verify failed",
    )):
        print(
            "  → ROOT CAUSE: TLS/SSL handshake failure (corporate proxy?).\n"
            "    If you're behind an HTTPS-inspecting proxy, SearXNG can't\n"
            "    validate the certificates that the proxy substitutes.\n"
            "    Fix: install your corporate CA into the container, or set\n"
            "    HTTP(S)_PROXY env vars in docker-compose.yml."
        )
        return

    if any(k in reasons_joined for k in (
        "429", "too many requests", "rate", "blocked", "captcha",
        "anomaly", "forbidden", "403",
    )):
        print(
            "  → ROOT CAUSE: engines are returning HTTP 429/403 (rate-limited\n"
            "    or bot-blocked).  In 2025-2026 Google/Bing/Brave aggressively\n"
            "    block SearXNG instances.  Mitigations:\n"
            "      1. Wait 30-60 min for the IP cooldown.\n"
            "      2. Edit settings.yml:\n"
            "         search:\n"
            "           formats: [html, json]\n"
            "         outgoing:\n"
            "           request_timeout: 15.0\n"
            "           useragent_suffix: ''     # blanker UA helps\n"
            "      3. Add engines that DON'T block: mojeek, wikipedia,\n"
            "         marginalia, brave (if not blocked from your IP), yacy.\n"
            "      4. Restart container:  docker restart searxng"
        )
        return

    if "limiter" in reasons_joined or "max_request" in reasons_joined:
        print(
            "  → ROOT CAUSE: SearXNG's request limiter is filtering responses.\n"
            "    In settings.yml ensure:\n"
            "         server:\n"
            "           limiter: false\n"
            "    Then restart:  docker restart searxng"
        )
        return

    # Generic.
    print(
        "  → ROOT CAUSE: not clearly diagnosable from reasons alone.\n"
        "    Inspect the container logs for the actual exceptions:\n"
        "         docker logs searxng --tail 200\n"
        "    Look for keywords: 'timeout', 'refused', 'DNS', 'SSL', '429'."
    )


_ENGINES_FIX_TEXT = """\
=========================== ENGINES FIX ===========================
SearXNG ships with most engines DISABLED for privacy reasons.  For
patent search to work, you need at least Google, Bing, DuckDuckGo,
and Qwant enabled.  Here's how:

1. Find your settings.yml.  Common locations:
   - deployment/searxng/searxng/settings.yml
   - C:\\Users\\<you>\\searxng\\settings.yml
   - inside the container at /etc/searxng/settings.yml
   Use Docker Desktop -> your searxng container -> Files tab to inspect.

2. Open settings.yml and find the 'engines:' section (near the bottom).
   For each of these engines, ensure 'disabled: false' (or remove the
   'disabled: true' line entirely):

       - name: google
         engine: google
         categories: [general]
         disabled: false
         shortcut: g
         use_mobile_ui: false

       - name: bing
         engine: bing
         categories: [general]
         disabled: false
         shortcut: bi

       - name: duckduckgo
         engine: duckduckgo
         categories: [general]
         disabled: false
         shortcut: ddg

       - name: qwant
         engine: qwant
         categories: [general]
         disabled: false
         shortcut: qw

       - name: startpage
         engine: startpage
         categories: [general]
         disabled: false
         shortcut: sp

3. Restart the container so it re-reads the config:
       docker restart searxng
       # or, if you used compose:
       docker compose -f deployment/searxng/docker-compose.yml restart

4. Re-run this script.  Step 4b should show 5+ general-search engines
   enabled, and the patent query in step 5 should return real URLs.

NOTE: AURA's SearXNG docker-compose ships with a curated settings.yml
under deployment/searxng/.  If you started SearXNG some other way, the
engines may be defaulted off — copy AURA's settings.yml as a starting
point:
       deployment/searxng/searxng/settings.yml
====================================================================
"""


if __name__ == "__main__":
    sys.exit(main())
