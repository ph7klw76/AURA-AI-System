# open-coscientist STDIO MCP wrapper (for AURA)

A thin **STDIO** MCP server wrapping
[open-coscientist](https://github.com/jataware/open-coscientist) (an open
LangGraph reimplementation of Google's AI Co-Scientist) so AURA's outbound MCP
gateway can use its **multi-agent research hypothesis generation**.

Upstream ships only an *HTTP* FastMCP server for its PubMed/INDRA literature
tools; AURA needs STDIO and wants the core `HypothesisGenerator`. This wrapper
provides that.

## Tools (read-only / generative; no external writes)

| Tool | Purpose |
|------|---------|
| `coscientist_health()` | Readiness + configured model. No LLM call. |
| `generate_hypotheses(research_goal, …)` | Run the co-scientist loop and return ranked hypotheses. |

`generate_hypotheses` output is **speculative AI-generated ideation, NOT
validated science**. AURA consumes it as `hypothesis_signal` (unverified,
low-confidence) and still routes it through the Scientific Verifier.

## Isolated environment (important)

open-coscientist pins `langgraph~=1.0.6` / `langchain-core~=1.2.7`, which would
**downgrade and break** local-deep-research in AURA's main env. So it lives in
its **own venv**:

```bash
python -m venv .mcp_envs/coscientist
.mcp_envs/coscientist/Scripts/python -m pip install open-coscientist fastmcp
```

AURA launches the wrapper with that venv's python (configured in `.env`):

```
AURA_MCP_USE_OPEN_COSCIENTIST=1
AURA_OPEN_COSCIENTIST_MCP_COMMAND=C:/Users/Woon/aura/.mcp_envs/coscientist/Scripts/python.exe
AURA_OPEN_COSCIENTIST_MCP_ARGS=C:/Users/Woon/aura/mcp_wrappers/open_coscientist/coscientist_server.py
```

## LLM key

`generate_hypotheses` calls an LLM via litellm. Set ONE key in the environment
(never logged):

- `GEMINI_API_KEY` — for the default `gemini/gemini-2.5-flash`
- `OPENAI_API_KEY` + `COSCIENTIST_MODEL=openai/gpt-4o-mini`
- `ANTHROPIC_API_KEY` + `COSCIENTIST_MODEL=anthropic/claude-3-5-sonnet-latest`

Optional caps: `COSCIENTIST_MAX_HYPOTHESES_CAP`, `COSCIENTIST_MAX_ITERATIONS_CAP`,
`COSCIENTIST_MAX_EVOLUTION_CAP`. Literature-review is OFF by default
(`COSCIENTIST_ENABLE_LIT_REVIEW=1` to enable, requires the upstream lit-review
MCP server).

## Run standalone (debug)

```bash
.mcp_envs/coscientist/Scripts/python mcp_wrappers/open_coscientist/coscientist_server.py
```
Speaks MCP over stdin/stdout; logs go to stderr.
