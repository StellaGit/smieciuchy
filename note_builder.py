"""Render the ServiceNow work note from the finished PlaybookState.

The note is written verbatim into SNow. Approval @-mentions are folded in here.
"""

from __future__ import annotations

from .models import Outcome, PlaybookState, RouteResult


def build_note(state: PlaybookState, route: RouteResult) -> str:
    c = state.classification
    lines = [f"Intent: {c.category} (confidence {round(c.confidence, 2)}, via {c.classifier})"]
    if c.reason:
        lines.append(f"Reason: {c.reason}")
    lines.append(f"Routed to: {route.queue}")
    lines.append("")

    if state.accounts:
        for acct in state.accounts:
            lines.append(f"Account: {acct.account_name or 'n/a'} ({acct.account_id})"
                         + (f" | env {acct.environment}" if acct.environment else "")
                         + (f" | owner {acct.owner}" if acct.owner else ""))

    if state.standards_applied:
        lines.append("Standards applied: " + ", ".join(state.standards_applied))

    if state.notes:
        lines.append("")
        lines.extend(state.notes)

    if state.outcome == Outcome.NEEDS_CLARIFICATION and state.questions:
        lines.append("")
        lines.append("Information required before this can proceed:")
        for q in state.questions:
            lines.append(f"- {q}")

    if state.approval_mentions:
        lines.append("")
        for mention in state.approval_mentions:
            lines.append(mention["note"])

    lines.append("")
    lines.append(f"Status: {state.outcome.value if state.outcome else 'unknown'}")
    return "\n".join(lines)
