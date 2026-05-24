"""Test memory-service schemas — validation, defaults, serialization."""
from __future__ import annotations

import json

import pytest
from core.memory_service.schemas import (
    ALLOWED_MEMORY_TYPES,
    AURAMemoryRecord,
    MemoryCandidate,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryWriteDecisionResult,
)


class TestAURAMemoryRecord:
    def test_defaults(self):
        r = AURAMemoryRecord()
        assert r.memory_id == ""
        assert r.memory_type == "unknown"
        assert r.namespace == []
        assert r.confidence == "medium"
        assert r.evidence_status == "unverified"

    def test_full_construct(self):
        r = AURAMemoryRecord(
            memory_id="mem-001",
            memory_type="user_preference",
            namespace=["aura", "user", "u1", "preferences"],
            key="writing_style",
            content={"style": "publication-quality README"},
            source_session_id="s42",
            source_agent="orchestrator",
            confidence="high",
            evidence_status="human_approved",
            verifier_route="approve",
            requires_verifier=False,
            requires_human_review=True,
            tags=["writing", "style"],
            limitations=["Only applies to README docs"],
        )
        assert r.memory_id == "mem-001"
        assert r.memory_type == "user_preference"
        assert r.confidence == "high"
        assert r.requires_human_review is True

    def test_invalid_memory_type_rejected(self):
        with pytest.raises(Exception):
            AURAMemoryRecord(memory_type="invalid_type")


class TestMemoryCandidate:
    def test_defaults(self):
        c = MemoryCandidate(candidate_id="c1")
        assert c.memory_type == "unknown"
        assert c.blocked is False
        assert c.block_reason == ""

    def test_blocked_true(self):
        c = MemoryCandidate(
            candidate_id="c1",
            blocked=True,
            block_reason="Contains API key",
        )
        assert c.blocked is True
        assert "API key" in c.block_reason


class TestMemoryRetrievalRequest:
    def test_defaults(self):
        r = MemoryRetrievalRequest(prompt="test")
        assert r.prompt == "test"
        assert r.max_results == 8
        assert r.memory_types == []


class TestMemoryRetrievalResult:
    def test_defaults(self):
        r = MemoryRetrievalResult()
        assert r.ok is True
        assert r.memories == []
        assert r.degraded is False
        assert r.compact_context == ""

    def test_degraded(self):
        r = MemoryRetrievalResult(
            ok=True,
            degraded=True,
            warnings=["Service unreachable"],
        )
        assert r.degraded is True
        assert len(r.warnings) == 1

    def test_compact_context(self):
        r = MemoryRetrievalResult(
            memories=[
                AURAMemoryRecord(
                    memory_type="user_preference",
                    content={"style": "concise"},
                ),
            ],
            compact_context='[user_preference] {"style": "concise"}',
        )
        assert "user_preference" in r.compact_context


class TestMemoryWriteDecisionResult:
    def test_defaults(self):
        d = MemoryWriteDecisionResult(candidate_id="c1")
        assert d.approved is False
        assert d.decision == "blocked"
        assert d.committed is False

    def test_approved(self):
        d = MemoryWriteDecisionResult(
            candidate_id="c1",
            approved=True,
            decision="approve",
            reason="Policy allows user preference auto-commit.",
            committed=True,
            memory_id="mem-001",
        )
        assert d.approved is True
        assert d.decision == "approve"
        assert d.committed is True


class TestAllowedTypes:
    def test_all_types_in_literal(self):
        """Ensure the ALLOWED_MEMORY_TYPES tuple matches the Literal."""
        expected = {
            "user_preference",
            "research_profile",
            "project_decision",
            "project_memory",
            "evidence_memory",
            "procedural_memory",
            "mcp_tool_memory",
            "task_agent_memory",
            "planner_memory",
            "repository_memory",
            "unknown",
        }
        assert set(ALLOWED_MEMORY_TYPES) == expected
