"""
Fetch a patent landing page.

Distinguishes the failure modes the spec calls out:
    ok | http_403 | http_404 | http_429 | http_other | timeout
    | non_html | too_large | request_error

- ``timeout`` from ``config.PATENT_WEB_FETCH_TIMEOUT_SECONDS``
- ``too_large`` from ``config.PATENT_WEB_MAX_RESPONSE_BYTES``
- ``non_html`` when Content-Type is not text/html or application/xhtml+xml

All failures return a populated ``FetchResult`` rather than raising; callers
turn this into a ``PatentSourceError`` and a partial ``PatentPageExtraction``.

Cached HTML is persisted under ``data/patent_web/`` for re-parsing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

try:
    import requests as _req_lib
    _REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _req_lib = None  # type: ignore[assignment]
    _REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]
    _BS4_AVAILABLE = False

import config

USER_AGENT = (
    "Mozilla/5.0 (compatible; AURA-PatentRecon/1.0; "
    "Stage-1 reconnaissance; +local-research-use)"
)

# Cleaned text excerpt cap (the raw HTML on disk is the full thing).
MAX_BODY_TEXT_CHARS = 20_000

CACHE_DIR: Path = config.BASE_DIR / "data" / "patent_web"


@dataclass
class FetchResult:
    """Outcome of a single page fetch.

    ``status`` is one of the ``FetchStatus`` literals in schemas.py.
    """
    status: str = "skipped"
    http_status: int = 0
    html: str = ""
    cleaned_text: str = ""
    cached_path: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_path_for(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.html"


def _clean_html_to_text(html: str) -> str:
    if not _BS4_AVAILABLE or not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())


def _is_html_content_type(ct: str) -> bool:
    if not ct:
        # Many sites omit Content-Type; we accept that case and let the parser decide.
        return True
    ct = ct.lower()
    return "text/html" in ct or "application/xhtml" in ct or "text/plain" in ct


def _classify_http_status(status: int) -> str:
    if status == 200:
        return "ok"
    if status == 403:
        return "http_403"
    if status == 404:
        return "http_404"
    if status == 429:
        return "http_429"
    return "http_other"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_patent_page(
    url: str,
    *,
    timeout: int | None = None,
    max_bytes: int | None = None,
) -> FetchResult:
    """Fetch *url* and return a structured result.

    Honours ``PATENT_WEB_FETCH_TIMEOUT_SECONDS`` and
    ``PATENT_WEB_MAX_RESPONSE_BYTES`` unless overridden.
    """
    if not _REQUESTS_AVAILABLE:
        return FetchResult(
            status="request_error", notes=["requests library not installed"]
        )

    timeout = timeout or config.PATENT_WEB_FETCH_TIMEOUT_SECONDS
    max_bytes = max_bytes or config.PATENT_WEB_MAX_RESPONSE_BYTES

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FetchResult(
            status="request_error",
            notes=[f"cannot create cache dir: {exc}"],
        )

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    # Stream so we can cap the response size cheaply.
    try:
        resp = _req_lib.get(  # type: ignore[union-attr]
            url, headers=headers, timeout=timeout, stream=True,
        )
    except _req_lib.exceptions.Timeout as exc:  # type: ignore[union-attr]
        return FetchResult(status="timeout", notes=[f"timeout after {timeout}s: {exc}"])
    except Exception as exc:
        return FetchResult(status="request_error", notes=[f"request failed: {exc}"])

    http_status = resp.status_code
    if http_status != 200:
        try:
            resp.close()
        except Exception:
            pass
        return FetchResult(
            status=_classify_http_status(http_status),
            http_status=http_status,
            notes=[f"HTTP {http_status} from {url}"],
        )

    content_type = (resp.headers.get("Content-Type") or "")
    if not _is_html_content_type(content_type):
        try:
            resp.close()
        except Exception:
            pass
        return FetchResult(
            status="non_html",
            http_status=200,
            notes=[f"non-HTML Content-Type: {content_type!r}"],
        )

    # Read body with hard byte cap.
    body_bytes = bytearray()
    too_large = False
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            body_bytes.extend(chunk)
            if len(body_bytes) > max_bytes:
                too_large = True
                break
    except Exception as exc:
        try:
            resp.close()
        except Exception:
            pass
        return FetchResult(
            status="request_error",
            http_status=200,
            notes=[f"body read failed: {exc}"],
        )
    finally:
        try:
            resp.close()
        except Exception:
            pass

    if too_large:
        return FetchResult(
            status="too_large",
            http_status=200,
            notes=[f"response exceeded {max_bytes} bytes; cap applied"],
        )

    encoding = resp.encoding or "utf-8"
    try:
        html = body_bytes.decode(encoding, errors="replace")
    except LookupError:
        html = body_bytes.decode("utf-8", errors="replace")

    cached_path = _cache_path_for(url)
    try:
        cached_path.write_text(html, encoding="utf-8", errors="replace")
        cached = str(cached_path)
    except OSError:
        cached = ""

    cleaned = _clean_html_to_text(html)[:MAX_BODY_TEXT_CHARS]

    return FetchResult(
        status="ok",
        http_status=200,
        html=html,
        cleaned_text=cleaned,
        cached_path=cached,
    )
