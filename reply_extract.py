"""Extract answers from a free-text reply on a suspended ticket.

When a ticket is waiting on specific fields (blocked_on / pending questions), the
requester replies in prose. This module turns that prose into the structured
answers the require_* resolvers expect.

Two extractors:
  - extract_with_haiku : re-run the classifier's extraction over the accumulated
    text, scoped to the fields we are actually waiting on (production).
  - extract_with_rules : deterministic best-effort for the offline harness.

Both take the reply text plus the set of pending field keys, and return
{field_key: value} for whatever they could confidently pull out.
"""

from __future__ import annotations

import os
import re

# Fields the orchestrator asks for, with deterministic extractors for the harness.
# Each entry: field_key -> (regex, group_or_transform)
_YES_NO_RE = re.compile(r"\b(yes|yeah|yep|correct|i do|affirmative)\b", re.I)
_NO_RE = re.compile(r"\b(no|nope|i don'?t|negative)\b", re.I)
_ENV_RE = re.compile(r"\b(dev|development|prod|production|val|validation|test|staging|sandbox)\b", re.I)
_ADGROUP_RE = re.compile(
    r"(?:ad group|group|role|permission set)\s*(?:is|:|=|named|called)?\s*"
    r"([A-Za-z][A-Za-z0-9._-]{2,})", re.I)
_BUCKET_RE = re.compile(r"\b([a-z0-9][a-z0-9.-]{2,62})\b")


def _norm_env(value: str) -> str:
    v = value.lower()
    if v.startswith("dev"):
        return "dev"
    if v.startswith("prod"):
        return "prod"
    if v.startswith("val"):
        return "val"
    return v


def extract_with_rules(reply: str, pending: set[str]) -> dict[str, str]:
    """Deterministic best-effort extraction for offline use."""
    out: dict[str, str] = {}
    text = reply or ""

    if "pa_account_confirmed" in pending:
        if _YES_NO_RE.search(text):
            out["pa_account_confirmed"] = "yes"
        elif _NO_RE.search(text):
            out["pa_account_confirmed"] = "no"

    if "environment" in pending:
        m = _ENV_RE.search(text)
        if m:
            out["environment"] = _norm_env(m.group(1))

    if "target_identity" in pending:
        m = _ADGROUP_RE.search(text)
        if m:
            out["target_identity"] = m.group(1)

    if "resource" in pending:
        # bucket-ish token that isn't a plain english stopword
        for tok in _BUCKET_RE.findall(text):
            if tok.lower() not in {"the", "bucket", "access", "yes", "please", "and"} \
                    and ("-" in tok or "." in tok or len(tok) >= 5):
                out["resource"] = tok
                break

    if "design" in pending and len(text.split()) >= 4:
        # any substantive reply satisfies the open-ended design question
        out["design"] = text.strip()

    if "account_ref" in pending:
        m = re.search(r"\b(\d{12})\b", text)
        if m:
            out["account_ref"] = m.group(1)
        else:
            m = re.search(r"account\s+([a-z][a-z0-9._-]{2,})", text, re.I)
            if m:
                out["account_ref"] = m.group(1)

    return out


def extract_with_haiku(reply: str, pending: set[str], full_text: str) -> dict[str, str]:
    """Re-run structured extraction with Claude Haiku, scoped to pending fields."""
    import json

    import boto3

    model_id = os.environ.get("BEDROCK_MODEL_ID", "")
    if not model_id:
        return extract_with_rules(reply, pending)

    system = (
        "You extract answer values from a requester's reply to an IT ticket. "
        "Return ONLY a JSON object mapping each requested field to the value you can "
        "confidently extract; omit fields you cannot determine. "
        "pa_account_confirmed must be 'yes' or 'no'. environment must be 'dev' or 'prod'."
    )
    user = (
        f"Fields still needed: {sorted(pending)}\n"
        f"Full ticket so far: <ticket>{full_text[:3000]}</ticket>\n"
        f"Latest reply: <reply>{reply[:1500]}</reply>"
    )
    try:
        client = boto3.client("bedrock-runtime")
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 300, "temperature": 0},
        )
        raw = resp["output"]["message"]["content"][0]["text"]
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        return {k: str(v) for k, v in data.items() if k in pending and str(v).strip()}
    except Exception as exc:  # never fail the resume on a model error
        print(f"[reply_extract] haiku failed, using rules: {exc}")
        return extract_with_rules(reply, pending)


def extract_answers(reply: str, pending: set[str], full_text: str = "") -> dict[str, str]:
    """Front door: Haiku when configured, else deterministic rules."""
    if not reply or not pending:
        return {}
    if os.environ.get("BEDROCK_MODEL_ID"):
        return extract_with_haiku(reply, pending, full_text or reply)
    return extract_with_rules(reply, pending)
