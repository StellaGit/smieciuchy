"""Intent playbooks: an ordered list of resolvers per category, plus the runner.

Each case from cases.txt maps to a playbook:
  inc1 access_request   -> verify account, owner, ask AD group + PA, draft approval
  inc2 account_lifecycle -> apply /24 + AZ policy, confirm env + design
  inc3 resource_access  -> verify account, resolve bucket, owner, policy, approval
  inc4 incident         -> verify account, agent-investigate with account context
"""

from __future__ import annotations

from typing import Callable

from . import resolvers as R
from .models import Outcome, PlaybookState, StepResult

Resolver = Callable[[PlaybookState], StepResult]

PLAYBOOKS: dict[str, list[Resolver]] = {
    "access_request": [
        R.verify_account,
        R.lookup_owner,
        R.require_ad_group,
        R.require_pa_account,
        R.draft_owner_approval,
    ],
    "resource_access": [
        R.verify_account,
        R.resolve_resource,
        R.lookup_owner,
        R.propose_policy,
        R.draft_owner_approval,
    ],
    "account_lifecycle": [
        R.apply_org_defaults,
        R.require_environment,
        R.apply_az_policy,
        R.require_design_confirmation,
    ],
    "incident": [
        R.attach_kb_guidance,
        R.verify_account,
        R.invoke_devops_agent,
        R.summarize_findings,
    ],
    "read_only_investigation": [
        R.verify_account,
        R.invoke_devops_agent,
        R.summarize_findings,
    ],
    "network_change": [
        R.verify_account,
        R.invoke_devops_agent,
        R.summarize_findings,
    ],
    "kb_resolution": [
        R.attach_kb_guidance,
    ],
}

# Categories that route straight to a human queue with no automated pre-work.
HUMAN_ONLY = {"security_concern", "vendor_notice", "guardrail_exception",
              "provisioning", "unknown"}

# Which resolver steps invoke the agent (=> outcome agent_investigating).
_AGENT_STEPS = {"invoke_devops_agent", "continue_agent_investigation"}


def run_playbook(state: PlaybookState) -> PlaybookState:
    """Execute the playbook for the classified category, setting state.outcome."""
    category = state.classification.category
    steps = PLAYBOOKS.get(category)

    if steps is None:
        # No playbook: it's a human-only route or a clarification.
        state.outcome = Outcome.READY_FOR_HUMAN
        return state

    used_agent = False
    for step in steps:
        result = step(state)
        state.completed_steps.append(step.__name__)
        if step.__name__ in _AGENT_STEPS and result == StepResult.RESOLVED:
            used_agent = True
        if result == StepResult.NEEDS_INPUT:
            state.outcome = Outcome.NEEDS_CLARIFICATION
            return state
        if result == StepResult.ESCALATE:
            state.outcome = Outcome.READY_FOR_HUMAN
            return state

    state.outcome = Outcome.AGENT_INVESTIGATING if used_agent else Outcome.READY_FOR_HUMAN
    return state
