"""Test memory-service review pipeline — policy gate, pending files, commits."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from core.memory_service.review import review_memory_candidates
from core.memory_service.config import MemoryServiceConfig
from core.memory_service.schemas import MemoryCandidate


def _cfg(**overrides) -> MemoryServiceConfig:
    d = dict(
        enabled=True,
        write_mode="propose_only",
        pending_file_path="/tmp/aura_test_memory_candidates.jsonl",
        audit_log_path="/tmp/aura_test_memory_service.jsonl",
    )
    d.update(overrides)
    return MemoryServiceConfig(**d)


def _c(memory_type: str, cid: str = "c1", **kw) -> MemoryCandidate:
    defaults = dict(
        candidate_id=cid,
        memory_type=memory_type,
        content={"test": cid},
        source_session_id="s1",
    )
    defaults.update(kw)
    return MemoryCandidate(**defaults)


class TestProposeOnlyMode:
    def test_propose_only_no_commits(self):
        cfg = _cfg(write_mode="propose_only")
        cands = [_c("user_preference", cid="c1")]
        decisions = review_memory_candidates(cands, {}, config=cfg, session_id="s_r1")
        assert len(decisions) == 1
        assert decisions[0].committed is False
        assert decisions[0].decision in ("needs_human_review",)

    def test_pending_file_created(self):
        p = Path("/tmp/aura_test_memory_candidates.jsonl")
        p.unlink(missing_ok=True)

        cfg = _cfg(write_mode="propose_only", pending_file_path=str(p))
        cands = [_c("user_preference", cid="c1")]
        review_memory_candidates(cands, {}, config=cfg, session_id="s_r2")

        assert p.exists()
        lines = p.read_text().strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["candidate_id"] == "c1"
        p.unlink()

    def test_procedural_never_auto_commits(self):
        cfg = _cfg(write_mode="approved_only")
        cands = [_c("procedural_memory", cid="c_p1")]
        decisions = review_memory_candidates(cands, {}, config=cfg, session_id="s_r3")
        assert decisions[0].committed is False
        assert decisions[0].decision == "needs_human_review"

    def test_blocked_candidate_not_written(self):
        cfg = _cfg(write_mode="propose_only")
        cands = [
            _c("user_preference", cid="c_sec", content={"key": "sk-abcdefghijklmnopqrstuvwxyz"}),
        ]
        decisions = review_memory_candidates(cands, {}, config=cfg, session_id="s_r4")
        assert len(decisions) == 1
        assert decisions[0].decision == "blocked"


class TestApprovedOnlyMode:
    def test_user_preference_approved_falls_back_when_service_unavailable(self):
        """Policy says approve, but service is unreachable so falls back to pending."""
        cfg = _cfg(write_mode="approved_only")
        cands = [_c("user_preference", cid="c_a1")]
        # Service unavailable → commit fails → fallback to needs_human_review
        decisions = review_memory_candidates(cands, {}, config=cfg, session_id="s_r5")
        assert decisions[0].committed is False
        assert decisions[0].decision == "needs_human_review"
        assert "unavailable" in decisions[0].reason.lower()

    def test_user_preference_commits_when_service_available(self):
        """With mocked available service, user_preference auto-commits."""
        cfg = _cfg(write_mode="approved_only")
        cands = [_c("user_preference", cid="c_a2")]

        with mock.patch(
            "core.memory_service.review.memory_service_available", return_value=True,
        ):
            with mock.patch(
                "core.memory_service.review.commit_approved_memory",
                return_value={"ok": True, "memory_id": "mem-001"},
            ):
                decisions = review_memory_candidates(
                    cands, {}, config=cfg, session_id="s_r5b",
                )
        assert decisions[0].decision == "approve"
        assert decisions[0].committed is True
        assert decisions[0].memory_id == "mem-001"

    def test_evidence_verifier_route_approve_commits(self):
        cfg = _cfg(write_mode="approved_only")
        cands = [
            _c("evidence_memory", cid="c_ev1", verifier_route="approve"),
        ]
        with mock.patch(
            "core.memory_service.review.memory_service_available", return_value=True,
        ):
            with mock.patch(
                "core.memory_service.review.commit_approved_memory",
                return_value={"ok": True, "memory_id": "mem-ev1"},
            ):
                decisions = review_memory_candidates(
                    cands, {}, config=cfg, session_id="s_r6",
                )
        assert decisions[0].decision == "approve"
        assert decisions[0].committed is True

    def test_repository_memory_needs_review(self):
        cfg = _cfg(write_mode="approved_only")
        cands = [_c("repository_memory", cid="c_rep1")]
        decisions = review_memory_candidates(cands, {}, config=cfg, session_id="s_r7")
        assert decisions[0].decision == "needs_human_review"
