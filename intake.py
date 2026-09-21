"""Intake adapter: normalize any channel into a single Envelope.

Ported and simplified from the legacy handler.py. Supports ServiceNow (webhook +
legacy direct), SNS-delivered AWS Health / email, and plain chat/API test payloads.
"""

from __future__ import annotations

import json
import re

from .models import Envelope

_SIGNATURE_CUTS = re.compile(
    r"Confidentiality notice and disclaimer|Disclaimer:|This service message was delivered",
    re.I,
)


def clean_text(text: str) -> str:
    """Strip markup, links, signatures and disclaimers before classification."""
    text = " ".join((text or "").replace("\xa0", " ").split())
    text = re.sub(r"<[^>]{0,200}>", " ", text)       # HTML tags
    text = re.sub(r"https?://\S+", " ", text)         # links
    text = _SIGNATURE_CUTS.split(text)[0]             # cut signatures/disclaimers
    text = re.sub(r"Long Description -", " ", text)
    return " ".join(text.split())[:1600]


def to_envelope(event: dict) -> Envelope:
    """Produce one Envelope regardless of the incoming channel."""
    # API Gateway proxy: the ServiceNow JSON payload is in event["body"].
    if isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except (ValueError, TypeError):
            pass

    # SNS-delivered AWS Health event or forwarded email.
    if "Records" in event:
        record = event["Records"][0].get("Sns", {})
        payload = record.get("Message", "")
        try:
            payload = json.dumps(json.loads(payload))
        except (ValueError, TypeError):
            pass
        return Envelope(
            source="aws_health_email",
            external_id=record.get("MessageId", ""),
            requester=record.get("TopicArn", ""),
            user_group="aws_service",
            text=clean_text(f"{record.get('Subject', '')} {payload}"),
        )

    # ServiceNow structured payload.
    if event.get("source") == "servicenow" and "record" in event:
        record = event.get("record") or {}
        user = event.get("user") or {}
        groups = user.get("groups") or ["general"]
        return Envelope(
            source="snow_inc",
            external_id=(event.get("correlation_id") or event.get("external_id")
                         or record.get("number", "")),
            correlation_id=event.get("correlation_id", ""),
            requester=user.get("user_id", "unknown"),
            user_group=groups[0] if isinstance(groups, list) else "general",
            text=clean_text(f"{record.get('short_description', '')} "
                            f"{record.get('description', '')} "
                            f"{record.get('aws_devops_note', '')}"),
            related_tickets=event.get("related_tickets", []),
        )

    # Legacy direct ServiceNow / chat / local test payload.
    number = event.get("number", "")
    if "source" in event:
        source = event["source"]
    elif number.startswith("RITM"):
        source = "snow_ritm"
    elif number.startswith("INC"):
        source = "snow_inc"
    else:
        source = "chat"
    return Envelope(
        source=source,
        external_id=number or event.get("external_id", ""),
        correlation_id=event.get("correlation_id", ""),
        requester=event.get("caller_id") or event.get("requester", ""),
        user_group=event.get("user_group", "general"),
        text=clean_text(f"{event.get('short_description', '')} "
                        f"{event.get('description') or event.get('text', '')}"),
        related_tickets=event.get("related_tickets", []),
    )
