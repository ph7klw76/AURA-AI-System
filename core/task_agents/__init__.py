"""AURA Task-Scoped Agent System.

Task agents are temporary, bounded helpers created by the orchestrator to
handle narrow subtasks.  They do NOT replace existing AURA agents — the
Strategic Governor, Orchestrator, and Scientific Verifier remain in full
control of routing, verification, and persistence.

.. warning::
   Task agents are **disabled by default**.  Set ``AURA_TASK_AGENTS_ENABLED=1``
   to enable.

Public API — safe entry points for the orchestrator:
    :func:`maybe_create_task_agent`  — proposal + validation gate
    :func:`run_task_agent`           — execute a validated AgentSpec
"""

from __future__ import annotations

from .audit import log_blocked, log_created, log_executed, log_failed
from .factory import propose_task_agent
from .policy import is_task_agents_enabled
from .registry import find_existing_agent_for_task
from .runner import run_task_agent
from .schemas import (
    AgentCreationDecision,
    AgentSpec,
    TaskAgentRequest,
    TaskAgentResult,
)

__all__ = [
    "AgentSpec",
    "TaskAgentRequest",
    "TaskAgentResult",
    "AgentCreationDecision",
    "maybe_create_task_agent",
    "run_task_agent",
    "is_task_agents_enabled",
    "find_existing_agent_for_task",
]


def maybe_create_task_agent(
    session_id: str,
    parent_agent: str,
    requested_role: str,
    subtask: str,
    context: dict | None = None,
) -> AgentCreationDecision:
    """Single entry point for the orchestrator to request a task agent.

    Returns an ``AgentCreationDecision``.  The orchestrator should:
    1. Check ``decision.create_agent``.
    2. If True, call :func:`run_task_agent` with ``decision.proposed_spec``.
    3. If False and ``decision.use_existing_agent`` is set, route to that agent.
    4. Always route task-agent output through the Scientific Verifier.
    """
    from .factory import propose_task_agent as _propose
    from .schemas import TaskAgentRequest as _Req

    request = _Req(
        parent_session_id=session_id,
        parent_agent=parent_agent,
        requested_role=requested_role,
        subtask=subtask,
        context=context or {},
    )
    decision = _propose(request)

    # Audit every attempt
    if decision.create_agent and decision.proposed_spec:
        log_created(decision.proposed_spec, session_id)
    else:
        log_blocked(
            requested_role, subtask, decision.reason, session_id,
            existing_agent=decision.use_existing_agent,
        )

    return decision
