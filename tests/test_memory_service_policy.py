"""Test memory-service policy — classification, secret blocking, type rules."""
from __future__ import annotations

import os

import pytest
from core.memory_service.policy import classify_memory_candidate, validate_memory_write
from core.memory_service.config import MemoryServiceConfig
from core.memory_service.schemas import MemoryCandidate

_ENABLED_PROPOSE = MemoryServiceConfig(
    enabled=True,
    write_mode="propose_only",
)
_ENABLED_APPROVED = MemoryServiceConfig(
    enabled=True,
    write_mode="approved_only",
)


def _c(memory_type: str, **kw) -> MemoryCandidate:
    defaults = dict(
        candidate_id="c1",
        memory_type=memory_type,
        content={"test": "value"},
        source_session_id="s1",
    )
    defaults.update(kw)
    return MemoryCandidate(**defaults)


class TestClassifySecrets:
    def test_blocks_openai_api_key(self):
        c = _c("user_preference", content={"key": "sk-abcdefghijklmnopqrstuvwxyz"})
        result = classify_memory_candidate(c)
        assert result.blocked is True
        assert "API key" in result.block_reason

    def test_blocks_bearer_token(self):
        c = _c("user_preference", content={"auth": "Bearer abcdefghijklmnopqrstuv"})
        result = classify_memory_candidate(c)
        assert result.blocked is True

    def test_blocks_password_assignment(self):
        c = _c("user_preference", content={"config": "password = secret123"})
        result = classify_memory_candidate(c)
        assert result.blocked is True

    def test_blocks_github_pat(self):
        c = _c("user_preference", content={"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"})
        result = classify_memory_candidate(c)
        assert result.blocked is True

    def test_allows_normal_content(self):
        c = _c("user_preference", content={"style": "concise", "format": "markdown"})
        result = classify_memory_candidate(c)
        assert result.blocked is False


class TestClassifyTypeRules:
    def test_procedural_requires_human_review(self):
        c = _c("procedural_memory")
        result = classify_memory_candidate(c)
        assert result.requires_human_review is True

    def test_evidence_requires_verifier(self):
        c = _c("evidence_memory")
        result = classify_memory_candidate(c)
        assert result.requires_verifier is True

    def test_planner_low_confidence_and_review(self):
        c = _c("planner_memory")
        result = classify_memory_candidate(c)
        assert result.requires_human_review is True
        assert result.confidence == "low"

    def test_task_agent_blocks_permission_grant(self):
        c = _c("task_agent_memory", content={"action": "bypass verifier", "perm": "sudo"})
        result = classify_memory_candidate(c)
        assert result.blocked is True

    def test_mcp_tool_memory_low_confidence(self):
        c = _c("mcp_tool_memory")
        result = classify_memory_candidate(c)
        assert result.confidence == "low"
        assert result.requires_verifier is True

    def test_user_preference_not_blocked(self):
        c = _c("user_preference")
        result = classify_memory_candidate(c)
        assert result.blocked is False
        assert result.requires_human_review is False


class TestValidateProcedural:
    def test_procedural_needs_human_review(self):
        c = _c("procedural_memory")
        dec = validate_memory_write(c, config=_ENABLED_PROPOSE)
        assert dec.approved is False
        assert dec.decision == "needs_human_review"

    def test_procedural_approved_if_review_disabled(self):
        cfg = MemoryServiceConfig(enabled=True, require_review_for_procedural=False,
                                  write_mode="approved_only")
        c = _c("procedural_memory")
        dec = validate_memory_write(c, config=cfg)
        assert dec.approved is True


class TestValidateEvidence:
    def test_evidence_with_approve_route_approved(self):
        c = _c("evidence_memory", verifier_route="approve")
        dec = validate_memory_write(c, config=_ENABLED_APPROVED)
        assert dec.approved is True

    def test_evidence_with_reject_route_blocked(self):
        c = _c("evidence_memory", verifier_route="reject")
        dec = validate_memory_write(c, config=_ENABLED_APPROVED)
        assert dec.approved is False
        assert dec.decision == "blocked"

    def test_evidence_needs_verifier_if_no_route(self):
        c = _c("evidence_memory", verifier_route="")
        dec = validate_memory_write(c, config=_ENABLED_APPROVED)
        assert dec.decision == "needs_verifier"


class TestValidateWriteDisabled:
    def test_write_disabled_blocks_all(self):
        cfg = MemoryServiceConfig(enabled=False, write_mode="propose_only")
        c = _c("user_preference")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        assert dec.approved is False
        assert dec.decision == "blocked"
        assert "disabled" in dec.reason.lower()


class TestValidatePlannerMemory:
    def test_planner_needs_human_review(self):
        c = _c("planner_memory")
        dec = validate_memory_write(c, config=_ENABLED_APPROVED)
        assert dec.decision == "needs_human_review"


class TestValidateUnknown:
    def test_unknown_type_blocked(self):
        c = _c("unknown")
        dec = validate_memory_write(c, config=_ENABLED_APPROVED)
        assert dec.decision == "blocked"
