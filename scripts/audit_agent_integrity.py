"""Whole-AURA integrity audit — agent-system-compatibility skill §17.

Verifies that the China Grant Architect arc of changes preserved
inter-agent communication and file-writing pathways.  Run:

    python scripts/audit_agent_integrity.py
"""
from __future__ import annotations

import subprocess
import sys
import typing
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

failures: list[str] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(name)
    flag = "[OK]  " if ok else "[FAIL]"
    print(f"{flag} {name}")
    if detail:
        print(f"        {detail}")


# 1. Registry integrity ------------------------------------------------------
from core.registry import AGENT_REGISTRY

required = {
    "research_scout", "grant_architect", "china_grant_architect",
    "scientific_verifier", "self_evolution_engine", "lab_data_analyst",
    "teaching_mentor", "influence_public_communication",
    "collaboration_operator", "founder_innovation", "patent_intelligence",
}
present = set(AGENT_REGISTRY.keys())
chk("17.1 every required agent registered", required.issubset(present),
    f"missing={required - present or 'none'}")
for name in required:
    spec = AGENT_REGISTRY[name]
    special = name in {"scientific_verifier", "self_evolution_engine"}
    chk(f"17.2 {name}: handler resolvable",
        spec.handler is not None or special)

# 2. Schema integrity --------------------------------------------------------
from core.schemas import (
    GrantArchitectOutput, ChinaGrantArchitectOutput,
    ResearchScoutOutput, TeachingMentorOutput,
)
for cls, kwargs in [
    (GrantArchitectOutput, {}),
    (ChinaGrantArchitectOutput, {}),
    (ResearchScoutOutput, {"mode": "literature_scan", "summary": "t"}),
    (TeachingMentorOutput, {"agent_name": "teaching_mentor", "summary": "t"}),
]:
    try:
        inst = cls(**kwargs)
        chk(f"17.5 schema default-constructs: {cls.__name__}",
            getattr(inst, "schema_version", 1) == 1)
    except Exception as e:
        chk(f"17.5 schema default-constructs: {cls.__name__}", False, str(e))

cga = ChinaGrantArchitectOutput()
chk("17.6 China output: additive fields default-safe",
    cga.references_used == []
    and cga.local_literature_evidence_used == []
    and cga.scout_diagnostics == {})

# 3. Permission boundary -----------------------------------------------------
hints = typing.get_type_hints(ChinaGrantArchitectOutput)
al = str(hints.get("approval_level"))
chk("17.11 China approval_level locked to draft_only",
    "draft_only" in al and "human_approval_required" not in al, f"hint={al}")
try:
    ChinaGrantArchitectOutput(approval_level="human_approval_required")
    chk("17.11 schema rejects escalation", False, "Pydantic accepted it!")
except Exception:
    chk("17.11 schema rejects escalation", True)

# 4. Executable contracts ----------------------------------------------------
from core.aura_principles import (
    DEEP_RESEARCH_REPORT_SECTIONS, CHINA_GRANT_PROPOSAL_SECTIONS,
    CHINA_GRANT_REVIEWER_ROSTER, CHINA_GRANT_SCORE_RUBRIC,
    assert_china_grant_draft_contract, ChinaGrantContractViolation,
)
chk("17.4 deep_research 16 sections", len(DEEP_RESEARCH_REPORT_SECTIONS) == 16)
chk("17.4 china 24 sections", len(CHINA_GRANT_PROPOSAL_SECTIONS) == 24)
chk("17.4 china rubric sums to 100", sum(CHINA_GRANT_SCORE_RUBRIC.values()) == 100)
chk("17.4 china 5 reviewers", len(CHINA_GRANT_REVIEWER_ROSTER) == 5)
try:
    assert_china_grant_draft_contract({"approval_level": "human_approval_required"})
    chk("17.11 contract guard rejects escalation", False)
except ChinaGrantContractViolation:
    chk("17.11 contract guard rejects escalation", True)
try:
    assert_china_grant_draft_contract({
        "approval_level": "draft_only",
        "recommended_actions": [{"description": "submit grant to funder"}],
    })
    chk("17.11 contract guard rejects forbidden action", False)
except ChinaGrantContractViolation:
    chk("17.11 contract guard rejects forbidden action", True)

# 5. Capability routing ------------------------------------------------------
from agents.strategic_governor import _keyword_specialist_agents, ALLOWED_AGENTS
for a in ("research_scout", "grant_architect", "china_grant_architect",
          "scientific_verifier", "self_evolution_engine"):
    chk(f"17.2 governor whitelist contains {a}", a in ALLOWED_AGENTS)
for prompt, expected in [
    ("Invoke the China sub-mode, draft a grant on MR-TADF", "china_grant_architect"),
    ("draft me a grant for OLED stability", "grant_architect"),
    ("draft an NSFC Key Program proposal", "china_grant_architect"),
    ("write a tutorial on TADF for students", "teaching_mentor"),
]:
    got = _keyword_specialist_agents(prompt)
    chk(f"17.3 routing -> {expected}", expected in got, f"got={got}")
# China + grant must be mutually exclusive
got = _keyword_specialist_agents("Invoke the China sub-mode, draft a proposal")
chk("17.3 china+grant mutually exclusive",
    "china_grant_architect" in got and "grant_architect" not in got, f"got={got}")

# 6. Orchestrator safety net -------------------------------------------------
from core.orchestrator import (
    _EVIDENCE_HEAVY_DOWNSTREAM_AGENTS, _upgrade_scout_mode_for_evidence_heavy_tasks,
)
chk("17.12 orchestrator whitelist: china_grant_architect",
    "china_grant_architect" in _EVIDENCE_HEAVY_DOWNSTREAM_AGENTS)
up = _upgrade_scout_mode_for_evidence_heavy_tasks(
    "ideation", {}, ["research_scout", "china_grant_architect"])
chk("17.12 orchestrator upgrades ideation->literature_scan", up == "literature_scan",
    f"got={up}")

# 7. File writer dirs --------------------------------------------------------
for rel in ("reports", "reports/pending_review", "reports/china_grants",
            "reports/deep_research", "reports/literature_scans", "data"):
    d = REPO / rel
    d.mkdir(parents=True, exist_ok=True)
    chk(f"17.9 writable dir: {rel}", d.is_dir())

# 8. Memory roundtrip --------------------------------------------------------
from core.memory import save_memory, retrieve_relevant_memory
try:
    save_memory("integrity_audit", "audit smoke probe xyzzy", {"audit": True})
    hits = retrieve_relevant_memory("xyzzy", limit=2)
    chk("17.9 memory save+retrieve roundtrip",
        any("xyzzy" in (h.get("content") or "") for h in hits),
        f"retrieved={len(hits)}")
except Exception as e:
    chk("17.9 memory save+retrieve roundtrip", False, str(e))

# 9. Self-evolution boundary (static scan) -----------------------------------
flagged = []
for py in (REPO / "agents").glob("*.py"):
    src = py.read_text(encoding="utf-8", errors="ignore")
    if ('approval_level="human_approval_required"' in src
            or "approval_level='human_approval_required'" in src):
        flagged.append(py.name)
chk("17.10 no agent statically escalates approval_level",
    not flagged, f"flagged={flagged}")

# 10. Template editable from inside AURA -------------------------------------
from agents.grant_architect import get_china_template
tmpl = get_china_template()
chk("17.10 china template resolvable in-system",
    tmpl.get("template_id") == "CHINA_GRANT_PROPOSAL_BLUEPRINT_V1"
    and len(tmpl.get("sections", [])) == 24
    and "presentation_outline" in tmpl)

# 11. Test suite -------------------------------------------------------------
# Phase 3 (goal A): the audit must exercise tests that ACTUALLY exist and
# must include the Phase 1 + Phase 2 regression suites so it does not claim
# coverage that is not run.  Every file below is verified present first; a
# missing file is a hard audit failure rather than a silently-skipped name.
_AUDIT_TEST_FILES = [
    "tests/test_china_grant_architect.py",
    "tests/test_grant_architect.py",
    "tests/test_draft_writer.py",
    "tests/test_orchestrator_smoke.py",
    # Phase 1 fail-closed safety/security regression coverage.
    "tests/test_phase1_fail_closed.py",
    # Phase 2 workflow-contract / persistence / consistency regression coverage.
    "tests/test_phase2_workflow_repairs.py",
]
_missing_tests = [f for f in _AUDIT_TEST_FILES if not (REPO / f).exists()]
chk("17.8 referenced test files exist",
    not _missing_tests, f"missing={_missing_tests or 'none'}")

if _missing_tests:
    # Don't claim a pass we cannot run.
    chk("17.8 contract + Phase 1/2 regression tests pass", False,
        "skipped: referenced test files missing")
else:
    res = subprocess.run(
        [sys.executable, "-m", "pytest", *_AUDIT_TEST_FILES, "-q", "--tb=no"],
        cwd=str(REPO), capture_output=True, text=True, timeout=300,
    )
    last = res.stdout.strip().splitlines()[-1] if res.stdout else "(no output)"
    chk("17.8 contract + Phase 1/2 regression tests pass",
        res.returncode == 0, last)

# Summary --------------------------------------------------------------------
total = 0
# recount from printed lines is messy; just use failures
print()
print("=" * 68)
if failures:
    print(f"  INTEGRITY AUDIT: {len(failures)} FAILURE(S)")
    for f in failures:
        print(f"    - {f}")
else:
    print("  INTEGRITY AUDIT: ALL §17 ACCEPTANCE CRITERIA PASSED")
print("=" * 68)
sys.exit(1 if failures else 0)
