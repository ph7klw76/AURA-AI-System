"""
Thin wrapper around local Ollama and remote (DeepSeek‑style) LLM calls.
Respects LLM_MODEL, LLM_API_KEY, AURA_NUM_CTX, AURA_KEEP_ALIVE env vars.

Uses config.get_model_name() at call time so model selection can change
without restarting the process.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
from typing import Any

import requests

import config


# Wall-clock cap for any single LLM call.  Unlike ``requests``' per-read
# timeout (which resets on every byte received and so cannot bound a
# slow-streaming "thinking" model), this is enforced via a background
# thread + join deadline: when it fires, the orchestrator's failure-safe
# path takes over instead of the UI hanging indefinitely.
#
# Configurable via ``AURA_LLM_WALL_TIMEOUT`` (seconds).  Default 300 s.
_WALL_TIMEOUT_DEFAULT: int = 300


def _wall_timeout() -> int:
    raw = os.getenv("AURA_LLM_WALL_TIMEOUT", str(_WALL_TIMEOUT_DEFAULT))
    try:
        return max(30, int(raw))
    except (TypeError, ValueError):
        return _WALL_TIMEOUT_DEFAULT


def _post_with_wall_timeout(
    url: str, *, json_body: dict, headers: dict, read_timeout: int,
) -> requests.Response:
    """POST with an absolute wall-clock cap.

    ``requests`` resets its timeout on every chunk received, so a slow
    reasoning model emitting a token per second can run far past the
    nominal timeout.  We dispatch the request on a ``ThreadPoolExecutor``
    worker and ``future.result(timeout=deadline)``; on timeout we raise
    ``TimeoutError`` so callers fall through to the failure-safe path.

    NON-PREEMPTIVE caveat (truthful semantics): the worker thread is NOT a
    daemon, and ``future.cancel()`` cannot interrupt a request already in
    flight.  After a timeout this function returns control PROMPTLY (we call
    ``pool.shutdown(wait=False)``), but the underlying ``requests.post`` may
    keep running in the background until the socket drains, and the
    interpreter will join that worker at exit.  This bounds how long the
    CALLER waits — it does NOT forcibly kill the HTTP request.  Genuine
    killability would require subprocess isolation.
    """
    deadline = _wall_timeout()

    def _do_post() -> requests.Response:
        return requests.post(url, json=json_body, headers=headers,
                             timeout=read_timeout)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    started = time.monotonic()
    future = pool.submit(_do_post)
    try:
        return future.result(timeout=deadline)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        pool.shutdown(wait=False)
        elapsed = time.monotonic() - started
        raise TimeoutError(
            f"LLM call exceeded wall-clock budget of {deadline}s "
            f"(elapsed {elapsed:.0f}s); background request may still be running"
        ) from exc
    finally:
        # Don't wait for the background socket to drain — that defeats
        # the whole point of the wall-clock cap.
        pool.shutdown(wait=False)

# ---------------------------------------------------------------------------
# Remote provider configuration (OpenAI‑compatible)
# ---------------------------------------------------------------------------

REMOTE_BASE_URL: str = os.getenv(
    "REMOTE_API_URL",
    "https://api.deepseek.com/v1/chat/completions",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """Remove  tags from some models."""
    return re.sub(r"<.*?think>.*?</.*?think>", "", text, flags=re.DOTALL).strip()


def _extract_fenced_json(text: str) -> str:
    """Return the content between the first ```json and ``` fences, or the original text."""
    match = re.search(r"```json\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text.strip()


# ---------------------------------------------------------------------------
# Low-level call (routes to Ollama or remote API)
# ---------------------------------------------------------------------------

def ask_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    json_mode: bool = False,
    think: bool = False,
) -> str:
    """Send a prompt to the configured LLM and return the response text.

    Model selection is performed at call time via config.get_model_name().
    For models that contain a colon (e.g. "qwen3:8b") the request is sent
    to a local Ollama instance. All other models are treated as remote
    (DeepSeek‑style) and require the LLM_API_KEY environment variable.
    """
    if temperature is None:
        temperature = config.TEMPERATURE

    model = config.get_model_name()
    api_key = os.environ.get("LLM_API_KEY", "")

    # ---- Ollama pathway (local model with colon) ----------------------------
    if ":" in model:
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        # Defect 2: Ollama's /api/chat documents `keep_alive` as a TOP-LEVEL
        # field (alongside model/messages/options/stream), NOT inside
        # `options`.  `think` is also a top-level boolean and must be sent
        # explicitly when the caller opts in (Ollama silently ignores it
        # otherwise, but the request must still match the documented API).
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": config.NUM_CTX,
            },
            "keep_alive": config.KEEP_ALIVE,
            "stream": False,
        }
        # Defect 2: `think` is a top-level field, only sent when caller
        # explicitly opted in.  Models that do not support it ignore the key.
        if think:
            payload["think"] = True
        if json_mode:
            payload["format"] = "json"

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = _post_with_wall_timeout(
                f"{ollama_host}/api/chat",
                json_body=payload, headers=headers, read_timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
        except Exception as exc:
            raise RuntimeError(f"Ollama call failed: {exc}") from exc

        if not think:
            content = _strip_think_tags(content)
        return content

    # ---- Remote pathway (OpenAI‑style, e.g. DeepSeek) -----------------------
    if not api_key:
        raise RuntimeError(
            f"LLM_API_KEY must be set to use remote model {model!r}. "
            "Provide it via the AURA prompt or set the environment variable."
        )

    # Defect: Founder-Innovation and similar long-form specialists routinely
    # produce 4-6 KB of JSON.  The previous 4096-token cap caused mid-string
    # truncation that crashed JSON parsing.  Bump to 8192 by default; allow
    # overriding via ``AURA_LLM_MAX_TOKENS`` env var when the user wants to
    # economise on a small task.
    try:
        max_tokens = max(512, int(os.getenv("AURA_LLM_MAX_TOKENS", "8192")))
    except (TypeError, ValueError):
        max_tokens = 8192
    remote_payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        remote_payload["response_format"] = {"type": "json_object"}

    headers_remote = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = _post_with_wall_timeout(
            REMOTE_BASE_URL,
            json_body=remote_payload, headers=headers_remote, read_timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(f"Remote LLM call failed: {exc}") from exc

    if not think:
        content = _strip_think_tags(content)
    return content


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def ask_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    think: bool = False,
) -> dict:
    """Like ask_llm but returns a dict parsed from the LLM's JSON output."""
    raw = ask_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        json_mode=True,
        think=think,
    )
    return extract_json(raw)


def extract_json(text: str) -> dict:
    """Parse an LLM response into a JSON OBJECT (Python dict).

    Defect 1: this function used to return ``json.loads(...)`` whatever the
    type — meaning a list / string / int / bool / null could leak through
    and crash any caller that did ``result.get(...)``.  ``ask_json`` is
    typed ``-> dict`` and must honour that contract.  Non-object JSON now
    raises ``ValueError`` so the caller's exception handler engages the
    same way it does for unparseable input.
    """
    if not isinstance(text, str):
        raise ValueError("extract_json expected a string, got %r" % type(text).__name__)
    text = text.strip()
    if not text:
        raise ValueError("extract_json received empty input")

    parsed: Any
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try stripping a ``` ```json ... ``` fence and re-parsing.
        cleaned = _extract_fenced_json(text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: a "thinking" / large-output model may have been
            # truncated mid-token by max_tokens.  Try to close any open
            # string / array / object brackets and re-parse.  This NEVER
            # invents missing keys — it only seals the structural gap so
            # already-emitted content survives.
            repaired = _repair_truncated_json(cleaned or text)
            if repaired is not None:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"Could not parse JSON from LLM output: {text[:200]}"
                    )
            else:
                raise ValueError(
                    f"Could not parse JSON from LLM output: {text[:200]}"
                )

    if not isinstance(parsed, dict):
        raise ValueError(
            "extract_json refused non-object JSON "
            f"({type(parsed).__name__}): {text[:200]}"
        )
    return parsed


def _repair_truncated_json(text: str) -> str | None:
    """Best-effort repair of a truncated JSON object.

    Walks the string tracking string-mode + bracket depth, then appends the
    minimum suffix needed to close the structure.  Returns ``None`` when
    the input is not even plausibly a JSON object (no leading ``{``).

    Repairs handled:
      * truncation inside a string literal       -> closing quote
      * truncation after a trailing comma        -> strip the comma
      * truncation after a key (``"foo":``)      -> append ``null``
      * unclosed nested arrays / objects         -> append matching closers

    Does NOT attempt to fix invalid escape sequences or malformed numbers.
    """
    if not text:
        return None
    text = text.strip()
    if not text.startswith("{"):
        # Could still be a fenced object — try the existing fence helper.
        fenced = _extract_fenced_json(text)
        if not fenced.startswith("{"):
            return None
        text = fenced

    stack: list[str] = []
    in_string = False
    escape = False
    last_non_ws = ""
    for ch in text:
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                last_non_ws = ch
            continue
        if ch == '"':
            in_string = True
            last_non_ws = ch
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
        if not ch.isspace():
            last_non_ws = ch

    suffix = ""
    if in_string:
        suffix += '"'
    # If we were sitting right after a key (``"foo":``) the next valid token
    # is a value.  Emit ``null`` so the parser is satisfied.
    if last_non_ws == ":":
        suffix += "null"
    # Strip any trailing comma so closing the structure stays valid JSON.
    body = text.rstrip()
    if body.endswith(","):
        body = body[:-1].rstrip()
    suffix += "".join(reversed(stack))
    return body + suffix
