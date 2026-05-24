"""AURA China Grant Architect — thin shim.

The China-tailored Grant Architect is now implemented as a SUB-MODE
INSIDE ``agents/grant_architect.py`` (see ``run_china`` there) so the
two share one auditable codepath.  This module is a compatibility
shim: it re-exports the China entry point so:

  * the registry's existing ``china_grant_architect`` handler keeps
    working,
  * downstream callers that import ``from agents import
    china_grant_architect`` keep working,
  * callers that invoke ``china_grant_architect.run`` go through this
    module's binding.

Monkeypatching note (read-through, NOT write-through): patching
``china_grant_architect.run`` only affects callers that resolve ``run``
THROUGH this shim — the registry handler imports
``grant_architect.run_china`` directly, so it is unaffected.  Likewise,
patching an LLM/memory function on THIS module (e.g.
``china_grant_architect.ask_json``) does NOT change what
``grant_architect.run_china`` sees, because ``run_china`` resolves those
names from ``agents.grant_architect``'s own globals.  To stub the LLM for
``run_china``, patch the HOST module: ``agents.grant_architect.ask_json``.

Contract enforced by ``core.aura_principles.assert_china_grant_draft_contract``.
"""
from __future__ import annotations

from agents import grant_architect as _ga

# Re-export the public entry point under both names so existing imports
# (``china_grant_architect.run``) and the new canonical name
# (``china_grant_architect.run_china``) both work.
run = _ga.run_china
run_china = _ga.run_china

# Re-export the prompts under their original module-level names so any
# test or external caller that referenced them keeps working.
DRAFTING_SYSTEM_PROMPT = _ga.CHINA_DRAFTING_SYSTEM_PROMPT
REVIEWER_SYSTEM_PROMPT = _ga.CHINA_REVIEWER_SYSTEM_PROMPT


# READ-THROUGH passthrough for any name not explicitly re-exported above.
#
# ``__getattr__`` is consulted only for attributes MISSING from this module,
# and it READS from the host module.  It is NOT a write-through: assigning
# ``china_grant_architect.ask_json = fake`` sets a name on THIS module and
# does not alter ``agents.grant_architect``'s globals, which is what
# ``run_china`` actually reads.  Tests that need to stub the LLM/memory for
# ``run_china`` must patch the HOST module (``agents.grant_architect``).
import agents.grant_architect as _host_module


def __getattr__(name: str):
    # Lazy read-through for any name we didn't explicitly re-export above —
    # keeps the shim minimal.
    return getattr(_host_module, name)


__all__ = [
    "run", "run_china",
    "DRAFTING_SYSTEM_PROMPT", "REVIEWER_SYSTEM_PROMPT",
]
