# Advisory LLM Agent Planner

An optional, advisory layer that proposes agent execution plans for tasks
outside hard-coded routing rules.

## Core rule

```
LLM proposes → policy validates → orchestrator executes → Scientific Verifier judges
```

The planner is **advisory only** — it never executes agents, calls tools, or
makes final decisions.

## Quick start

```python
from core.planning import propose_agent_plan, validate_agent_plan, PlanningContext, safe_fallback_plan

ctx = PlanningContext(user_prompt="Search literature on CRISPR and draft a grant proposal.")
raw = propose_agent_plan(ctx)          # LLM proposes
validated = validate_agent_plan(raw, ctx)  # policy validates

if not validated.ok:
    validated = safe_fallback_plan(ctx.user_prompt)  # fallback
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `AURA_LLM_PLANNER_ENABLED` | `0` | Enable the LLM planner |
| `AURA_LLM_PLANNER_MODE` | `advisory` | Always advisory (only mode) |
| `AURA_LLM_PLANNER_REQUIRE_POLICY` | `1` | Policy validation required |
| `AURA_LLM_PLANNER_REQUIRE_VERIFIER` | `1` | Verifier required |
| `AURA_LLM_PLANNER_ALLOW_UNKNOWN_AGENTS` | `0` | Unknown agents blocked |
| `AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP` | `0` | External MCP suggestions blocked |
| `AURA_LLM_PLANNER_ALLOW_TASK_AGENTS` | `0` | Task-agent suggestions blocked |
| `AURA_LLM_PLANNER_TIMEOUT_SECONDS` | `60` | LLM call timeout |

## Safety invariants

- **Disabled by default** — no behaviour change when off
- **Advisory only** — LLM proposes, never executes
- **Unknown agents blocked** — only pre-approved agent names allowed
- **Verifier cannot be disabled** — forced on for scientific/evidence tasks
- **External MCP blocked by default** — requires explicit flag
- **Task agents blocked by default** — requires explicit flag
- **High-risk → human review** — forced for patent/legal/medical tasks
- **Always blocked**: submit_grant, file_patent, send_email, github_write,
  memory_write, profile_write, self_evolution_approve, shell_exec

## What the planner may recommend

- Existing AURA agents (research_scout, grant_architect, etc.)
- Task-scoped helper agents (if enabled)
- External MCP evidence providers (if enabled)
- Evidence requirement level
- Risk level
- Whether verifier and human review are needed
- Blocked actions

## What the planner may NOT do

- Execute agents directly
- Invent unknown agents
- Disable the Scientific Verifier
- Approve its own plan
- Persist drafts
- Write memory/profile
- Approve self-evolution
- Call arbitrary MCP servers
- Run shell commands
- Push/merge/delete on GitHub

## Fallback routing

When the LLM fails or is disabled, `safe_fallback_plan()` provides
deterministic, conservative routing based on keyword matching.

## Audit

All planner events are logged to `data/llm_agent_plans.jsonl`.
No secrets, API keys, or private documents are logged.
