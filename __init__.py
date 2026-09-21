"""Agent Orchestrator v2 - smart routing for ServiceNow tickets.

Pipeline:  normalize -> fast-path -> prefetch context -> classify (Haiku)
           -> deterministic route -> run intent playbook -> render SNow note.

The model only proposes a category and extracts fields; authorization, tier gates
and deny rules are always deterministic. No AWS write action is executed - every
ticket ends 'ready_for_human' or 'needs_clarification'.
"""

from .pipeline import handle_ticket

__all__ = ["handle_ticket"]
