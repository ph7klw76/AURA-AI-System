# AURA Memory Service — Optional LangGraph Memory Adapter

Stage 1: retrieval only.  Writes are not implemented yet.

## Quick start

```bash
# Enable (disabled by default)
export AURA_MEMORY_SERVICE_ENABLED=1
export AURA_MEMORY_SERVICE_URL=http://localhost:2024
```

```python
from core.memory_service import retrieve_relevant_memories, is_memory_service_enabled

if is_memory_service_enabled():
    result = retrieve_relevant_memories("CRISPR biomarker research", session_id="s42")
    print(result.compact_context)
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AURA_MEMORY_SERVICE_ENABLED` | `0` | Enable the adapter |
| `AURA_MEMORY_SERVICE_URL` | `http://localhost:2024` | LangGraph Memory Service base URL |
| `AURA_MEMORY_WRITE_MODE` | `propose_only` | `disabled` / `propose_only` / `approved_only` |
| `AURA_MEMORY_REQUIRE_REVIEW_FOR_PROCEDURAL` | `1` | Procedural memories always need human review |
| `AURA_MEMORY_REQUIRE_VERIFIER_FOR_EVIDENCE` | `1` | Evidence memories must go through verifier |
| `AURA_MEMORY_MAX_RETRIEVED` | `8` | Max results per retrieval |
| `AURA_MEMORY_NAMESPACE_PREFIX` | `aura` | Namespace prefix for all records |
| `AURA_MEMORY_AUDIT_LOG` | `data/memory_service.jsonl` | Audit log path |
| `AURA_MEMORY_PENDING_FILE` | `data/memory_candidates.jsonl` | Pending review file |
| `AURA_MEMORY_TIMEOUT_SECONDS` | `30` | HTTP timeout |
| `AURA_MEMORY_FAIL_CLOSED` | `0` | Fail closed (crash on service error) |

## Safety invariants

- **Disabled by default** — no change to existing AURA behaviour
- **Advisory only** — memory helps AURA remember, Scientific Verifier decides trust
- **Fail-safe** — memory service unreachability is a warning, not a crash
- **Secrets blocked** — API keys, tokens, passwords never stored
- **No authority** — memory cannot bypass verifier, governor, planner, or human-review gates
- **Existing memory preserved** — `core/memory.py`, `profiles/`, `data/memories.jsonl` unchanged

## Architecture

```
AURA Session Start
  → retrieve_relevant_memories()     [Stage 1]
  → compact_context passed to agents [Stage 2+]

AURA Session End
  → extract_memory_candidates()      [Stage 2]
  → review_memory_candidates()       [Stage 2]
  → propose-only write or commit     [Stage 2-3]
```

## Namespaces

| Scope | Namespace |
|---|---|
| User preferences | `["aura", "user", user_id, "preferences"]` |
| Research profile | `["aura", "user", user_id, "research_profile"]` |
| Project decisions | `["aura", "project", project_id, "decisions"]` |
| Agent memory | `["aura", "agent", agent_name, project_id]` |
| Procedural rules | `["aura", "procedural_rules"]` |
| MCP tool memory | `["aura", "mcp", "tools"]` |
| Task-agent memory | `["aura", "task_agents"]` |
| Planner memory | `["aura", "planner"]` |
| Repository memory | `["aura", "repository", project_id]` |

## Memory types

- `user_preference` — explicit user preferences (auto-proposable)
- `research_profile` — research interests and topics
- `project_decision` — architecture and design decisions
- `evidence_memory` — requires Scientific Verifier
- `procedural_memory` — always requires human review
- `mcp_tool_memory` — external tool usefulness (not truth)
- `task_agent_memory` — helper-agent patterns (never permissions)
- `planner_memory` — routing lessons (advisory only)
- `repository_memory` — codebase constraints
- `unknown` — uncategorized

## Relationship to existing AURA memory

- `core/memory.py` — local memories.jsonl, reflections.jsonl (unchanged)
- `core/evolution_review.py` — self-evolution approval (unchanged)
- `agents/self_evolution_engine.py` — proposal engine (unchanged)
- `profiles/research_profile.yaml` — research profile (unchanged)

LangGraph Memory Service is an additive cross-session backend, not a replacement.
