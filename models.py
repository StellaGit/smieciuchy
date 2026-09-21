"""Core data structures shared across the orchestrator.

Kept as plain dataclasses so the whole pipeline is testable offline without AWS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    """Terminal state of a ticket after the orchestrator has done its pre-work.

    No auto_resolve in this phase: a human always approves/acts.
    """

    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_HUMAN = "ready_for_human"
    AGENT_INVESTIGATING = "agent_investigating"


class Decision(str, Enum):
    """Authorization decision, always produced by deterministic rules."""

    ALLOWED = "allowed"
    DENIED = "denied"
    FALLBACK = "fallback"


class StepResult(str, Enum):
    """Result of a single playbook resolver step."""

    RESOLVED = "resolved"        # step succeeded, continue
    NEEDS_INPUT = "needs_input"  # blocked on a user answer; stop and ask
    ESCALATE = "escalate"        # hand to a human queue; stop


@dataclass
class Envelope:
    """Channel-normalized ticket. One shape regardless of source."""

    source: str = "chat"
    external_id: str = ""
    correlation_id: str = ""
    requester: str = ""
    user_group: str = "general"
    text: str = ""
    related_tickets: list[str] = field(default_factory=list)


@dataclass
class Classification:
    """Output of the classifier (LLM or fast-path)."""

    category: str = "unknown"
    confidence: float = 0.0
    fields: dict[str, Any] = field(default_factory=dict)
    missing_info: list[str] = field(default_factory=list)
    reason: str = ""
    classifier: str = "rules"  # "haiku" | "rules" | "fast_path" | "channel"


@dataclass
class Account:
    """A resolved account row from accounts.csv (S3 runner_reports)."""

    account_id: str = ""
    account_name: str = ""
    owner: str = ""
    sponsor: str = ""
    environment: str = ""
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class PlaybookState:
    """Mutable state threaded through a playbook run."""

    envelope: Envelope
    classification: Classification
    accounts: list[Account] = field(default_factory=list)
    resource: dict[str, Any] = field(default_factory=dict)
    standards_applied: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    approval_mentions: list[dict[str, str]] = field(default_factory=list)
    agent_findings: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    blocked_on: str = ""
    outcome: Outcome | None = None


@dataclass
class RouteResult:
    """Deterministic routing outcome (before playbook execution)."""

    decision: Decision
    selected_agent: str
    queue: str
    owner: str
    reason: str
