# AURA Outbound MCP Gateway (Phase 2)

A safe, **optional** gateway that lets AURA call selected, allowlisted
external MCP servers as **evidence / context providers**.

## External tools are NOT authorities

External MCP outputs are treated as **unverified external evidence**. They are:

1. **policy-gated** (allowlisted servers + tools only),
2. **normalized** into `ExternalMcpEvidenceRecord`,
3. **confidence-capped** (never above `medium` before AURA verification),
4. **audited** (every call logged with hashed args/results), and
5. marked `verified_by_aura = false`.

**AURA remains the decision authority.** External evidence MUST be reviewed by
AURA's **Scientific Verifier** before it can influence any final draft — that
integration lands in **Phase 3**. Phase 2 never inserts external evidence into
final AURA drafts automatically.

## Disabled by default

Outbound MCP is **off** unless explicitly enabled. AURA runs normally with no
MCP dependencies installed — the SDK import is isolated inside the client and
degrades to a structured `mcp_unavailable` failure.

```bash
# Safe defaults (all off):
AURA_MCP_OUTBOUND_ENABLED=0
AURA_MCP_ALLOW_NETWORK_SERVERS=0
AURA_MCP_ALLOW_MOCK=0
AURA_MCP_TIMEOUT_SECONDS=60
AURA_MCP_RESEARCH_TIMEOUT_SECONDS=1800
AURA_MCP_AUDIT_LOG=data/mcp_calls.jsonl
```

## Allowlisted servers (conceptual — presence not assumed)

| Server | Allowed tools | Default |
|--------|---------------|---------|
| `local_deep_research` (LearningCircuit/local-deep-research) | `quick_research`, `detailed_research`, `generate_report`, `analyze_documents`, `search`, `list_search_engines`, `list_strategies`, `get_configuration` | OFF |
| `idea_reality` (mnemox-ai/idea-reality-mcp) | `idea_check` | OFF |
| `github` (github/github-mcp-server) | **READ-ONLY** repo/issue/PR/actions tools: `get_file_contents`, `search_code`, `list_issues`, `get_issue`, `list_pull_requests`, `get_pull_request`, `list_workflow_runs`, … (no write/admin/merge/delete/release tools) | OFF |

The gateway degrades gracefully when a server is not installed.

Each server is enabled by its own flag (`AURA_MCP_USE_LOCAL_DEEP_RESEARCH`,
`AURA_MCP_USE_IDEA_REALITY`, `AURA_MCP_USE_GITHUB`) and uses an
env-configurable launch command (`AURA_LDR_MCP_COMMAND`/`_ARGS`,
`AURA_IDEA_REALITY_MCP_COMMAND`/`_ARGS`, `AURA_GITHUB_MCP_COMMAND`/`_ARGS`).
GitHub auth comes from `GITHUB_PERSONAL_ACCESS_TOKEN`/`GITHUB_TOKEN` in the
environment only and is **never logged**.

## Public adapter helpers

```python
from core.mcp import (
    external_research_search,    # local_deep_research.search       -> raw_search
    external_research_report,    # local_deep_research.generate_report -> external_report
    external_deep_research,      # quick/detailed_research          -> research_summary
    external_idea_check,         # idea_reality.idea_check          -> market/competitor_signal
    external_github_repo_context,# github read tools                -> repository_context
)

out = external_research_search("red-NIR TADF emitters", session_id="s1")
# out = {"ok": bool, "evidence": {...}, "warnings": [...], "errors": [...]}
```

Each helper: checks policy → calls the tool → normalizes evidence → audits the
call → returns the normalized record plus warnings.

## Confidence rules

- All external MCP evidence starts **unverified**.
- Confidence cannot exceed **medium** before AURA verification (never `high`).
- Market/competition signals (`idea_reality`) are **not scientific evidence**.
- Mock/synthetic outputs force **low** confidence (and mock is opt-in only).

## Safety boundary

The gateway has **no** code paths for: arbitrary shell, arbitrary filesystem
access, external write/mutation actions, profile/memory writes, or
self-evolution approval. Subprocess launch commands are checked against a
command whitelist and rejected if they contain shell metacharacters. Network
MCP servers are blocked unless explicitly allowed.

## Dependency note

The MCP SDK (`pip install "mcp>=1.0"`) is required only to actually contact a
server. It is **not** a hard AURA dependency — the gateway and all of its unit
tests run without it installed.
