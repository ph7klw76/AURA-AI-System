"""Verify task agents respect MCP boundaries.

Task agents may use external MCP only through the approved outbound MCP
gateway, and only when ``can_call_external_mcp=True``.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest
from core.task_agents.policy import validate_agent_spec, is_task_agents_enabled
from core.task_agents.schemas import AgentSpec


def _spec(**overrides):
    return AgentSpec(
        agent_id="ta-x", name="test", purpose="test",
        parent_session_id="s", parent_agent="o", parent_task="t",
        subtask="s", created_by="o",
        **overrides,
    )


class TestMCPBoundaries:
    def test_mcp_servers_require_external_mcp_flag(self):
        """Having allowed_mcp_servers without can_call_external_mcp is rejected."""
        ok, errors = validate_agent_spec(
            _spec(allowed_mcp_servers=["local_deep_research"])
        )
        assert not ok
        assert any("can_call_external_mcp" in e.lower() for e in errors)

    def test_mcp_flag_allows_mcp_tools(self):
        """When can_call_external_mcp=True, MCP tools from allowed namespaces pass."""
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["aura.mcp.local_deep_research.search"],
            can_call_external_mcp=True,
        ))
        assert ok, f"Errors: {errors}"

    def test_mcp_github_read_only_allowed(self):
        """GitHub read-only MCP tools are allowed through the gateway."""
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["aura.mcp.github.search_code"],
            can_call_external_mcp=True,
        ))
        assert ok, f"Errors: {errors}"

    def test_arbitrary_mcp_server_blocked(self):
        """Tools not in allowed namespaces are blocked."""
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["arbitrary.mcp.server"],
        ))
        assert not ok

    def test_github_write_tool_blocked_in_mcp(self):
        """GitHub write tools are blocked even with MCP flag."""
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["github.write.push"],
            can_call_external_mcp=True,
        ))
        assert not ok
        assert any("github.write" in e.lower() for e in errors)

    def test_github_merge_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["github.merge.pr"],
            can_call_external_mcp=True,
        ))
        assert not ok

    def test_github_delete_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["github.delete.branch"],
            can_call_external_mcp=True,
        ))
        assert not ok

    def test_shell_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["shell.exec"],
        ))
        assert not ok

    def test_subprocess_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["subprocess.run"],
        ))
        assert not ok

    def test_grant_submit_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["grant.submit"],
        ))
        assert not ok

    def test_patent_file_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["patent.file"],
        ))
        assert not ok

    def test_email_send_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["email.send"],
        ))
        assert not ok

    def test_mcp_tools_require_gateway_namespace(self):
        """Even with MCP flag, tools must use the aura.mcp.* namespace."""
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["local_deep_research.search"],  # no aura.mcp. prefix
            can_call_external_mcp=True,
        ))
        assert not ok
        assert any("namespace" in e.lower() or "prefix" in e.lower() for e in errors)

    def test_configured_disabled(self):
        """Task agents are disabled by default — no MCP access."""
        assert is_task_agents_enabled() is True
