"""End-to-end pipeline: raw event -> routing decision + drafted SNow note.

    normalize -> kb/fast-path -> prefetch context -> classify (Haiku)
    -> deterministic route -> run intent playbook -> render note.
"""

from __future__ import annotations

from typing import Any

from . import accounts as accounts_mod
from .classifier import classify
from .intake import to_envelope
from .kb import detect_kb
from .models import Classification, Decision, PlaybookState
from .note_builder import build_note
from .playbooks import run_playbook
from .router import route


def _context_block(text: str, field_id: str = "") -> tuple[str, int]:
    """Pre-fetch cheap context (account matches) and format it for the prompt.

    Returns (context_block_string, number_of_accounts_matched).
    """
    matched, suggestions = accounts_mod.resolve(text, field_id=field_id)
    lines = []
    for acct in matched:
        lines.append(f"- account {acct.account_name or acct.account_id} resolved to "
                     f"id={acct.account_id}, env={acct.environment or 'unknown'}, "
                     f"owner={acct.owner or 'unknown'}")
    if not matched and suggestions:
        lines.append("- no exact account match; closest names: " + ", ".join(suggestions))
    if detect_kb(text):
        lines.append("- ticket text matches a known-issue KB article")
    return "\n".join(lines), len(matched)


def handle_ticket(event: dict) -> dict[str, Any]:
    envelope = to_envelope(event)

    kb_hit = detect_kb(envelope.text) is not None
    context_block, account_count = _context_block(envelope.text)

    classification: Classification = classify(
        envelope.text, envelope.source,
        kb_hit=kb_hit, context_block=context_block, account_count=account_count,
    )

    route_result = route(envelope, classification)

    state = PlaybookState(envelope=envelope, classification=classification)

    # Denied / pure-clarification routes skip the playbook.
    if route_result.decision == Decision.DENIED:
        note = build_note(state, route_result)
        return _serialize(envelope, classification, route_result, state, note)

    run_playbook(state)
    note = build_note(state, route_result)
    return _serialize(envelope, classification, route_result, state, note)


def _serialize(envelope, classification, route_result, state, note) -> dict[str, Any]:
    return {
        "correlation_id": envelope.correlation_id or envelope.external_id,
        "external_id": envelope.external_id,
        "category": classification.category,
        "confidence": round(classification.confidence, 2),
        "classifier": classification.classifier,
        "identity": {"user_group": envelope.user_group, "source": envelope.source},
        "decision": route_result.decision.value,
        "outcome": state.outcome.value if state.outcome else None,
        "queue": route_result.queue,
        "owner": route_result.owner,
        "reason": route_result.reason,
        "context": {
            "accounts": [
                {"account_id": a.account_id, "account_name": a.account_name,
                 "owner": a.owner, "environment": a.environment}
                for a in state.accounts
            ],
            "resource": state.resource,
            "standards_applied": state.standards_applied,
        },
        "playbook": {
            "completed_steps": state.completed_steps,
            "blocked_on": state.blocked_on,
            "questions": state.questions,
        },
        "approval_mentions": state.approval_mentions,
        "agent_findings": state.agent_findings,
        "servicenow_note": note,
    }
