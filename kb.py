"""Known-issue KB articles matched against ticket text.

A hit lets the classifier fast-path to kb_resolution and lets the note builder
surface the documented fix, so a repeat/documented issue is handled without an agent.
Articles can be grown; keep triggers specific to avoid false positives.
"""

from __future__ import annotations

import re
from typing import Any

KB_ARTICLES: list[dict[str, Any]] = [
    {
        "title": "AWS Transfer Family - SSH public key wrong format",
        "trigger": re.compile(
            r"(transfer family|\bsftp\b).{0,80}(wrong|incorrect|invalid|bad) format|"
            r"ssh key.{0,40}(wrong|incorrect|invalid|not accepted)",
            re.I | re.S,
        ),
        "guidance": (
            "The SSH public key provided is not in the format AWS Transfer Family "
            "accepts. Convert it with:\n"
            "  ssh-keygen -i -f <PublicKeyCustomer> > NewPublicKey.pub\n"
            "Then have the requester re-upload the converted (NewPublicKey.pub) key."
        ),
        "related_tickets": ["INC0454554"],
    },
]


def detect_kb(text: str) -> dict[str, Any] | None:
    for article in KB_ARTICLES:
        if article["trigger"].search(text or ""):
            return article
    return None
