# AURA Core — User Manual

A complete guide to running AURA locally with `qwen3:8b` via Ollama.

> AURA is a local-first multi-agent research assistant for OLED / TADF /
> photophysics / organic-electronics work. It plans literature scans, drafts
> grant proposals, prepares teaching material, plans data analysis, drafts
> public-facing communication, suggests collaborators, and analyses
> commercialization potential — all while refusing to perform any external
> action without your explicit approval.

---

## Table of Contents

1. [Quick Start (5 commands)](#1-quick-start-5-commands)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Configuration](#4-configuration)
5. [Running AURA](#5-running-aura)
6. [The Nine Agents](#6-the-nine-agents)
7. [Example Prompts (by intent)](#7-example-prompts-by-intent)
8. [Safety Boundaries — what AURA refuses to do](#8-safety-boundaries--what-aura-refuses-to-do)
9. [Reading AURA's Output](#9-reading-auras-output)
10. [Memory and Artifacts](#10-memory-and-artifacts)
11. [The Approval Log](#11-the-approval-log)
12. [Tests and Diagnostics](#12-tests-and-diagnostics)
13. [Troubleshooting](#13-troubleshooting)
14. [Reference: every CLI command](#14-reference-every-cli-command)

---

## 1. Quick Start (5 commands)

If you've already installed Conda + Ollama, this is everything:

```bash
# 1. Create the environment
conda create -n aura python=3.11 -y
conda activate aura

# 2. Install Python dependencies
cd C:\Users\Woon\aura
pip install -r requirements.txt

# 3. Pull the model (one-time, ~5.2 GB download)
ollama pull qwen3:8b

# 4. Verify everything works
python -m pytest tests/ -q

# 5. Start the agent
python main.py
```

You should see:

```
╭─────────────────────────────────────╮
│ AURA Core MVP                       │
│ Powered by Qwen3:8B via Ollama      │
╰─────────────────────────────────────╯
Type 'exit' or 'quit' to stop. Type 'json' after a result to see raw JSON.

AURA: ▌
```

Type a prompt, press Enter, wait 1–10 minutes for qwen3:8b to think.

---

## 2. Prerequisites

### Hardware

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 16 GB | 32 GB |
| Free disk | 15 GB (model + data + reports) | 50 GB |
| GPU | None required (CPU works, slowly) | NVIDIA with 8 GB+ VRAM (qwen3:8b runs ~5× faster) |
| OS | Windows 10/11, macOS 12+, Linux x86_64 | — |

A single qwen3:8b call takes:
- **CPU only:** 30 s – 5 min depending on prompt length
- **GPU (RTX 4070 / M2 Max):** 5–30 s

A full AURA workflow (governor + scout + 1–5 specialists + verifier + self-evolution) makes 4–10 LLM calls. Plan for 1–15 minutes per request on CPU, 1–5 minutes on GPU.

### Software

| Tool | Version | Why |
|---|---|---|
| Conda (Miniconda or Anaconda) | latest | Python environment isolation |
| Python | 3.11 | Pydantic v2, modern type hints |
| Ollama | 0.1.29 or newer | Local LLM runtime |
| Git | optional | If you want version control |
| `sqlite3` CLI | optional | If you want to inspect the literature DB |

---

## 3. Installation

### 3.1 Install Ollama

- **Windows:** download `OllamaSetup.exe` from <https://ollama.com/download>
- **macOS:** download `Ollama.dmg` from the same page
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

After install, confirm Ollama runs:

```bash
ollama --version
```

### 3.2 Pull qwen3:8b

```bash
ollama pull qwen3:8b
```

This downloads 5.2 GB. Verify:

```bash
ollama list
```

You should see:

```
NAME           ID              SIZE      MODIFIED
qwen3:8b       500a1f067a9f    5.2 GB    just now
```

> **Why qwen3:8b only?** AURA's safety contracts (verifier-after pattern, action policy, memory triage) are tuned to qwen3:8b's behaviour. Other models will work technically but may produce different safety failure modes. The `config.py` validator rejects every other model by default.

### 3.3 Create the conda environment

```bash
conda create -n aura python=3.11 -y
conda activate aura
```

### 3.4 Install Python dependencies

```bash
cd C:\Users\Woon\aura
pip install -r requirements.txt
```

This installs:

- `ollama` — Ollama Python client
- `pydantic` — schema validation
- `rich` — terminal formatting
- `pytest` — test runner
- `pyyaml` — research profile config
- `requests` — for arXiv / OpenAlex paper search

### 3.5 Confirm everything works

```bash
python -m pytest tests/ -q
```

Expected: `618 passed`. If anything fails, see [Troubleshooting](#13-troubleshooting).

Then a live model check:

```bash
python -c "from core.llm import ask_llm; print(ask_llm('test', 'Respond with exactly: AURA core llm check passed.'))"
```

Expected: `AURA core llm check passed.` (in 5–30 s the first time as the model loads).

---

## 4. Configuration

Most users don't need to change anything. The defaults work.

### 4.1 Default settings

| Setting | Default | What it controls |
|---|---|---|
| `AURA_MODEL` | `qwen3:8b` | The Ollama model name. Other names are rejected. |
| `AURA_TEMPERATURE` | `0.2` | Lower = more deterministic; higher = more creative |
| `AURA_NUM_CTX` | `8192` | Context window in tokens |
| `AURA_KEEP_ALIVE` | `30m` | How long Ollama keeps the model in RAM after a request |

### 4.2 Override via environment variables

```bash
# More deterministic
export AURA_TEMPERATURE=0.1

# Smaller context window (faster, less memory)
export AURA_NUM_CTX=4096
```

On Windows PowerShell:

```powershell
$env:AURA_TEMPERATURE = "0.1"
```

### 4.3 The research profile

`profiles/research_profile.yaml` defines:

- Your research topics (used to score papers)
- Scoring weights (relevance vs novelty vs grant potential vs ...)
- Protected topics that are never auto-modified

Default profile is tuned for OLED / TADF / red-NIR / lanthanide work. To change:

```yaml
research_topics:
  - TADF
  - OLED
  - red-NIR emission
  - lanthanide complex
  # add your own

scoring_weights:
  relevance: 0.30
  novelty: 0.22
  grant_potential: 0.18
  collaboration_potential: 0.12
  industry_potential: 0.08
  teaching_public_value: 0.10
```

The agent never modifies `protected_topics` automatically — those updates always go through the approval log.

---

## 5. Running AURA

### 5.1 The interactive CLI

```bash
conda activate aura
cd C:\Users\Woon\aura
python main.py
```

You get a prompt:

```
AURA: ▌
```

Type a request and press Enter. AURA prints:

1. **Strategic Decision** — which agents will run, why, autonomy level
2. **Research Scout** — only if literature is needed
3. **Specialist outputs** — Grant Architect, Teaching Mentor, etc.
4. **Scientific Verifier** — claim-level critique of everything above
5. **Self-Evolution** — what the session taught the system

After the result, you can type:

- `json` — print the full raw JSON of the last result (useful for debugging)
- a new prompt — start a fresh session
- `exit` or `quit` — stop AURA

### 5.2 First call takes longer

The first prompt loads `qwen3:8b` into RAM (~10–30 s on top of the inference time). After that, the model stays loaded for `AURA_KEEP_ALIVE=30m`, so subsequent calls are faster.

### 5.3 Watching what happens

The CLI prints colour-coded panels for each agent. If you want the raw structured output too, type `json` after a result.

---

## 6. The Nine Agents

AURA orchestrates one always-on coordinator (the governor), plus seven specialist agents and two cross-cutting reviewers.

| Agent | Role | When it runs | What it never does |
|---|---|---|---|
| **Strategic Governor** | Routes the request: which specialists to invoke, what evidence depth, what autonomy level, whether to require approval. | Always (first). | Doesn't act externally — it only decides. |
| **Research Scout** | Plans literature scans, runs OpenAlex/arXiv searches, scores papers, identifies research gaps. | When the prompt mentions papers, literature, gaps, or ideation. | Never publishes; never sends; never modifies the profile. |
| **Grant Architect** | Builds reviewer-aware grant proposal structure (objectives, work packages, reviewer attack points, evidence-needed-before-submission). | When the prompt mentions grant / proposal / funding. | Never submits a grant; clamped to `draft_only`. |
| **Teaching Mentor** | Builds teaching material with learning outcomes, Socratic questions, common misconceptions, quiz questions, technical cautions. | When the prompt mentions teach / lecture / class / students / quiz. | Doesn't oversimplify into false statements; flags uncertainty. |
| **Lab/Data Analyst** | Plans local data analysis (J-V-L, EQE, spectra, simulations) with required columns, plots, reproducibility checks, interpretation limits. | When the prompt mentions data, J-V-L, EQE, spectra, plots, calibration. | Never deletes/overwrites raw data; never claims efficiency without seen data. |
| **Influence/Public Communication** | Drafts LinkedIn posts, lay summaries, podcast angles with caution statements and safer wording. | When the prompt mentions LinkedIn, public, lay summary, audience. | Never publishes; always sets `approval_required_before_publishing=True`. |
| **Collaboration Operator** | Drafts outreach emails, prepares meeting agendas, identifies missing information about possible collaborators. | When the prompt mentions collaborator, partnership, draft email. | Never sends; always sets `approval_required_before_contacting=True`. |
| **Founder/Innovation** | Analyses commercialization: product hypothesis, target users, IP considerations, validation experiments, market assumptions, 90-day plan. | When the prompt mentions startup, commercialization, market, IP, patent, investor. | Always carries `legal_financial_disclaimer`; never gives legal/financial/IP advice; clamped to `draft_only`. |
| **Scientific Verifier** | Reviews every high-stakes specialist's claims with seven-reviewer-lens framing (materials scientist + device physicist + photophysicist + grant panel + industry feasibility + biomedical translation skeptic + methodology reviewer). | After every implemented specialist that has `requires_verification=True`. | Doesn't invent citations; flags overclaim, hype, missing evidence. |
| **Self-Evolution Engine** | Extracts session lessons, classifies failure modes (12-type taxonomy), proposes profile updates (drafts only). | Always (last). | Never auto-modifies profile; only stores lessons that pass a 6-gate triage (save_now + low risk + confidence ≥0.75 + non-session scope + verifier route ≠ reject/human_review + zero critical/high severity claims). |

The verifier-after pattern means the verifier runs **once per high-stakes specialist** in the same session. The self-evolution engine then has access to all specialist outputs and the verifier's review.

---

## 7. Example Prompts (by intent)

Below are prompts that reliably route to the right agents. Copy-paste them as a starting point and adapt.

### 7.1 Literature scan / research-gap finding

> *Find recent papers on red-NIR TADF OLEDs and identify the most promising research gap.*

Routing: `research_scout (literature_scan)` → `verifier` → `evolution`

What you get: top 5–8 scored papers, a gap candidate, claims to verify, suggested follow-up queries.

### 7.2 Idea exploration (no paper search)

> *I want to explore a research proposal on red/NIR TADF-lanthanide OLEDs for photobiomodulation therapy. What is the opportunity and what should I verify first?*

Routing: `research_scout (ideation)` → `verifier` → `evolution`

### 7.3 Grant proposal structure

> *Use the recent red-NIR TADF OLED literature and create a grant proposal structure with objectives, work packages, reviewer attack points, and evidence needed before submission.*

Routing: `research_scout` → `grant_architect` → `verifier` → `evolution`

What you get: possible title, problem statement, central hypothesis, 3+ objectives, work packages, reviewer attack points, evidence needed before submission, grant readiness verdict (`idea_only` / `concept_note_ready` / `needs_evidence` / `proposal_draft_ready`).

### 7.4 Teaching material

> *Explain TADF OLEDs to undergraduate students and create Socratic questions, misconceptions, quiz questions, and a short teaching activity.*

Routing: `teaching_mentor` → `verifier` → `evolution`

What you get: learner level, learning outcomes, conceptual explanation, Socratic questions, common misconceptions, quiz questions, assessment rubric, teaching activity, technical cautions.

### 7.5 Data analysis planning

> *I have OLED J-V-L data with voltage, current density, luminance, and EQE. Help me analyze what plots, checks, and reproducibility steps are needed.*

Routing: `lab_data_analyst` → `verifier` → `evolution`

What you get: analysis type, required columns, recommended methods/calculations/plots, data quality checks, reproducibility checks, interpretation limits, **safe_file_handling** ("Do not delete raw data", "Do not overwrite original files").

### 7.6 Public communication draft

> *Turn this red-NIR TADF OLED research direction into a LinkedIn post for a general scientific audience, but avoid hype.*

Routing: `influence_public_communication` → `verifier` → `evolution`

What you get: audience, communication goal, core message, 2–3 hook options, LinkedIn draft, public explanation, narrative angle, evidence cautions, overclaim risks, safer wording. **`approval_required_before_publishing` is always `True`.**

### 7.7 Collaboration outreach

> *Draft an email to a possible red-NIR OLED collaborator, but do not send it.*

Routing: `collaboration_operator` → `verifier` → `evolution`

What you get: collaboration goal, possible collaborator archetypes (not invented names), rationale, evidence-for-fit, missing information, draft email subject + body, meeting agenda, questions to ask, institutional risk notes. **`approval_required_before_contacting` is always `True`.**

### 7.8 Commercialization analysis

> *Evaluate whether my red-NIR OLED research idea could become a startup.*

Routing: `founder_innovation` → `verifier` → `evolution`

What you get: innovation thesis, product hypothesis, target users, value proposition, IP considerations, market assumptions, commercialization pathways, validation experiments, business model options, key risks, regulatory/ethical considerations, 90-day plan, **canonical legal/financial/IP disclaimer**, `approval_required_before_external_commitment=True`.

### 7.9 The "do everything" prompt

> *Find recent papers on red-NIR TADF OLEDs, identify a research gap, turn it into a grant concept, suggest possible collaborators, create a cautious LinkedIn draft, and evaluate whether there is any early commercialization potential.*

Routing: `research_scout → grant_architect → influence_public_communication → collaboration_operator → founder_innovation → verifier → evolution` (all five specialists in one pass)

Takes ~12 minutes on a GPU. Useful for exploring a project end-to-end.

### 7.10 Combination prompts

> *Find recent papers on TADF and explain them to my graduate students.*
> → `research_scout → teaching_mentor → verifier → evolution`

> *Find recent papers on TADF OLEDs and identify possible collaborators.*
> → `research_scout → collaboration_operator → verifier → evolution`

> *Find recent papers on red-NIR OLEDs and evaluate commercialization potential.*
> → `research_scout → founder_innovation → verifier → evolution`

---

## 8. Safety Boundaries — what AURA refuses to do

AURA has **four layers of defence** against external action:

1. **Permission patterns** — `core/permissions.py` matches the user prompt against ~30 high-risk patterns. Any match flags `requires_human_approval=True` and writes a row to `data/approval_log.jsonl`.
2. **Specialist safety invariants** — Each high-risk specialist forces conservative defaults regardless of LLM output (e.g. Influence agent always sets `approval_required_before_publishing=True`).
3. **ACTION_POLICY matrix** — Recommended actions are classified `auto` / `approval_required` / `never`. `never` actions (financial, legal, sign-agreement, file-patent) are stripped before reaching the user.
4. **Verifier-route veto on memory** — If the verifier's route is `reject` or `human_review`, the self-evolution engine refuses to auto-promote any lesson from that session to durable memory.

### What's blocked

| You ask AURA to... | Result |
|---|---|
| Send an email | Drafts only; flags approval required; writes to approval log |
| Publish a LinkedIn post | Drafts only; `approval_required_before_publishing=True` |
| Submit a grant proposal | Builds structure; `grant_readiness` capped at `needs_evidence`; flags approval |
| Delete raw data | Lab/Data Analyst refuses; `safe_file_handling` injects "do not delete" |
| Overwrite a CSV | Same — refuses, flags approval |
| Contact a specific researcher | Drafts only; `approval_required_before_contacting=True`; warns about institutional risk |
| Schedule a meeting | Drafts agenda only; flags approval |
| File a patent | Refuses; logs approval; founder agent flags as never-autonomous |
| Contact investors | Refuses; logs approval; founder agent flags as never-autonomous |
| Sign an agreement / NDA | `ACTION_POLICY` classifies as `never` |
| Make a financial decision | `ACTION_POLICY` classifies as `never` |
| Incorporate a company | `ACTION_POLICY` classifies as `never` |

### Defence-in-depth example

If you type:

> *Analyze my OLED data and delete the bad raw files.*

What happens:

- `requires_human_approval()` matches `'delete the'` → row written to approval log
- Lab/Data Analyst runs, but `safe_file_handling` is force-injected with "Do not delete raw data." and "Do not overwrite original files." regardless of what the LLM said
- Verifier flags the destructive intent
- No file is actually touched

**No agent has filesystem write access** to anything outside `data/` and `reports/`, and even those writes are append-only (memories.jsonl, reflections.jsonl, approval_log.jsonl).

---

## 9. Reading AURA's Output

### 9.1 The Strategic Decision panel

```
╭─ Strategic Decision ─────────────────────────────────╮
│ task_type: grant_strategy                            │
│ autonomy_level: L3                                   │
│ mission_alignment_score: 0.92                        │
│ evidence_requirement: high                           │
│ Selected agents:                                     │
│   1. research_scout (literature_scan)                │
│   2. grant_architect                                 │
│   3. scientific_verifier                             │
│   4. self_evolution_engine                           │
│ requires_approval: False                             │
╰──────────────────────────────────────────────────────╯
```

| Field | Meaning |
|---|---|
| `task_type` | One of: research_scan, idea_evaluation, grant_strategy, teaching, communication, collaboration, data_analysis, admin, unknown |
| `autonomy_level` | L0 (answer only) → L1 (draft in memory) → L2 (search + retrieve) → L3 (generate files) → L4 (prepare external action — won't execute) → L5 (would execute external action — always requires approval) |
| `mission_alignment_score` | 0.0–1.0; how central this is to your declared OLED/TADF research direction |
| `evidence_requirement` | low / medium / high / ultra; sets verifier strictness |
| `requires_approval` | If `True`, an approval row was written to the log; the user must explicitly approve before any external action |

### 9.2 Specialist panels

Each specialist prints a colour-coded panel:

- **Yellow** — Grant Architect
- **Blue** — Teaching Mentor
- **Cyan** — Lab/Data Analyst
- **Magenta** — Influence/Public Communication
- **Green** — Research Scout
- (others use dim panels)

Inside each panel you'll see `evidence_level`, `confidence`, `approval_level`, plus specialist-specific fields (e.g. `grant_readiness`, `learner_level`, `analysis_type`).

### 9.3 The Verifier panel

The verifier shows:

- `overall_assessment`: weak / acceptable / strong / incomplete
- `route`: approve / revise / retrieve_more_evidence / human_review / reject
- `final_recommendation`: short text
- Per-claim breakdown: severity (low / medium / high / critical), support_status (supported / partially_supported / unsupported / contradicted / unverifiable), evidence_needed, correction

A **route of `reject` or `human_review`** is the verifier saying "do not proceed without manual review." It also vetoes self-evolution memory writes.

### 9.4 The Self-Evolution panel

Shows:

- `session_assessment`: one paragraph on what worked
- `failure_modes`: from a 12-type taxonomy
- `lesson_details`: candidate lessons, each with `save_decision` (`save_now` / `needs_review` / `discard`), `confidence`, `risk_if_applied`, `scope`
- `next_experiments`: suggested follow-ups
- `profile_update_proposals`: drafts only — never auto-applied

### 9.5 Type `json` to see the raw output

After any result, type `json` at the prompt to dump the full nested dictionary. Useful for:

- Debugging a missing field
- Feeding a result into a downstream tool
- Saving a session for later reference

---

## 10. Memory and Artifacts

AURA writes to four files under `data/`:

| File | Format | What it stores | Growth rate |
|---|---|---|---|
| `data/memories.jsonl` | JSONL, one record per line | Durable lessons that passed the 6-gate triage | ~1–3 lessons per session, only if all gates pass |
| `data/reflections.jsonl` | JSONL | Every session's `ReflectionRecord` (full session_assessment + failure_modes + lesson_details) | 1 per session |
| `data/approval_log.jsonl` | JSONL | Every prompt that triggered approval-required pattern OR a `verifier_route` event (`reject` / `human_review`) | 0–N per session |
| `data/research_memory.db` | SQLite | Every paper retrieved + scored by Research Scout | ~5–20 papers per literature_scan |
| `data/performance_log.jsonl` | JSONL | One line per session: which agents ran, latency, errors | 1 per session |

### 10.1 Inspecting memories

```bash
# Last 5 saved lessons
python -c "import json; [print(json.loads(l).get('content', '')[:120]) for l in open('data/memories.jsonl').readlines()[-5:]]"
```

### 10.2 Inspecting top papers

```bash
sqlite3 data/research_memory.db "SELECT title, source, total_score, recommended_action FROM papers ORDER BY total_score DESC LIMIT 5;"
```

Or in Python:

```python
import sqlite3
conn = sqlite3.connect("data/research_memory.db")
for row in conn.execute("SELECT title, source, total_score FROM papers ORDER BY total_score DESC LIMIT 5"):
    print(row)
```

### 10.3 Reading the latest session reflection

```bash
python -c "import json; r=[json.loads(l) for l in open('data/reflections.jsonl')][-1]; print(r['session_assessment'])"
```

### 10.4 Weekly briefs

When you ask for a weekly brief, AURA writes a Markdown file to `reports/weekly_brief_YYYY-MM-DD.md` with:

- Executive summary
- Top papers (ranked, with scores and recommended actions)
- Research gap candidate
- Risks and warnings

Open it with any Markdown reader.

### 10.5 Resetting memory

If you want to start fresh:

```bash
# Back up first!
cp -r data data_backup_$(date +%Y-%m-%d)

# Then truncate
> data/memories.jsonl
> data/reflections.jsonl
> data/approval_log.jsonl
> data/performance_log.jsonl

# To wipe paper DB:
rm data/research_memory.db
# (it auto-rebuilds on next literature_scan)
```

**The system never deletes these files itself.** You are always in control of what's persisted.

---

## 11. The Approval Log

`data/approval_log.jsonl` is the audit trail of every potentially-risky request. Each row looks like:

```json
{
  "user_input": "Send an email to this collaborator and invite them to join my grant.",
  "reason": "Input matches approval-required pattern: 'send an email'",
  "decision": { ...full governor decision... },
  "logged_at": "2026-05-09T14:23:11.456+08:00"
}
```

Or, when triggered by the verifier:

```json
{
  "trigger": "verifier_route",
  "route": "human_review",
  "user_input": "...",
  "governor_task_type": "communication",
  "logged_at": "..."
}
```

### 11.1 What to do when something is logged

1. Read the draft AURA produced (it never executed the action — it only drafted it)
2. If you want to proceed, copy the draft and act manually (e.g. send the email yourself, file the patent yourself)
3. If you decide AURA should never propose this again, optionally edit the prompt heuristics in `core/permissions.py`

### 11.2 Reviewing recent approvals

```bash
python -c "
import json
for line in open('data/approval_log.jsonl').readlines()[-5:]:
    r = json.loads(line)
    print(f'{r.get(\"logged_at\", \"\")[:19]}  {r.get(\"reason\", \"\")[:80]}')
    print(f'  prompt: {r.get(\"user_input\", \"\")[:100]}')
    print()
"
```

---

## 12. Tests and Diagnostics

### 12.1 Unit + integration tests (no LLM required)

```bash
python -m pytest tests/ -q
```

Expected: `618 passed`. These mock every LLM call and finish in under a minute.

### 12.2 Targeted test groups

```bash
# Just the qwen3:8b enforcement tests
python -m pytest tests/test_llm_config.py tests/test_wave2_qwen_enforcement.py tests/test_wave3_qwen_enforcement.py -q

# Just permissions
python -m pytest tests/test_wave2_permissions.py tests/test_wave3_permissions.py -q

# Just routing
python -m pytest tests/test_wave1_regression_before_wave2.py tests/test_wave2_routing.py tests/test_wave3_routing.py -q

# Single agent
python -m pytest tests/test_grant_architect.py -v
```

### 12.3 Live diagnostics (qwen3:8b required)

These hit the real model. Each takes 10–60 minutes.

```bash
# Wave 2 diagnostic — Lab/Data + Influence + research-to-public + dangerous_publish
python scripts/diagnose_wave2.py

# Wave 3 diagnostic — Collaboration + Founder + 2 dangerous probes
python scripts/diagnose_wave3.py

# Custom validation — Grant + Teaching + delete-data probe + full workflow
python scripts/live_validate_core.py
```

Output is colour-coded with PASS/FAIL safety checks for the dangerous prompts.

### 12.4 Reading the live validation report

After running diagnostics, see:

```
reports/live_validation_report.md
reports/live_validate_core_results.json
```

---

## 13. Troubleshooting

### 13.1 `ImportError: No module named ollama`

```bash
pip install ollama
```

### 13.2 `ConnectionError: [Errno 61] Connection refused` when calling Ollama

Ollama isn't running.

- **Windows:** check the Ollama icon in the system tray
- **macOS:** `Ollama.app` should be running
- **Linux:** `systemctl --user status ollama` or `ollama serve` in a separate terminal

Then verify:

```bash
ollama list
```

### 13.3 `Error: model 'qwen3:8b' not found`

```bash
ollama pull qwen3:8b
```

### 13.4 First call hangs for 60+ seconds

Normal. Ollama is loading the 5.2 GB model into RAM/VRAM. Subsequent calls are fast for the next 30 minutes (or however long `AURA_KEEP_ALIVE` is set).

### 13.5 `ValueError: AURA only permits qwen3:8b. Got 'X'.`

You set `AURA_MODEL` to something other than `qwen3:8b`. Either unset it:

```bash
unset AURA_MODEL    # bash/zsh
$env:AURA_MODEL = $null   # PowerShell
```

…or change it back:

```bash
export AURA_MODEL=qwen3:8b
```

### 13.6 Pytest fails with `qwen3:8b not in ALLOWED_MODELS`

You probably modified `config.py` and broke the allowlist. Restore from your backup or git history.

### 13.7 `JSON parse error from LLM output`

qwen3:8b sometimes emits malformed JSON for very long prompts. The system has fallback handlers that produce a safe-default output and mark `partial_results=True`. If you keep seeing this:

- Lower `AURA_TEMPERATURE` to `0.1`
- Increase `AURA_NUM_CTX` to `12288` (uses more memory)
- Shorten your prompt

### 13.8 An agent didn't run even though my prompt mentioned it

Check the Strategic Decision panel for `selected_agents`. If your specialist isn't there:

- Maybe your phrasing didn't match a keyword (see `_GRANT_ARCHITECT_KEYWORDS`, `_TEACHING_MENTOR_KEYWORDS`, etc. in `agents/strategic_governor.py`)
- Try a more explicit phrasing (e.g. "draft a LinkedIn post" instead of "share publicly")
- Type `json` to see the full governor rationale

### 13.9 The verifier says `incomplete` for everything

That means the model thinks evidence is too thin. Either:

- Run the literature-scan path first (so the verifier has actual papers to chew on)
- Provide more context in your prompt (cite specific papers, give numerical claims)
- Don't use the verifier's verdict as final truth — it's deliberately strict

### 13.10 OpenAlex / arXiv timeouts

If your network can't reach those APIs, the Research Scout will:

- Retry with timeout
- Fall back to cached papers in `data/research_memory.db`
- Set `partial_results=True` and `confidence=low`

This is intentional — the system gracefully degrades.

### 13.11 GPU not being used

```bash
ollama ps
```

Look for `PROCESSOR` column. If it says `100% CPU`, the model isn't using your GPU. Check your Ollama install — recent versions auto-detect CUDA / Metal.

---

## 14. Reference: every CLI command

### 14.1 Daily use

```bash
conda activate aura
python main.py
```

### 14.2 Run all tests

```bash
python -m pytest tests/ -q
```

### 14.3 Run one test file

```bash
python -m pytest tests/test_wave3_permissions.py -v
```

### 14.4 Live diagnostics

```bash
python scripts/diagnose_wave2.py        # Wave 2 agents + 2 safety probes (~20-50 min)
python scripts/diagnose_wave3.py        # Wave 3 agents + 2 safety probes (~30-60 min)
python scripts/live_validate_core.py    # Grant + Teaching + delete-data + full workflow
```

### 14.5 Inspect data

```bash
# Last 5 memories
python -c "import json; [print(json.loads(l).get('content', '')[:120]) for l in open('data/memories.jsonl').readlines()[-5:]]"

# Last 5 reflections
python -c "import json; [print(json.loads(l).get('session_assessment', '')[:120]) for l in open('data/reflections.jsonl').readlines()[-5:]]"

# Top 5 papers
sqlite3 data/research_memory.db "SELECT title, source, total_score FROM papers ORDER BY total_score DESC LIMIT 5;"

# Last 5 approval-log entries
python -c "import json; [print(json.loads(l).get('reason', '')[:80], '|', json.loads(l).get('user_input', '')[:80]) for l in open('data/approval_log.jsonl').readlines()[-5:]]"
```

### 14.6 Reset state

```bash
# Back up
cp -r data data_backup_$(date +%Y-%m-%d)

# Truncate JSONL
> data/memories.jsonl
> data/reflections.jsonl
> data/approval_log.jsonl
> data/performance_log.jsonl

# Wipe paper DB
rm data/research_memory.db
```

### 14.7 Verify model + Ollama

```bash
ollama list                          # see installed models
ollama ps                            # see what's currently loaded
ollama pull qwen3:8b                 # pull/update model
ollama run qwen3:8b "Say hi"         # quick interactive test (Ctrl+D to exit)
```

### 14.8 Verify core.llm

```bash
python -c "from core.llm import ask_llm; print(ask_llm('test', 'Respond with exactly: AURA core llm check passed.'))"
```

---

## Appendix A: Project layout cheatsheet

```
aura/
├── agents/                                 # all 9 agents
│   ├── strategic_governor.py
│   ├── research_scout.py
│   ├── grant_architect.py                  # Wave 1
│   ├── teaching_mentor.py                  # Wave 1
│   ├── lab_data_analyst.py                 # Wave 2
│   ├── influence_public_communication.py   # Wave 2
│   ├── collaboration_operator.py           # Wave 3
│   ├── founder_innovation.py               # Wave 3
│   ├── scientific_verifier.py
│   └── self_evolution_engine.py
├── core/
│   ├── llm.py                              # ONLY file that talks to Ollama
│   ├── orchestrator.py                     # registry-driven specialist loop
│   ├── registry.py                         # AgentSpec for every agent
│   ├── schemas.py                          # all Pydantic schemas
│   ├── permissions.py                      # ACTION_POLICY + approval patterns
│   ├── memory.py                           # JSONL + SQLite I/O
│   └── formatter.py                        # CLI output rendering
├── integrations/
│   └── research_evolution/                 # paper sources, scoring, weekly brief
├── tests/                                  # 618 tests (mocked, no LLM)
├── scripts/                                # live diagnostics
├── reports/                                # weekly briefs, validation reports
├── data/                                   # memories, reflections, approval log, papers DB
├── profiles/
│   └── research_profile.yaml               # your topics + scoring weights
├── main.py                                 # entry point
├── config.py                               # settings + model validator
├── requirements.txt
├── README.md
└── USER_MANUAL.md                          # this file
```

## Appendix B: Quick-reference safety rules

| Rule | Where it's enforced |
|---|---|
| Only `qwen3:8b` is the runtime model | `config._validate_model` |
| All LLM calls go through `core/llm.py` | `tests/test_llm_config.py` (static scan) |
| The 8 high-risk actions never execute autonomously | `core/permissions.ACTION_POLICY` |
| Every high-stakes specialist gets verifier review | `core/registry.AgentSpec.requires_verification` |
| Self-evolution can't promote weak claims to durable memory | `agents/self_evolution_engine._save_approved_lessons` (6 gates) |
| Specialist agents force conservative defaults | `_enforce_safety_invariants` in each Wave 1/2/3 agent |
| Self-Evolution always runs last | `agents/strategic_governor._order_agents` |

---

*End of manual. Last updated 2026-05-09 against AURA Wave 3 (618 tests passing, all 7 specialists implemented).*
