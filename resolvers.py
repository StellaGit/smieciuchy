"""Playbook resolver steps.

Each resolver takes the mutable PlaybookState and returns a StepResult:
  RESOLVED    - step done, continue
  NEEDS_INPUT - blocked on a user answer; questions are appended, run stops
  ESCALATE    - hand to a human; run stops

Resolvers are small and independently testable. Adding an intent = composing
existing resolvers in playbooks.py.
"""

from __future__ import annotations

from . import accounts as accounts_mod
from .agent_adapter import build_agent_context, get_agent
from .kb import detect_kb
from .models import PlaybookState, StepResult
from .standards import az_for_environment, load_standards

# ---- shared -------------------------------------------------------------------

def _fields(state: PlaybookState) -> dict:
    return state.classification.fields or {}


def _ask(state: PlaybookState, key: str, question: str) -> StepResult:
    state.blocked_on = key
    if question not in state.questions:
        state.questions.append(question)
    return StepResult.NEEDS_INPUT


def require_field(key: str, question: str, aliases: tuple[str, ...] = ()):
    """Factory: resolver that requires a classifier field (or ask the user)."""
    def _resolver(state: PlaybookState) -> StepResult:
        fields = _fields(state)
        for candidate in (key, *aliases):
            if str(fields.get(candidate, "")).strip():
                return StepResult.RESOLVED
        # missing_info from the model can also carry the answer's absence
        return _ask(state, key, question)
    _resolver.__name__ = f"require_{key}"
    return _resolver


# ---- account / owner ----------------------------------------------------------

def verify_account(state: PlaybookState) -> StepResult:
    """Match the ticket to accounts.csv. Ask if we can't."""
    fields = _fields(state)
    matched, suggestions = accounts_mod.resolve(
        state.envelope.text,
        field_id=str(fields.get("account_ref", "")),
        field_name=str(fields.get("account_ref", "")),
    )
    if matched:
        state.accounts = matched
        return StepResult.RESOLVED
    if suggestions:
        return _ask(state, "account_ref",
                    "Which AWS account? Closest matches: " + ", ".join(suggestions))
    return _ask(state, "account_ref",
                "Which AWS account is this for? Please provide the account name or 12-digit id.")


def lookup_owner(state: PlaybookState) -> StepResult:
    """Owner comes from accounts.csv; requires verify_account to have run."""
    if not state.accounts:
        return _ask(state, "account_ref", "Which AWS account is this for?")
    if not state.accounts[0].owner:
        return _ask(state, "owner",
                    "The account owner is not on record - who should approve this request?")
    return StepResult.RESOLVED


# ---- resource (S3 etc.) -------------------------------------------------------

def resolve_resource(state: PlaybookState) -> StepResult:
    resource = str(_fields(state).get("resource", "")).strip()
    if not resource:
        return _ask(state, "resource",
                    "Which specific resource (e.g. S3 bucket name) do you need access to?")
    state.resource = {"name": resource}
    return StepResult.RESOLVED


def propose_policy(state: PlaybookState) -> StepResult:
    name = state.resource.get("name", "the resource")
    state.notes.append(
        f"Proposed least-privilege policy scope for {name}: grant only the actions the "
        f"requester stated; owner to confirm read vs write."
    )
    return StepResult.RESOLVED


# ---- new-account standards ----------------------------------------------------

def apply_org_defaults(state: PlaybookState) -> StepResult:
    cfg = load_standards()["new_account"]
    fields = _fields(state)
    region = str(fields.get("region", "")).strip() or cfg["region_default"]
    state.standards_applied.append(f"subnet_cidr={cfg['subnet_cidr']}")
    state.standards_applied.append(f"region={region}")
    state.notes.append(
        f"Applied org defaults: subnet {cfg['subnet_cidr']}, region {region}."
    )
    return StepResult.RESOLVED


def require_environment(state: PlaybookState) -> StepResult:
    env = str(_fields(state).get("environment", "")).strip()
    if not env:
        return _ask(state, "environment", "Is this account for dev or prod?")
    return StepResult.RESOLVED


def apply_az_policy(state: PlaybookState) -> StepResult:
    env = str(_fields(state).get("environment", "")).strip() or "prod"
    az = az_for_environment(env)
    state.standards_applied.append(f"az_{env}={az}")
    state.notes.append(
        f"AZ policy for {env}: at least {az} availability zone(s). "
        f"Requester asked for 1 subnet; confirm this meets the {env} minimum."
    )
    return StepResult.RESOLVED


def require_design_confirmation(state: PlaybookState) -> StepResult:
    return _ask(state, "design",
                "How will this account be used (workload, expected AZs, connectivity)? "
                "Needed to validate the design.")


# ---- access-request specifics (no directory API: ask, don't verify) ----------

require_ad_group = require_field(
    "target_identity", "Which AD group do you need access to?",
    aliases=("ad_group", "group"),
)


def require_pa_account(state: PlaybookState) -> StepResult:
    fields = _fields(state)
    if str(fields.get("pa_account_confirmed", "")).strip():
        return StepResult.RESOLVED
    return _ask(state, "pa_account_confirmed",
                "Do you have a privileged (PA) account? (yes/no) - we cannot verify this "
                "automatically.")


# ---- approval (SNow @-mention, not email) -------------------------------------

def draft_owner_approval(state: PlaybookState) -> StepResult:
    if not state.accounts:
        return _ask(state, "owner", "Who is the account owner that should approve this?")
    account = state.accounts[0]
    owner = account.owner or "the account owner"
    requester = state.envelope.requester or "the requester"
    what = state.classification.fields.get("target_identity") \
        or (state.resource.get("name") if state.resource else "") \
        or "the requested access"
    note = (f"@{owner}, please approve: {requester} is requesting {what} on account "
            f"{account.account_name or account.account_id} ({account.account_id}). "
            f"Approve here and Cloud Ops will action it.")
    state.approval_mentions.append({"owner": owner, "note": note})
    return StepResult.RESOLVED


# ---- investigation via DevOps agent ------------------------------------------

def invoke_devops_agent(state: PlaybookState) -> StepResult:
    """Create the read-only investigation in AWS DevOps Agent Space.

    The agent is asynchronous: this creates an INVESTIGATION backlog task and
    returns QUEUED. If the target account isn't associated with the Agent Space,
    the agent returns a blocker and we escalate to a human owner.
    """
    objective = state.classification.fields.get("requester_intent") or state.envelope.text
    context = build_agent_context(state.envelope, state.accounts, objective)
    result = get_agent().investigate(context)
    state.agent_findings = result

    if result.get("blockers"):
        for blocker in result["blockers"]:
            state.notes.append(f"Investigation blocked ({blocker.get('code','')}): "
                               f"{blocker.get('message','')}")
        return StepResult.ESCALATE
    return StepResult.RESOLVED


def summarize_findings(state: PlaybookState) -> StepResult:
    result = state.agent_findings or {}
    for line in result.get("findings") or []:
        state.notes.append(str(line))
    for fact in result.get("verified_facts") or []:
        state.notes.append(f"Verified: {fact}")
    cause = result.get("confirmed_cause")
    if cause:
        state.notes.append(f"Confirmed cause: {cause}")

    status = result.get("resolution_status", "in_progress")
    if status == "in_progress":
        task = result.get("task_id", "")
        url = result.get("agent_space_url", "")
        state.notes.append(
            f"Read-only investigation created in AWS DevOps Agent Space"
            + (f" (task {task})" if task else "")
            + ". Findings will follow on this ticket."
            + (f" Monitor: {url}" if url else "")
        )
    return StepResult.RESOLVED


def continue_agent_investigation(state: PlaybookState) -> StepResult:
    """Continue an in-progress agent investigation (collect findings + evaluate).
    
    This resolver is called on durable resume when investigation findings are ready.
    It collects streamed findings, evaluates them, and decides whether to continue
    iterating or hand off to human.
    """
    result = state.agent_findings or {}
    task_id = result.get("task_id")
    execution_id = result.get("execution_id")
    iteration = result.get("iteration", 0)
    
    if not task_id or not execution_id:
        state.notes.append("Cannot continue investigation: missing task_id or execution_id")
        return StepResult.ESCALATE
    
    # Build continuation prompt if evaluation suggested next steps
    continuation_prompt = result.get("suggested_continuation")
    
    # Collect findings and evaluate
    updated_result = get_agent().continue_investigation(
        task_id, execution_id, iteration, continuation_prompt
    )
    state.agent_findings = updated_result
    
    # Check resolution status
    resolution_status = updated_result.get("resolution_status", "human_handoff")
    
    if resolution_status == "blocked":
        for blocker in updated_result.get("blockers", []):
            state.notes.append(f"Investigation blocked: {blocker.get('message', '')}")
        return StepResult.ESCALATE
    
    if resolution_status == "continue":
        # Need another iteration - suspend and wait for next resume
        state.notes.append(
            f"Investigation iteration {iteration + 1} complete. "
            f"Continuing investigation: {updated_result.get('suggested_continuation', 'gathering more data')}"
        )
        # Save the updated state and return NEEDS_INPUT to pause
        # (In real flow, this would schedule another async continuation)
        return StepResult.NEEDS_INPUT
    
    # resolved or human_handoff - investigation complete
    return StepResult.RESOLVED


def attach_kb_guidance(state: PlaybookState) -> StepResult:
    article = detect_kb(state.envelope.text)
    if article:
        state.notes.append(f"Matched KB: {article['title']}")
        state.notes.append(article["guidance"])
        if article.get("related_tickets"):
            state.notes.append("Related tickets: " + ", ".join(article["related_tickets"]))
    return StepResult.RESOLVED
