# AURA MCP — inbound Model Context Protocol adapter (Phase 1)

A **thin, read-only / governed** adapter that exposes AURA to external AI
agents over the Model Context Protocol.

## Purpose

`aura_mcp` lets an MCP-capable client (e.g. Claude Desktop, an IDE agent, or
another orchestrator) call AURA's research and verification capabilities
**without bypassing any of AURA's safety machinery**. Every generative or
research workflow is delegated to AURA's orchestrator
(`core/orchestrator.py::run_aura_core()`), so the **Strategic Governor**,
**permission gates**, **Scientific Verifier**, and **draft-persistence rules**
remain fully in force.

> **All research and drafting runs through AURA's Governor and Verifier.**
> The MCP layer never calls specialist agents directly, never approves
> self-evolution, never mutates memory/profile, and never performs an external
> action (email, publishing, grant submission, patent filing, trades, etc.).

## ⚠️ STDIO transport only

Phase 1 supports **STDIO transport only**. There is **no HTTP/network server**.
The process speaks MCP over stdin/stdout and is intended to be launched as a
subprocess by a trusted local MCP client. Do not expose it over a network.

## Running

```bash
python -m aura_mcp.server
```

This requires the MCP Python SDK:

```bash
pip install "mcp>=1.0"
```

(The tool implementations themselves import cleanly and are unit-tested
**without** the SDK; the SDK is only needed to actually serve STDIO.)

AURA itself still starts normally and independently:

```bash
python main.py
```

## Example MCP client config

Claude Desktop / generic MCP client (`mcpServers` entry):

```json
{
  "mcpServers": {
    "aura": {
      "command": "python",
      "args": ["-m", "aura_mcp.server"],
      "cwd": "/absolute/path/to/aura",
      "env": {
        "AURA_MODEL": "qwen3:8b"
      }
    }
  }
}
```

## Exposed tools (the only ones)

| Tool | Read/Write | Description |
|------|-----------|-------------|
| `aura_health` | read-only | Reports Python version, AURA model env vars, and module availability. Does **not** call an LLM unless `check_llm: true`. |
| `aura_research` | governed | Runs a task through `run_aura_core()`. Returns session id, pipeline status, selected agents, scout/specialist summaries, **verifier route (never suppressed)**, and draft paths. |
| `aura_deep_research` | governed | Runs AURA's multi-round deep-research pipeline. Returns `mission_id`, `report_path`, `evidence_path`, `reflection_path`, and `mock_mode`. **Not** a systematic review or final truth. |
| `aura_verify_claims` | governed | Verifies claims against evidence via AURA's Scientific Verifier, wrapped through `run_aura_core()`. Returns verifier route, claim-level issues, missing evidence, and a recommended next action. |
| `aura_list_reports` | read-only | Lists safe, report-like files under `reports/`. Never traverses outside the repo; excludes hidden/backup/cache/secret files. |
| `aura_get_report` | read-only | Returns the content of one approved Markdown/JSON/JSONL/TXT report under `reports/`. Path-safe via `core/path_safety.py` (blocks `..`, absolute escape, and external symlinks). |

### Response envelope

Every tool returns a JSON-serializable dict:

```json
{
  "ok": true,
  "tool": "aura_research",
  "session_id": "…optional…",
  "data": { },
  "warnings": [],
  "errors": []
}
```

On any failure the tool returns `ok: false` with a populated `errors` array
rather than raising.

## Safety boundary (Phase 1)

Explicitly **not** provided:

- ❌ No HTTP / network transport (STDIO only).
- ❌ No memory or profile mutation tools.
- ❌ No self-evolution approval/apply tools.
- ❌ No external-action tools (email, publish, submit grant, file patent, trade…).
- ❌ No local-document-folder access through MCP.
- ❌ No arbitrary filesystem access or shell execution.
- ❌ No write tools — the only writes are AURA's own internal persistence
  triggered by a governed `run_aura_core()` run.

The exposed-tool allowlist lives in [`policy.py`](./policy.py) and is asserted
against the server's tool registry at import time.
