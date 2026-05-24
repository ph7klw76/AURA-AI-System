"""Diagnose governor failure — run with: python _diagnose_governor.py"""
import traceback, json

# Test 1: Direct governor call with verbose error
print("=== Test 1: Direct governor run() ===")
try:
    from agents.strategic_governor import run
    result = run("Find recent TADF papers on arXiv")
    print("task_type:", result.get("task_type"))
    print("selected_agents:", result.get("selected_agents"))
    print("requires_approval:", result.get("requires_approval"))
    print("research_scout_mode:", result.get("research_scout_mode"))
except Exception as e:
    print("EXCEPTION:", e)
    traceback.print_exc()

# Test 2: The raw ask_json call that the governor makes
print()
print("=== Test 2: ask_json with governor prompt (abbreviated) ===")
try:
    from core.llm import ask_json
    short_system = (
        "You are a task classifier. Return strict JSON with ONLY these fields:\n"
        '{"task_type": "research_scan", "requires_approval": false, '
        '"risk_level": "low", "selected_agents": ["research_scout"], '
        '"research_scout_mode": "literature_scan", "rationale": "..."}'
    )
    result = ask_json(short_system, "Find recent TADF papers", temperature=0.1)
    print("PASS:", json.dumps(result, indent=2)[:500])
except Exception as e:
    print("FAIL:", e)
    traceback.print_exc()

# Test 3: Full governor SYSTEM_PROMPT with LLM
print()
print("=== Test 3: Governor with full SYSTEM_PROMPT ===")
try:
    from agents.strategic_governor import SYSTEM_PROMPT
    from core.llm import ask_json
    user_prompt = "User request:\nFind recent TADF papers on arXiv\n\nReturn your executive decision as strict JSON."
    result = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.1)
    print("PASS - keys:", list(result.keys()))
    print("task_type:", result.get("task_type"))
    print("selected_agents:", result.get("selected_agents"))
    print("workflow_sequence count:", len(result.get("workflow_sequence", [])))
except Exception as e:
    print("FAIL:", e)
    traceback.print_exc()

# Test 4: Check if GovernorDecision(**raw) fails
print()
print("=== Test 4: GovernorDecision parse ===")
try:
    from agents.strategic_governor import SYSTEM_PROMPT
    from core.llm import ask_json
    from core.schemas import GovernorDecision, MemoryPolicy, SelfEvolutionPolicy, WorkflowStep
    user_prompt = "User request:\nFind recent TADF papers\n\nReturn your executive decision as strict JSON."
    raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.1)
    print("Raw keys:", list(raw.keys()))

    # Coerce nested types
    if isinstance(raw.get("memory_policy"), dict):
        raw["memory_policy"] = MemoryPolicy(**raw["memory_policy"])
    if isinstance(raw.get("self_evolution_policy"), dict):
        raw["self_evolution_policy"] = SelfEvolutionPolicy(**raw["self_evolution_policy"])
    if isinstance(raw.get("workflow_sequence"), list):
        raw["workflow_sequence"] = [
            WorkflowStep(**s) if isinstance(s, dict) else s
            for s in raw["workflow_sequence"]
        ]

    decision = GovernorDecision(**raw)
    print("PASS - GovernorDecision parsed successfully")
    print("task_type:", decision.task_type)
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:500])
    traceback.print_exc()
