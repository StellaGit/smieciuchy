"""Durable playbook runner.

start_or_resume(event) is the single entrypoint. It:
  1. Normalizes the event and finds/creates the run record (keyed by correlation_id).
  2. On a NEW run: classifies, routes, and persists the plan.
  3. Merges any user answers from the event into accumulated answers.
  4. Executes playbook steps from the saved cursor, SKIPPING checkpointed steps.
  5. On NEEDS_INPUT: saves status=suspended and returns (workflow pauses).
  6. On completion: saves status=completed and returns the final decision.

Because step results are checkpointed, a resume never re-runs a step that already
succeeded - e.g. account lookup and the agent call are not repeated when the ticket
comes back with the AD-group answer.
"""

from __future__ import annotations

from typing import Any

from .. import accounts as accounts_mod
from ..classifier import classify
from ..intake import to_envelope
from ..kb import detect_kb
from ..models import Classification, Decision, Outcome, PlaybookState, StepResult
from ..note_builder import build_note
from ..playbooks import PLAYBOOKS, _AGENT_STEPS
from ..reply_extract import extract_answers
from ..router import route
from .store import RunRecord, RunStore


def _context_block(text: str) -> tuple[str, int]:
    matched, suggestions = accounts_mod.resolve(text)
    lines = [f"- account {a.account_name or a.account_id} resolved to id={a.account_id}, "
             f"env={a.environment or 'unknown'}, owner={a.owner or 'unknown'}" for a in matched]
    if not matched and suggestions:
        lines.append("- no exact account match; closest names: " + ", ".join(suggestions))
    if detect_kb(text):
        lines.append("- ticket text matches a known-issue KB article")
    return "\n".join(lines), len(matched)


def _structured_answers(event: dict) -> dict[str, Any]:
    """Structured answers if the caller sent them, e.g. {'answers': {'environment': 'prod'}}."""
    answers = event.get("answers")
    return dict(answers) if isinstance(answers, dict) else {}


def start_or_resume(event: dict, store: RunStore | None = None) -> dict[str, Any]:
    store = store or RunStore()
    envelope = to_envelope(event)
    cid = envelope.correlation_id or envelope.external_id
    record = store.load(cid)

    if record is None:
        # ---- NEW run: classify + route once, then persist the plan.
        kb_hit = detect_kb(envelope.text) is not None
        ctx, account_count = _context_block(envelope.text)
        classification = classify(envelope.text, envelope.source,
                                  kb_hit=kb_hit, context_block=ctx, account_count=account_count)
        route_result = route(envelope, classification)
        record = RunRecord(
            correlation_id=cid,
            category=classification.category,
            state_json={
                "envelope": _envelope_dict(envelope),
                "classification": _classification_dict(classification),
                "route": {"decision": route_result.decision.value,
                          "selected_agent": route_result.selected_agent,
                          "queue": route_result.queue, "owner": route_result.owner,
                          "reason": route_result.reason},
            },
        )
        if route_result.decision == Decision.DENIED:
            record.status = "completed"
            store.save(record)
            return _finalize(record, Outcome.READY_FOR_HUMAN)
    else:
        # ---- RESUME. Two ways an answer can arrive:
        #   1. structured  {'answers': {...}}  (if the caller ever sends it)
        #   2. free text    the reply prose in the ticket body (the current SNow flow)
        record.answers.update(_structured_answers(event))

        reply = envelope.text
        if reply:
            prior_text = record.state_json["envelope"].get("text", "")
            full_text = f"{prior_text} {reply}".strip()
            record.state_json["envelope"]["text"] = full_text
            # Extract the fields we are actually waiting on from the free-text reply.
            pending = set(record.pending_fields)
            if pending:
                extracted = extract_answers(reply, pending, full_text)
                record.answers.update(extracted)

    return _execute(record, store)


def _execute(record: RunRecord, store: RunStore) -> dict[str, Any]:
    envelope = _envelope_from(record.state_json["envelope"])
    classification = _classification_from(record.state_json["classification"])
    # Merge accumulated answers into classifier fields so require_* steps see them.
    classification.fields = {**classification.fields, **record.answers}

    state = _rebuild_state(record, envelope, classification)
    steps = PLAYBOOKS.get(record.category)

    if steps is None:
        record.status = "completed"
        store.save(record)
        outcome = Outcome.READY_FOR_HUMAN
        return _finalize(record, outcome, state)

    used_agent = any(record.step_results.get(s.__name__) == StepResult.RESOLVED.value
                     for s in steps if s.__name__ in _AGENT_STEPS)

    for idx in range(record.cursor, len(steps)):
        step = steps[idx]
        prior = record.step_results.get(step.__name__)
        if prior == StepResult.RESOLVED.value:
            # Already done on an earlier invocation - replay from checkpoint, don't rerun.
            if step.__name__ not in [s for s in state.completed_steps]:
                state.completed_steps.append(step.__name__)
            record.cursor = idx + 1
            continue

        result = step(state)
        state.completed_steps.append(step.__name__)
        record.step_results[step.__name__] = result.value
        # Persist any resolver output that must survive a suspend.
        record.state_json["work"] = _work_snapshot(state)

        if step.__name__ in _AGENT_STEPS and result == StepResult.RESOLVED:
            used_agent = True

        if result == StepResult.NEEDS_INPUT:
            record.status = "suspended"
            record.cursor = idx  # re-attempt THIS step after the answer arrives
            # Remember what we are waiting on so the free-text reply can be scoped.
            record.pending_fields = [state.blocked_on] if state.blocked_on else []
            store.save(record)
            state.outcome = Outcome.NEEDS_CLARIFICATION
            return _finalize(record, state.outcome, state)

        if result == StepResult.ESCALATE:
            record.status = "completed"
            record.cursor = idx + 1
            store.save(record)
            state.outcome = Outcome.READY_FOR_HUMAN
            return _finalize(record, state.outcome, state)

        record.cursor = idx + 1

    record.status = "completed"
    store.save(record)
    state.outcome = Outcome.AGENT_INVESTIGATING if used_agent else Outcome.READY_FOR_HUMAN
    return _finalize(record, state.outcome, state)


# ---- state (de)serialization -------------------------------------------------

def _envelope_dict(e) -> dict:
    return {"source": e.source, "external_id": e.external_id,
            "correlation_id": e.correlation_id, "requester": e.requester,
            "user_group": e.user_group, "text": e.text,
            "related_tickets": e.related_tickets}


def _envelope_from(d: dict):
    from ..models import Envelope
    return Envelope(**d)


def _classification_dict(c: Classification) -> dict:
    return {"category": c.category, "confidence": c.confidence, "fields": c.fields,
            "missing_info": c.missing_info, "reason": c.reason, "classifier": c.classifier}


def _classification_from(d: dict) -> Classification:
    return Classification(**d)


def _rebuild_state(record: RunRecord, envelope, classification) -> PlaybookState:
    state = PlaybookState(envelope=envelope, classification=classification)
    work = record.state_json.get("work", {})
    if work:
        from ..models import Account
        state.accounts = [Account(**a) for a in work.get("accounts", [])]
        state.resource = work.get("resource", {})
        state.standards_applied = work.get("standards_applied", [])
        state.approval_mentions = work.get("approval_mentions", [])
        state.agent_findings = work.get("agent_findings", {})
        state.notes = work.get("notes", [])
    return state


def _work_snapshot(state: PlaybookState) -> dict:
    return {
        "accounts": [{"account_id": a.account_id, "account_name": a.account_name,
                      "owner": a.owner, "sponsor": a.sponsor,
                      "environment": a.environment, "raw": a.raw} for a in state.accounts],
        "resource": state.resource,
        "standards_applied": state.standards_applied,
        "approval_mentions": state.approval_mentions,
        "agent_findings": state.agent_findings,
        "notes": state.notes,
    }


def _finalize(record: RunRecord, outcome: Outcome, state: PlaybookState | None = None) -> dict:
    r = record.state_json
    route_d = r.get("route", {})
    classification = _classification_from(r["classification"])
    envelope = _envelope_from(r["envelope"])
    if state is None:
        state = PlaybookState(envelope=envelope, classification=classification)
    state.outcome = outcome

    # rebuild RouteResult for the note
    from ..models import Decision as D, RouteResult
    route_result = RouteResult(
        decision=D(route_d.get("decision", "fallback")),
        selected_agent=route_d.get("selected_agent", ""),
        queue=route_d.get("queue", "Service Desk"),
        owner=route_d.get("owner", "service_desk"),
        reason=route_d.get("reason", ""),
    )
    note = build_note(state, route_result)
    return {
        "correlation_id": record.correlation_id,
        "external_id": envelope.external_id,
        "run_status": record.status,
        "category": classification.category,
        "confidence": round(classification.confidence, 2),
        "classifier": classification.classifier,
        "identity": {"user_group": envelope.user_group, "source": envelope.source},
        "decision": route_result.decision.value,
        "outcome": outcome.value,
        "queue": route_result.queue,
        "owner": route_result.owner,
        "reason": route_result.reason,
        "context": {
            "accounts": [{"account_id": a.account_id, "account_name": a.account_name,
                          "owner": a.owner, "environment": a.environment}
                         for a in state.accounts],
            "resource": state.resource,
            "standards_applied": state.standards_applied,
        },
        "playbook": {
            "completed_steps": state.completed_steps,
            "blocked_on": state.blocked_on,
            "questions": state.questions,
            "cursor": record.cursor,
        },
        "approval_mentions": state.approval_mentions,
        "agent_findings": state.agent_findings,
        "servicenow_note": note,
    }
