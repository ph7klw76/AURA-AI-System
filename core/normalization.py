"""
Defensive normalization helpers for LLM- and agent-produced payloads.

Phase 3 of AURA hardening targets a single class of bug: code that
*trusts* the declared shape of an LLM JSON field.  Concretely:

* ``list(value)`` on a string yields a character array
  (``list("ABC") == ["A","B","C"]``) — corrupting findings, claims, and
  safety risks.
* Iterating ``for item in value`` when ``value`` is a string degrades to
  per-character iteration with the same effect.
* ``for d in value: d.get(...)`` crashes with ``AttributeError`` when an
  element is a string instead of a dict.

These helpers replace ``list(...)`` and ad-hoc iteration on untrusted
fields with deliberate, schema-aware normalization.

Scalar-string policy
--------------------
A scalar string supplied where a list of strings is expected is
**preserved as a single-element list**, NEVER split into characters.
This matches what an LLM almost certainly meant ("one item that happens
not to be wrapped in an array") and never silently invents data.

A scalar value supplied where a list of *dicts* is expected is
**dropped** (with an optional structured warning), because we cannot
fabricate the missing structure without lying about provenance.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------

def ensure_str(value: Any, *, default: str = "", max_len: int | None = None) -> str:
    """Return ``value`` as a stripped string, or ``default`` if unusable.

    Numbers and bools are stringified.  Lists / dicts / None → default
    (we refuse to coerce structured data into a string silently).
    """
    if value is None:
        return default
    if isinstance(value, str):
        out = value.strip()
    elif isinstance(value, (int, float, bool)):
        out = str(value)
    else:
        return default
    if max_len is not None and len(out) > max_len:
        out = out[:max_len]
    return out


def ensure_optional_dict(value: Any) -> dict | None:
    """Return ``value`` if it is a real dict, else ``None`` (never ``{}``).

    Callers that want ``{}`` as the empty case should write
    ``ensure_optional_dict(v) or {}``.
    """
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# List helpers (the main Phase-3 surface)
# ---------------------------------------------------------------------------

def ensure_str_list(
    value: Any,
    *,
    allow_scalar_string: bool = True,
    max_items: int | None = None,
    max_item_len: int | None = None,
) -> list[str]:
    """Coerce ``value`` into a clean ``list[str]``.

    Rules:
      * ``None`` / missing → ``[]``
      * ``str`` → ``[value]`` when ``allow_scalar_string`` (NEVER chars),
        otherwise ``[]``
      * ``list`` / ``tuple`` / ``set`` → each element passed through
        :func:`ensure_str`; entries that normalize to ``""`` are dropped
      * ``dict`` → ``[]`` (a dict is not a list of strings)
      * any other scalar (int/float/bool) → ``[str(value)]`` so a
        Pydantic-typed integer doesn't silently disappear

    This function NEVER expands a string into characters.
    """
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        if allow_scalar_string:
            s = value.strip()
            if s:
                out = [s]
        return _truncate_list(out, max_items, max_item_len)
    if isinstance(value, (int, float, bool)):
        return _truncate_list([str(value)], max_items, max_item_len)
    if isinstance(value, dict):
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            s = ensure_str(item)
            if s:
                out.append(s)
        return _truncate_list(out, max_items, max_item_len)
    return out


def ensure_dict_list(
    value: Any,
    *,
    max_items: int | None = None,
    warn: Callable[[str], None] | None = None,
    field_name: str = "field",
) -> list[dict]:
    """Coerce ``value`` into a clean ``list[dict]``.

    Non-dict elements are dropped.  When the *whole* value is not a list
    (e.g. an LLM returned a string instead of an array), the result is
    ``[]`` and — if ``warn`` is provided — a one-line shape warning is
    emitted so the caller can surface it as a structured risk.

    Never raises.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        # A single dict where a list was expected — treat as 1-element list.
        return _truncate_dict_list([value], max_items)
    if isinstance(value, (list, tuple)):
        dropped = 0
        out: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
            else:
                dropped += 1
        if dropped and warn is not None:
            warn(shape_warning(field_name, "list[dict]",
                               f"dropped {dropped} non-dict entr"
                               + ("y" if dropped == 1 else "ies")))
        return _truncate_dict_list(out, max_items)
    if warn is not None:
        warn(shape_warning(field_name, "list[dict]",
                           f"got {type(value).__name__}"))
    return []


def ensure_list(value: Any, *, max_items: int | None = None) -> list:
    """Generic list coercion that DOES NOT split strings into characters.

    Use this when the element type is heterogeneous (e.g. either a string
    or a dict) and a stricter helper does not apply.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = list(value)
    elif isinstance(value, (str, int, float, bool, dict)):
        out = [value]
    elif isinstance(value, (set, frozenset)):
        out = list(value)
    else:
        out = []
    if max_items is not None and len(out) > max_items:
        out = out[:max_items]
    return out


# ---------------------------------------------------------------------------
# Iteration helper (drop-in for "for d in value")
# ---------------------------------------------------------------------------

def iter_dicts(value: Any) -> Iterable[dict]:
    """Yield only dict elements from *value*, ignoring strings/None.

    Safe substitute for ``for x in value: x.get(...)`` when *value* may
    be a string, None, or a list containing non-dict items.
    """
    if value is None:
        return
    if isinstance(value, dict):
        yield value
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                yield item


# ---------------------------------------------------------------------------
# Structured warning
# ---------------------------------------------------------------------------

def shape_warning(field: str, expected: str, got_detail: str) -> str:
    """Return a short, structured warning string about a malformed field.

    Format: ``"shape:<field>: expected <expected>; <got_detail>"``.
    """
    return f"shape:{field}: expected {expected}; {got_detail}"


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _truncate_list(
    out: list[str], max_items: int | None, max_item_len: int | None,
) -> list[str]:
    if max_item_len is not None:
        out = [s[:max_item_len] for s in out]
    if max_items is not None and len(out) > max_items:
        out = out[:max_items]
    return out


def _truncate_dict_list(out: list[dict], max_items: int | None) -> list[dict]:
    if max_items is not None and len(out) > max_items:
        out = out[:max_items]
    return out
