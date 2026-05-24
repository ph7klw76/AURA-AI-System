# AURA — Autonomous Unified Research Agent

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Pydantic](https://img.shields.io/badge/pydantic-v2-orange)
![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20Python%20API-informational)
![LLM Backend](https://img.shields.io/badge/LLM-Ollama%20or%20OpenAI--compatible%20remote-purple)
![Search](https://img.shields.io/badge/search-SearXNG%20%2F%20no--key%20web%20%2F%20mock-green)
![Tests](https://img.shields.io/badge/tests-343%20passing-brightgreen)
![MCP](https://img.shields.io/badge/MCP-enabled-blueviolet)
![Memory](https://img.shields.io/badge/LangGraph%20Memory-optional-teal)

**AURA** is a multi-agent research control plane for structured scientific ideation, literature reconnaissance, grant-draft preparation, patent-landscape reconnaissance, local-document evidence retrieval, claim-level verification, supervised self-evolution, and long-term cross-session memory.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [User Manual](#user-manual)
   - [Installation](#installation)
   - [Configuration](#configuration)
   - [CLI Usage](#cli-usage)
   - [Python API Usage](#python-api-usage)
3. [Architecture](#architecture)
   - [Control Plane](#control-plane)
   - [Agent System](#agent-system)
   - [Verification & Safety](#verification--safety)
   - [Memory & Evolution](#memory--evolution)
4. [Subsystems](#subsystems)
   - [LLM Agent Planner](#llm-agent-planner)
   - [Task Agents](#task-agents)
   - [MCP Integration](#mcp-integration)
   - [LangGraph Memory Service](#langgraph-memory-service)
   - [AURA MCP Server](#aura-mcp-server)
   - [Local Documents](#local-documents)
   - [Patent Intelligence](#patent-intelligence)
   - [Deep Research](#deep-research)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Safety Invariants](#safety-invariants)
7. [Testing](#testing)
8. [Limitations](#limitations)
9. [Repository Scope](#repository-scope)

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/ph7klw76/AURA-AI-System.git
cd AURA-AI-System
pip install -r requirements.txt

# 2. Set your LLM API key
export AURA_LLM_API_KEY="sk-your-key-here"
export AURA_LLM_MODEL="deepseek-v4-flash"

# 3. Launch interactive mode
python main.py

# 4. Or use the Python API directly
python -c "
from core.orchestrator import run_aura_core
result = run_aura_core('Recent advances in CRISPR delivery vectors?')
print(result['research_scout']['summary'])
"
```

---

## User Manual

### Installation

**Prerequisites:** Python 3.11+, LLM API key (OpenAI-compatible or local Ollama), optional SearXNG for search

```bash
git clone https://github.com/ph7klw76/AURA-AI-System.git
cd AURA-AI-System
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Verify:** `python -m pytest tests/ -q` — should report 343 passed.

### Configuration

All configuration is via environment variables. Create a `.env` file:

```bash
# Required
AURA_LLM_API_KEY=sk-your-api-key-here
AURA_LLM_MODEL=deepseek-v4-flash

# Ollama (local models): set AURA_LLM_MODEL=llama3:8b (colon triggers Ollama)
# OLLAMA_HOST=http://localhost:11434

# SearXNG search
SEARXNG_ENABLED=1
SEARXNG_URL=http://localhost:8080

# LangGraph Memory Service (enabled by default)
AURA_MEMORY_SERVICE_URL=http://localhost:2024
AURA_MEMORY_WRITE_MODE=propose_only     # disabled | propose_only | approved_only
```

### CLI Usage

```bash
python main.py                           # Interactive mode
python main.py research "query"          # Direct deep research
python main.py research-grants "query"   # Grant-focused research
python main.py show-report <id>          # View saved report
python main.py show-evidence <id>        # View evidence backing report
python main.py show-reflection <id>      # View self-critique

# Diagnostics
python _diagnose_llm.py                  # Test LLM connectivity
python _diagnose_governor.py             # Test routing
python _demo_pipelines.py                # Demo grant+teaching pipelines
python _e2e_test.py                      # End-to-end harness
```

### Python API Usage

```python
from core.orchestrator import run_aura_core

# Basic query
result = run_aura_core("Key challenges in mRNA vaccine stability?")
print(result["research_scout"]["summary"])
print(result["scientific_verifier"]["verifier_route"])

# With session ID
result = run_aura_core("CRISPR off-target detection",
                       session_id="my-project-001")

# Pause/resume for local documents
first = run_aura_core("Use my local PDFs to find grant rationale")
if first.get("pipeline_status") == "awaiting_user_input":
    resumed = run_aura_core(
        first["user_input"],
        session_id=first["session_id"],
        user_responses={
            first["pending_prompt"]["target_agent"]: {
                "use_local_folder": True,
                "folder_path": "/path/to/papers",
            },
        },
    )

# Memory service results
ms = result.get("memory_service", {})
print(f"Candidates: {ms.get('candidate_count', 0)}")
print(f"Committed:  {ms.get('committed_count', 0)}")
print(f"Pending:    {ms.get('pending_review_count', 0)}")
```

**Result dict keys:** `user_input`, `session_id`, `strategic_governor`, `research_scout`, `specialists`, `verifications`, `scientific_verifier`, `self_evolution_engine`, `memory_service`, `pipeline_status`, `errors`

---

## Architecture

### Control Plane Flow

```
User Request → Strategic Governor → LLM Planner (advisory)
  → Orchestrator → Research Scout + Specialists + Task Agents
  → MCP Bridge (external tools) → Scientific Verifier
  → Draft Writer → Self-Evolution → Memory Service
```

### Agent System

| Agent | Purpose |
|---|---|
| **Strategic Governor** | Task classification, risk, agent selection, policy |
| **Research Scout** | Ideation, literature scans, gap analysis, grant-opp, deep-research |
| **Grant Architect** | Grant proposal drafting |
| **China Grant Architect** | China-specific grant drafting |
| **Patent Intelligence** | Patent-landscape reconnaissance |
| **Lab Data Analyst** | Experimental design, data-analysis planning |
| **Teaching Mentor** | Educational material, curriculum design |
| **Influence & Public Comms** | Public-facing science communication |
| **Collaboration Operator** | Research collaboration strategy |
| **Founder Innovation** | Commercialization, startup ideation |
| **Scientific Verifier** | Claim audit, evidence quality, route decision |
| **Self-Evolution Engine** | Lesson extraction, proposal generation (human-gated) |

### Verification & Safety

The Scientific Verifier audits every specialist output. Routes:

| Route | Action |
|---|---|
| `approve` / `accept` | Save to `reports/` |
| `conditional_accept` | Save with caveats |
| `revise` | Retry specialist (bounded) |
| `retrieve_more_evidence` | Trigger MCP/search |
| `human_review` | Save to `reports/pending_review/` |
| `reject` | Block persistence |

### Memory Layers

| Layer | Auto-apply? |
|---|---|
| **Session Memory** (`core/memory.py`) | No — human-gated |
| **Self-Evolution** (`agents/self_evolution_engine.py`) | No — human-gated |
| **LangGraph Memory** (`core/memory_service/`) | Policy-gated |

---

## Subsystems

### LLM Agent Planner

**Location:** `core/planning/` | **Default:** enabled

LLM-based routing optimization. Strictly advisory — governor + policy make final decisions. Human-approval gate at planner, orchestrator, and task-agent dispatch.

**Env vars:** `AURA_LLM_PLANNER_ENABLED`, `AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP`, `AURA_LLM_PLANNER_ALLOW_TASK_AGENTS`

### Task Agents

**Location:** `core/task_agents/` | **Default:** enabled

Bounded single-purpose helpers. Sandboxed (no memory/profiles/self-evolution access), human-gated, audited, stateless.

**Env vars:** `AURA_TASK_AGENTS_ENABLED`, `AURA_TASK_AGENTS_REQUIRE_APPROVAL`

### MCP Integration

**Location:** `core/mcp/`

External tool bridge via Model Context Protocol. Supported servers:

| Server | Repository |
|---|---|
| local-deep-research | `ph7klw76/local-deep-research2` |
| ToolUniverse | `ph7klw76/ToolUniverse2` |
| jupyter-mcp-server | `ph7klw76/jupyter-mcp-server2` |
| paper-qa | `ph7klw76/paper-qa2` |
| open-coscientist | `ph7klw76/open-coscientist-v2` |
| idea-reality-mcp | `ph7klw76/idea-reality-mcp2` |

MCP output is **unverified external evidence** — never treated as truth.

### LangGraph Memory Service

**Location:** `core/memory_service/` | **Default:** enabled | **Tests:** 120

Cross-session long-term memory. **Core rule:** subordinate to all other systems.

**Pipeline:** Retrieve → Attach context → [AURA runs] → Extract candidates → Classify (14 secret patterns) → Validate (11 type rules) → Commit or pend → Audit log

**Memory type policy:**

| Type | Auto-commit | Verifier | Human review |
|---|---|---|---|
| `user_preference` | Yes (approved_only) | No | No |
| `evidence_memory` | If verifier-approved | **Yes** | No |
| `procedural_memory` | **Never** | No | **Always** |
| `planner_memory` | **Never** | No | **Always** |
| `task_agent_memory` | No | Conditional | **Yes** |
| `mcp_tool_memory` | No | **Yes** | propose_only |
| `project_decision` | No | No | **Yes** |
| `repository_memory` | No | No | **Yes** |

**Key env vars:** `AURA_MEMORY_SERVICE_ENABLED`, `AURA_MEMORY_SERVICE_URL`, `AURA_MEMORY_WRITE_MODE`, `AURA_MEMORY_REQUIRE_REVIEW_FOR_PROCEDURAL`, `AURA_MEMORY_REQUIRE_VERIFIER_FOR_EVIDENCE`, `AURA_MEMORY_MAX_RETRIEVED`, `AURA_MEMORY_TIMEOUT_SECONDS`, `AURA_MEMORY_FAIL_CLOSED`

### AURA MCP Server

**Location:** `aura_mcp/` — exposes AURA reports to external MCP clients.

### Local Documents

**Location:** `core/local_documents/` — PDF/DOCX/TXT/MD ingestion, chunking, in-memory retrieval. User must explicitly approve folder access.

### Patent Intelligence

**Location:** `agents/patent_intelligence.py`, `integrations/patent_web/` — Stage-1 web-based patent discovery. Not API-verified, not legal advice.

### Deep Research

**Location:** `qwen_evolver/deep_research/` — 16-section Markdown reports, SearXNG/mock, mission IDs, source tracking.

---

## Environment Variables Reference

### LLM
| Variable | Default |
|---|---|
| `AURA_LLM_API_KEY` | — |
| `AURA_LLM_MODEL` | `deepseek-v4-flash` |
| `AURA_TEMPERATURE` | `0.2` |
| `AURA_NUM_CTX` | `8192` |

### Search
| Variable | Default |
|---|---|
| `SEARXNG_ENABLED` | `0` |
| `SEARXNG_URL` | `http://localhost:8080` |
| `SEMANTIC_SCHOLAR_API_KEY` | — |
| `OPENALEX_API_KEY` | — |

### Planner (all default: `1`)
`AURA_LLM_PLANNER_ENABLED`, `AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP`, `AURA_LLM_PLANNER_ALLOW_TASK_AGENTS`

### Task Agents (all default: `1`)
`AURA_TASK_AGENTS_ENABLED`, `AURA_TASK_AGENTS_REQUIRE_APPROVAL`

### Memory Service
| Variable | Default |
|---|---|
| `AURA_MEMORY_SERVICE_ENABLED` | `1` |
| `AURA_MEMORY_SERVICE_URL` | `http://localhost:2024` |
| `AURA_MEMORY_WRITE_MODE` | `propose_only` |
| `AURA_MEMORY_REQUIRE_REVIEW_FOR_PROCEDURAL` | `1` |
| `AURA_MEMORY_REQUIRE_VERIFIER_FOR_EVIDENCE` | `1` |
| `AURA_MEMORY_MAX_RETRIEVED` | `8` |
| `AURA_MEMORY_TIMEOUT_SECONDS` | `30` |
| `AURA_MEMORY_FAIL_CLOSED` | `0` |

### Persistence
| Variable | Default |
|---|---|
| `AURA_DATA_DIR` | `data/` |
| `AURA_REPORT_DIR` | `reports/` |
| `AURA_MEMORY_PATH` | `data/memories.jsonl` |

---

## Safety Invariants

1. **Secrets never stored** — 14 regex patterns block keys, tokens, passwords
2. **Procedural memory = human review** — always, unconditionally
3. **Evidence memory = verifier required** — no bypass
4. **Planner is advisory** — cannot override governor/policy/verifier
5. **Task agents are sandboxed** — no memory, profiles, self-evolution, permissions
6. **MCP output is not truth** — low-confidence, requires verification
7. **Memory is subordinate to verifier** — Scientific Verifier decides truth
8. **Human approval gates** — planner, orchestrator, task-agent dispatch
9. **Fail-safe degradation** — memory errors never crash AURA
10. **Write-mode gating** — disabled | propose_only | approved_only

---

## Testing

```bash
python -m pytest tests/ -q                    # 343 tests total
python -m pytest tests/test_memory_service_*.py -q  # 120 memory-service
python -m pytest tests/test_planning_*.py -q        # Planning
python -m pytest tests/test_task_agents_*.py -q     # Task agents
python _e2e_test.py                                # E2E (needs LLM)
```

---

## Limitations

1. Not autonomous execution — consequential actions require human approval
2. Not a systematic-review engine — literature scanning is reconnaissance
3. Not legal/financial/medical/patent advice
4. Not fully deterministic — LLM + web search introduce variability
5. Mock mode is synthetic — for testing/demos only
6. Soft timeouts are non-preemptive
7. Local-document index is in-memory, session-scoped
8. Memory service requires separate LangGraph deployment
9. No built-in CI configuration

---

## Repository Scope

AURA is a standalone Python CLI + library orchestration layer. No web server, no external DB beyond SQLite/JSONL.

**Capabilities:** Interactive CLI, deep research CLI, multi-agent control plane, LLM abstraction (Ollama + OpenAI-compatible), literature search, 16-section deep research reports, local document ingestion, patent reconnaissance, draft persistence, self-evolution proposals, LLM Agent Planner, task agents, MCP integration, LangGraph Memory Service, AURA MCP server.

---

## Acknowledgments

Built on: Pydantic, Rich, Requests, PyYAML, Beautiful Soup, PDF/DOCX extraction, Ollama, SearXNG.

External MCP tools: [local-deep-research](https://github.com/ph7klw76/local-deep-research2), [ToolUniverse](https://github.com/ph7klw76/ToolUniverse2), [jupyter-mcp-server](https://github.com/ph7klw76/jupyter-mcp-server2), [paper-qa](https://github.com/ph7klw76/paper-qa2), [open-coscientist](https://github.com/ph7klw76/open-coscientist-v2), [idea-reality-mcp](https://github.com/ph7klw76/idea-reality-mcp2), [Pitchlense-mcp](https://github.com/connectaman/Pitchlense-mcp), [M-Cube](https://github.com/yycyyv/M-Cube).

---

## Maintainer Note

When adding features: confirm code is implemented, covered by tests, mock/live modes are distinguished, outputs are labelled by evidence quality, externally consequential actions remain human-gated, generated artifacts are separated from source files.
