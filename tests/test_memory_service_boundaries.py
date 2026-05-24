"""Test memory-service boundaries — secret storage, verifier bypass, procedural auto-commit."""
from __future__ import annotations

import pytest
from core.memory_service.policy import classify_memory_candidate, validate_memory_write
from core.memory_service.schemas import MemoryCandidate
from core.memory_service.config import MemoryServiceConfig


def _c(memory_type: str, **kw) -> MemoryCandidate:
    d = dict(candidate_id="c1", memory_type=memory_type, content={}, source_session_id="s1")
    d.update(kw)
    return MemoryCandidate(**d)


class TestNoSecretStorage:
    SECRETS = [
        ("sk-abcdefghijklmnopqrstuv", "OpenAI API key"),
        ("api_key = abcdefgh12345678", "API key assignment"),
        ("Bearer abcdefghijklmnopqrstuvwx", "Bearer token"),
        ("password = hunter2", "Password"),
        ("ghp_abcdefghijklmnopqrstuvwx0123456789", "GitHub PAT"),
        ("AKIA1234567890ABCDE", "AWS access key"),
        ("-----BEGIN RSA PRIVATE KEY-----", "Private key"),
    ]

    @pytest.mark.parametrize("secret,label", SECRETS)
    def test_blocked_secret(self, secret, label):
        c = _c("user_preference", content={"data": secret})
        result = classify_memory_candidate(c)
        assert result.blocked is True, f"{label} should be blocked"


class TestNoVerifierBypass:
    """Memory cannot bypass Scientific Verifier."""

    def test_evidence_memory_always_requires_verifier(self):
        c = _c("evidence_memory")
        result = classify_memory_candidate(c)
        assert result.requires_verifier is True

    def test_evidence_memory_rejected_route_blocked(self):
        cfg = MemoryServiceConfig(enabled=True, write_mode="approved_only")
        c = _c("evidence_memory", verifier_route="reject")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        assert dec.decision == "blocked"

    def test_evidence_memory_human_review_route_blocked(self):
        cfg = MemoryServiceConfig(enabled=True, write_mode="approved_only")
        c = _c("evidence_memory", verifier_route="human_review")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        assert dec.decision == "blocked"


class TestNoProceduralAutoCommit:
    """Procedural memories NEVER auto-commit."""

    def test_procedural_always_human_review(self):
        cfg = MemoryServiceConfig(enabled=True, write_mode="approved_only")
        c = _c("procedural_memory")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        assert dec.approved is False
        assert dec.decision == "needs_human_review"

    def test_procedural_human_review_even_if_review_disabled(self):
        """When require_review_for_procedural=False, it can be approved but still marked."""
        cfg = MemoryServiceConfig(
            enabled=True,
            write_mode="approved_only",
            require_review_for_procedural=False,
        )
        c = _c("procedural_memory")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        # The classifier always sets requires_human_review=True for procedural
        assert c.requires_human_review is True


class TestPlannerBoundaries:
    """Planner memory cannot override policy."""

    def test_planner_memory_always_needs_review(self):
        cfg = MemoryServiceConfig(enabled=True, write_mode="approved_only")
        c = _c("planner_memory")
        c = classify_memory_candidate(c)
        dec = validate_memory_write(c, config=cfg)
        assert dec.decision == "needs_human_review"

    def test_planner_cannot_bypass_policy(self):
        """Even if marked approved somehow, the policy gate catches it."""
        c = _c("planner_memory", requires_human_review=False)
        c = classify_memory_candidate(c)
        # Classifier overrides: planner always needs human review
        assert c.requires_human_review is True
        assert c.confidence == "low"


class TestTaskAgentBoundaries:
    """Task-agent memory cannot grant permissions."""

    def test_task_agent_permission_blocked(self):
        c = _c("task_agent_memory", content={"can_bypass": True, "sudo": "yes"})
        result = classify_memory_candidate(c)
        assert result.blocked is True

    def test_task_agent_normal_pattern_not_blocked(self):
        c = _c("task_agent_memory", content={"role": "helper", "summary": "useful pattern"})
        result = classify_memory_candidate(c)
        assert result.blocked is False
        assert result.requires_human_review is True


class TestMCPBoundaries:
    """MCP memory cannot treat external output as truth."""

    def test_mcp_tool_memory_low_confidence(self):
        c = _c("mcp_tool_memory")
        result = classify_memory_candidate(c)
        assert result.confidence == "low"
        assert result.requires_verifier is True


class TestWriteDisabledBlocksAll:
    def test_disabled_blocks_every_memory_type(self):
        cfg = MemoryServiceConfig(enabled=False)
        for mt in ("user_preference", "evidence_memory", "procedural_memory",
                    "planner_memory", "task_agent_memory", "mcp_tool_memory"):
            c = _c(mt)
            c = classify_memory_candidate(c)
            dec = validate_memory_write(c, config=cfg)
            assert dec.decision == "blocked", f"{mt} should be blocked when disabled"
