"""
Normalisation utilities for patent records.

- ``normalise_publication_number(pub_number)`` returns a canonical key.
  Strips whitespace, dashes, slashes, and the common trailing kind-code
  (A1, A2, B1, …) so ``"US-2023/012345 A1"``, ``"US 2023012345 A1"``, and
  ``"US2023012345A1"`` collapse to the same key.

- ``normalise_url(url)`` lowercases the host, drops query string and fragment,
  and strips trailing slashes so two URLs that differ only in tracking params
  produce the same key.

- ``normalise_title(title)`` whitespace-collapses and lower-cases for fuzzy
  comparisons used by the title+assignee dedup fallback.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_TRAILING_KIND_CODE = re.compile(r"[A-Z]\d?$")


def normalise_publication_number(pub_number: str) -> str:
    if not pub_number:
        return ""
    raw = _NON_ALNUM.sub("", pub_number.upper())
    if not raw:
        return ""
    return _TRAILING_KIND_CODE.sub("", raw)


def normalise_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url)
    except Exception:
        return url.strip().rstrip("/").lower()
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()
    path = (p.path or "").rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))


_WS = re.compile(r"\s+")


def normalise_title(title: str) -> str:
    if not title:
        return ""
    return _WS.sub(" ", title.strip().lower())
