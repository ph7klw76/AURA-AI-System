import json
import re
from typing import Any

import ollama

import config


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_fenced_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def ask_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    json_mode: bool = False,
    think: bool = False,
) -> str:
    if temperature is None:
        temperature = config.TEMPERATURE

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    options: dict[str, Any] = {
        "temperature": temperature,
        "num_ctx": config.NUM_CTX,
    }
    if not think:
        options["think"] = False

    kwargs: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "messages": messages,
        "options": options,
        "keep_alive": config.KEEP_ALIVE,
    }
    if json_mode:
        kwargs["format"] = "json"

    response = ollama.chat(**kwargs)
    # SDK may return object or dict depending on version
    try:
        content = response.message.content
    except AttributeError:
        content = response["message"]["content"]
    return _strip_think_tags(content)


def ask_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    think: bool = False,
) -> dict:
    raw = ask_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        json_mode=True,
        think=think,
    )
    return extract_json(raw)


def extract_json(text: str) -> dict:
    cleaned = _strip_think_tags(text)
    candidate = _extract_fenced_json(cleaned)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON from LLM output.\nRaw text:\n{text}\nError: {exc}") from exc
