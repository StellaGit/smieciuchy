"""Deterministic routing. The model proposes a category; these rules decide
authorization, the assignment queue, and who owns the ticket. No model output
ever grants access.
"""

from __future__ import annotations

from .models import Classification, Decision, Envelope, RouteResult

# ServiceNow group name(s) allowed to reach the broader read-only agent scope.
CLOUD_ENGINEERING = {"cloud_engineering", "Cloud Engineering and Operations"}

# Sources that carry ops ownership + an audit trail, so a request raised there may
# reach the read-only agent even from a business user. Ad-hoc chat may not.
GOVERNED_SOURCES = {"snow_inc", "snow_ritm", "aws_health_email"}

# category -> (handler, agent_tier)   tier: None | "ro_limited" | "ro_extended"
ROUTING_MATRIX = {
    "access_request":          ("iam_intake", None),
    "resource_access":         ("iam_intake", None),
    "account_lifecycle":       ("cloud_governance", None),
    "incident":                ("devops_agent", "ro_limited"),
    "read_only_investigation": ("devops_agent", "ro_limited"),
    "network_change":          ("devops_agent", "ro_extended"),
    "provisioning":            ("cloud_engineering", "ro_extended"),
    "security_concern":        ("security_intake", None),
    "kb_resolution":           ("kb_self_service", None),
    "vendor_notice":           ("procurement", None),
    "guardrail_exception":     ("cloud_governance", None),
    "unknown":                 ("clarification", None),
}

QUEUE_BY_HANDLER = {
    "iam_intake":        "Identity & Access Management",
    "cloud_governance":  "Cloud Governance",
    "devops_agent":      "Cloud Ops automation",
    "cloud_engineering": "Cloud Engineering",
    "security_intake":   "Cyber Security Intake",
    "kb_self_service":   "Self-service",
    "procurement":       "Procurement / FinOps",
    "clarification":     "Intake bot",
    "denied_privileged": "None (blocked)",
}

OWNER_BY_HANDLER = {
    "devops_agent":      "servicenow_automation",
    "cloud_engineering": "cloud_engineering",
    "cloud_governance":  "cloud_governance",
}


def route(envelope: Envelope, classification: Classification) -> RouteResult:
    category = classification.category
    handler, tier = ROUTING_MATRIX.get(category, ("clarification", None))
    group = envelope.user_group
    source = envelope.source

    if classification.confidence < 0.5:
        return RouteResult(Decision.FALLBACK, "clarification",
                           QUEUE_BY_HANDLER["clarification"], "intake_bot",
                           "confidence below 0.5; intent unclear")

    # Tier gates: who may reach the read-only agent.
    if tier == "ro_extended" and group not in CLOUD_ENGINEERING:
        return RouteResult(Decision.DENIED, "denied_privileged",
                           QUEUE_BY_HANDLER["denied_privileged"], "cloud_governance",
                           f"'{category}' needs extended read scope (cloud engineering only); "
                           f"caller group '{group}'")
    if tier == "ro_limited" and group not in CLOUD_ENGINEERING and source not in GOVERNED_SOURCES:
        return RouteResult(Decision.DENIED, "denied_privileged",
                           QUEUE_BY_HANDLER["denied_privileged"], "cloud_governance",
                           f"read-only agent not exposed to '{group}' over ungoverned "
                           f"source '{source}'")

    queue = QUEUE_BY_HANDLER.get(handler, "Service Desk")
    owner = OWNER_BY_HANDLER.get(handler, "service_desk")
    decision = Decision.FALLBACK if handler == "clarification" else Decision.ALLOWED
    reason = f"category '{category}' -> handler '{handler}' for group '{group}' via '{source}'"
    return RouteResult(decision, handler, queue, owner, reason)
