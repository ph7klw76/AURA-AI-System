"""One-shot LLM diagnostics — run with: python _diagnose_llm.py"""
import json, sys, traceback

# Test 1: basic JSON
print("=== Test 1: Basic JSON call ===")
try:
    from core.llm import ask_json
    result = ask_json(
        "Return JSON only.",
        'Return {"status": "ok", "value": 42}',
        temperature=0.0,
    )
    print("PASS:", result)
except Exception as e:
    print("FAIL:", e)
    traceback.print_exc()

# Test 2: governor-style JSON
print()
print("=== Test 2: Governor-style JSON ===")
try:
    from core.llm import ask_json
    result = ask_json(
        "You are a task classifier. Return strict JSON with exactly these keys: task_type (string), requires_approval (boolean), risk_level (string).",
        "User input: find recent TADF papers on arXiv",
        temperature=0.1,
    )
    print("PASS:", result)
except Exception as e:
    print("FAIL:", e)
    traceback.print_exc()

# Test 3: raw LLM output inspection
print()
print("=== Test 3: Raw LLM output ===")
try:
    from core.llm import ask_llm
    raw = ask_llm(
        "Return only valid JSON. No prose.",
        'Return {"hello": "world"}',
        temperature=0.0,
        json_mode=True,
    )
    print("Raw output (first 300 chars):", repr(raw[:300]))
except Exception as e:
    print("FAIL:", e)
    traceback.print_exc()
