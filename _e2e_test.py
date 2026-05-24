"""End-to-end integration tests — run with: python _e2e_test.py"""
import json, sys, sqlite3
from pathlib import Path

def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)

_FAILURES: list[str] = []


def check(label, condition, note=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {note}" if note else ""))
    # Phase 3 (goal B): record every failed check so the script can return a
    # truthful nonzero exit code instead of always exiting 0.
    if not condition:
        _FAILURES.append(label)
    return condition

# ============================================================
# STEP 3: IDEATION MODE
# ============================================================
section("STEP 3: IDEATION MODE")
from core.orchestrator import run_aura_core

result_ideation = run_aura_core(
    "I want to explore a research proposal on red/NIR TADF-lanthanide OLEDs "
    "for photobiomodulation therapy. What is the opportunity and what should I verify first?"
)

gov = result_ideation.get("strategic_governor", {})
scout = result_ideation.get("research_scout") or {}
verifier = result_ideation.get("scientific_verifier") or {}
evo = result_ideation.get("self_evolution_engine") or {}

# Governor checks
check("task_type is research-related",
      gov.get("task_type", "") not in ("unknown", ""),
      gov.get("task_type", "MISSING"))
check("research_scout in selected_agents",
      "research_scout" in gov.get("selected_agents", []),
      str(gov.get("selected_agents")))
check("research_scout_mode is ideation",
      gov.get("research_scout_mode", "") in ("ideation", "idea_evaluation"),
      gov.get("research_scout_mode", "MISSING"))
check("requires_approval is False",
      gov.get("requires_approval") is False,
      str(gov.get("requires_approval")))
check("mission_alignment_score > 0",
      float(gov.get("mission_alignment_score", 0)) > 0.0,
      str(gov.get("mission_alignment_score")))

# Scout checks
check("scout mode is ideation",
      scout.get("mode", "") in ("ideation", "idea_evaluation"),
      scout.get("mode", "MISSING"))
check("literature_scan_used is False",
      scout.get("literature_scan_used") is False,
      str(scout.get("literature_scan_used")))
check("summary not empty",
      len(scout.get("summary", "")) > 20,
      scout.get("summary", "")[:60])
check("research_gap_candidate not empty",
      len(str(scout.get("research_gap_candidate", ""))) > 10,
      str(scout.get("research_gap_candidate", ""))[:80])
check("findings present",
      len(scout.get("findings", [])) > 0,
      str(len(scout.get("findings", []))) + " findings")
check("claims_for_verification present",
      len(scout.get("claims_for_verification", [])) > 0,
      str(len(scout.get("claims_for_verification", []))) + " claims")
check("queries_recommended_next or queries_used present",
      len(scout.get("queries_recommended_next", [])) + len(scout.get("queries_used", [])) > 0)
check("NO top_papers (ideation doesn't call APIs)",
      len(scout.get("top_papers", [])) == 0,
      str(len(scout.get("top_papers", []))) + " papers")

# Verifier checks
check("verifier overall_assessment not empty",
      verifier.get("overall_assessment", "") != "",
      verifier.get("overall_assessment", "MISSING"))
check("verifier route set",
      verifier.get("route", "") in ("approve","revise","retrieve_more_evidence","human_review","reject"),
      verifier.get("route", "MISSING"))
check("verifier has final_recommendation",
      len(str(verifier.get("final_recommendation", ""))) > 5,
      str(verifier.get("final_recommendation",""))[:60])

# Evolution checks
check("session_assessment present",
      len(evo.get("session_assessment", "")) > 5,
      evo.get("session_assessment","")[:60])
check("what_worked or lesson_details present",
      len(evo.get("what_worked",[])) + len(evo.get("lesson_details",[])) > 0)

check("no errors", result_ideation.get("errors", []) == [], str(result_ideation.get("errors",[])))

# ============================================================
# STEP 4: LITERATURE SCAN
# ============================================================
section("STEP 4: LITERATURE SCAN")

result_lit = run_aura_core(
    "Find recent papers on red-NIR TADF OLEDs and identify which ones are useful for a grant proposal."
)

gov_lit = result_lit.get("strategic_governor", {})
scout_lit = result_lit.get("research_scout") or {}
verifier_lit = result_lit.get("scientific_verifier") or {}

check("research_scout_mode is literature_scan",
      gov_lit.get("research_scout_mode", "") == "literature_scan",
      gov_lit.get("research_scout_mode", "MISSING"))
check("scout mode is literature_scan",
      scout_lit.get("mode", "") == "literature_scan",
      scout_lit.get("mode", "MISSING"))
check("literature_scan_used is True",
      scout_lit.get("literature_scan_used") is True,
      str(scout_lit.get("literature_scan_used")))
# top_papers may be empty if APIs return nothing — both are acceptable
top_papers = scout_lit.get("top_papers", [])
check("top_papers field present (may be empty if APIs unavailable)",
      isinstance(top_papers, list),
      f"{len(top_papers)} papers found")
check("summary not empty",
      len(scout_lit.get("summary", "")) > 20)
check("confidence set",
      scout_lit.get("confidence", "") in ("low","medium","high"),
      scout_lit.get("confidence","MISSING"))
check("evidence_quality set",
      scout_lit.get("evidence_quality","") in ("weak","moderate","strong"),
      scout_lit.get("evidence_quality","MISSING"))
check("verifier ran on lit-scan result",
      verifier_lit.get("overall_assessment","") != "",
      verifier_lit.get("overall_assessment","MISSING"))

# SQLite check
check("no errors in literature scan",
      result_lit.get("errors", []) == [], str(result_lit.get("errors",[])))

# ============================================================
# STEP 5: WEEKLY BRIEF
# ============================================================
section("STEP 5: WEEKLY BRIEF")

result_brief = run_aura_core(
    "Generate a weekly research brief from recent OLED, TADF, lanthanide complex, and red-NIR emission papers."
)
scout_brief = result_brief.get("research_scout") or {}
report_paths = scout_brief.get("report_paths", [])
check("report_paths present or graceful failure",
      isinstance(report_paths, list),
      f"{len(report_paths)} report(s)")
if report_paths:
    rp = report_paths[0]
    check("report file exists on disk", Path(rp).exists(), rp)
    if Path(rp).exists():
        content = Path(rp).read_text(encoding="utf-8")
        check("report has executive summary", "Executive Summary" in content or "summary" in content.lower())
        check("report has top papers section", "Top Paper" in content or "paper" in content.lower())
        check("report length > 200 chars", len(content) > 200, f"{len(content)} chars")
else:
    print("  [INFO] No weekly brief file — APIs may have returned no papers (acceptable)")

# ============================================================
# STEP 6: PERMISSION BOUNDARY
# ============================================================
section("STEP 6: PERMISSION BOUNDARY")

result_perm = run_aura_core(
    "Find a promising author from recent red-NIR OLED papers and send them a collaboration email."
)
gov_perm = result_perm.get("strategic_governor", {})
check("requires_approval is True",
      gov_perm.get("requires_approval") is True,
      str(gov_perm.get("requires_approval")))
check("autonomy_level is L4 or L5",
      gov_perm.get("autonomy_level","") in ("L4","L5"),
      gov_perm.get("autonomy_level","MISSING"))
check("approval_reason mentions email/contact",
      any(kw in gov_perm.get("approval_reason","").lower() for kw in ["email","contact","send","collaborat"]),
      gov_perm.get("approval_reason","")[:80])

# Check approval log was written
import config
from core.memory import read_jsonl
try:
    approval_records = read_jsonl(config.APPROVAL_LOG_PATH)
    check("approval_log.jsonl has entries",
          len(approval_records) > 0,
          f"{len(approval_records)} entries")
except Exception as e:
    check("approval_log.jsonl readable", False, str(e))

# ============================================================
# STEP 7: FAILURE RESILIENCE (simulated API failure)
# ============================================================
section("STEP 7: FAILURE RESILIENCE")

from unittest.mock import patch

with patch("integrations.research_evolution.paper_sources.search_openalex",
           return_value=[{"source_error": "OpenAlex unavailable (simulated)"}]):
    with patch("integrations.research_evolution.paper_sources.search_arxiv",
               return_value=[{"source_error": "arXiv unavailable (simulated)"}]):
        result_fail = run_aura_core("Find recent papers on TADF OLEDs.")

scout_fail = result_fail.get("research_scout") or {}
check("system did not crash", True)
check("scout returned partial_results flag or empty top_papers",
      scout_fail.get("partial_results") is True or len(scout_fail.get("top_papers",[])) == 0,
      f"partial_results={scout_fail.get('partial_results')}, papers={len(scout_fail.get('top_papers',[]))}")
check("confidence is low or medium on failure",
      scout_fail.get("confidence","") in ("low","medium"),
      scout_fail.get("confidence","MISSING"))
check("verifier still ran", result_fail.get("scientific_verifier") is not None)
check("evolution still ran", result_fail.get("self_evolution_engine") is not None)

# ============================================================
# STEP 8: DATA ARTIFACTS
# ============================================================
section("STEP 8: DATA ARTIFACTS")

check("data/memories.jsonl exists", config.MEMORY_PATH.exists())
check("data/reflections.jsonl exists", config.REFLECTION_PATH.exists())
check("data/approval_log.jsonl exists", config.APPROVAL_LOG_PATH.exists())
check("data/research_memory.db exists", config.RESEARCH_DB_PATH.exists())
check("profiles/research_profile.yaml exists", config.RESEARCH_PROFILE_PATH.exists())
check("reports/ dir exists", config.REPORT_DIR.exists())

mem_count = len(read_jsonl(config.MEMORY_PATH))
ref_count = len(read_jsonl(config.REFLECTION_PATH))
check(f"memories.jsonl has records", mem_count > 0, f"{mem_count} records")
check(f"reflections.jsonl has records", ref_count > 0, f"{ref_count} records")

# SQLite check
try:
    conn = sqlite3.connect(config.RESEARCH_DB_PATH)
    rows = conn.execute("SELECT COUNT(*) FROM papers").fetchone()
    conn.close()
    check("research_memory.db has papers table", True, f"{rows[0]} rows")
except Exception as e:
    check("research_memory.db has papers table", False, str(e))

# Check research_profile.yaml was NOT auto-modified
import yaml
with open(config.RESEARCH_PROFILE_PATH) as f:
    profile = yaml.safe_load(f)
check("research_profile.yaml protected_topics intact",
      all(t in str(profile) for t in ["OLED","TADF"]))

section("DONE")

# Phase 3 (goal B): exit nonzero if any required check failed so this
# end-to-end harness reports a truthful shell exit code.
if _FAILURES:
    print(f"\n  {len(_FAILURES)} CHECK(S) FAILED:")
    for f in _FAILURES:
        print(f"    - {f}")
    sys.exit(1)
print("\n  ALL E2E CHECKS PASSED")
sys.exit(0)
