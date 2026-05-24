# Task-Scoped Agents

AURA can create **temporary, bounded helper agents** for narrow subtasks.
These agents are **not autonomous** — they operate inside the governed
orchestrator pipeline and cannot replace existing AURA agents.

## Safety invariants

| Rule | Enforcement |
|---|---|
| Disabled by default | `AURA_TASK_AGENTS_ENABLED=0` |
| Cannot replace existing agents | Overlap registry blocks broad tasks |
| Cannot spawn agents | `can_spawn_agents` always `False` |
| Cannot modify memory | `can_modify_memory` always `False` |
| Cannot modify profile | `can_modify_profile` always `False` |
| Cannot persist drafts | `persistence_allowed` always `False` |
| Cannot bypass verifier | `verifier_required` always `True` |
| Cannot use shell | Tool namespace blocked |
| Cannot write to GitHub | Tool namespace blocked |
| Output always unverified | `verified_by_aura=False` |

## Integrity chain (unchanged)

```
User → Strategic Governor → Orchestrator → existing agents or task agents
→ Scientific Verifier → route → draft persistence gate → human-reviewed evolution
```

Task agents produce **auxiliary evidence only**.  The Scientific Verifier
remains the sole authority that approves outputs for final use.

## Allowed task-agent roles

| Role | What it does |
|---|---|
| `claim_extractor` | Extract candidate claims from text (no verification) |
| `evidence_table_formatter` | Format evidence records into structured tables |
| `query_variant_generator` | Generate alternative search query variants |
| `mcp_result_normalizer` | Normalize raw MCP output into evidence records |
| `repo_issue_classifier` | Classify GitHub issues by likely AURA module |
| `competitor_name_extractor` | Extract competitor names from text |
| `reviewer_objection_mapper` | Map draft text to reviewer objection categories |
| `risk_register_builder` | Build simple risk register from project text |
| `test_case_suggester` | Suggest test cases for features/modules |
| `local_document_excerpt_summarizer` | Deterministic extractive text summary |

## Forbidden roles

- `research_scout_clone`, `verifier_clone`, `grant_architect_clone`
- `patent_agent_clone`, `founder_agent_clone`, `self_evolution_agent`
- `memory_writer_agent`, `profile_editor_agent`, `github_writer_agent`
- `autonomous_coder_agent`, `shell_executor_agent`

## Orchestrator integration

```python
from core.task_agents import maybe_create_task_agent, run_task_agent

# Only the orchestrator may call:
decision = maybe_create_task_agent(
    session_id="...", parent_agent="orchestrator",
    requested_role="claim_extractor",
    subtask="extract claims from research_scout output",
    context={"text": scout_output},
)
if decision.create_agent and decision.proposed_spec:
    result = run_task_agent(decision.proposed_spec, {"text": scout_output})
    # result.verified_by_aura is always False
    # route through Scientific Verifier before final use
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `AURA_TASK_AGENTS_ENABLED` | `0` | Enable task-agent system |
| `AURA_TASK_AGENTS_MAX_PER_SESSION` | `3` | Max agents per session |
| `AURA_TASK_AGENTS_MAX_STEPS` | `5` | Max steps per agent |
| `AURA_TASK_AGENTS_REQUIRE_VERIFIER` | `1` | Require verifier on all task-agent outputs |
