"""Account inventory lookup backed by accounts.csv in S3 (bucket: runner_reports).

Known columns: account, account_name, account_owner, account_sponsor.
The reader is tolerant of extra/renamed columns and of hyphen/underscore spelling.

Backends:
  - "s3"    : read the CSV object from S3 (production)
  - "local" : read a local CSV file path (offline tests / harness)

Set ACCOUNTS_BACKEND + ACCOUNTS_S3_BUCKET/ACCOUNTS_S3_KEY or ACCOUNTS_LOCAL_PATH.
"""

from __future__ import annotations

import csv
import difflib
import io
import os
import re
from functools import lru_cache

from .models import Account

_ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")
# "account mdev (123234567865)" / "account data-intelligence-val (975337691569)"
_NAME_WITH_ID_RE = re.compile(r"account\s+([a-z][a-z0-9._-]{1,50})\s*\(\s*(\d{6,14})\s*\)", re.I)


def _first(row: dict, *keys: str, default: str = "") -> str:
    """Read a column trying several spellings (hyphen/underscore, aliases)."""
    for key in keys:
        for variant in (key, key.replace("_", "-"), key.replace("-", "_")):
            if variant in row and str(row[variant]).strip():
                return str(row[variant]).strip()
    return default


def _row_to_account(row: dict) -> Account:
    return Account(
        account_id=_first(row, "account", "account_id"),
        account_name=_first(row, "account_name"),
        owner=_first(row, "account_owner", "owner"),
        sponsor=_first(row, "account_sponsor", "sponsor"),
        environment=_first(row, "environment", "env"),
        raw={k: (v or "") for k, v in row.items()},
    )


def _load_csv_text() -> str:
    backend = os.environ.get("ACCOUNTS_BACKEND", "local").lower()
    if backend == "s3":
        import boto3  # imported lazily so offline tests need no AWS

        bucket = os.environ["ACCOUNTS_S3_BUCKET"]  # e.g. "runner_reports"
        key = os.environ.get("ACCOUNTS_S3_KEY", "accounts.csv")
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8-sig")
    path = os.environ.get("ACCOUNTS_LOCAL_PATH", "")
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


@lru_cache(maxsize=1)
def load_accounts() -> tuple[Account, ...]:
    """Load and cache the full inventory. Cache cleared via reset_cache()."""
    text = _load_csv_text()
    if not text:
        return ()
    reader = csv.DictReader(io.StringIO(text))
    return tuple(_row_to_account(row) for row in reader)


def reset_cache() -> None:
    load_accounts.cache_clear()


# ---- extraction helpers -------------------------------------------------------

def extract_account_ids(text: str, field_id: str = "") -> list[str]:
    """Every distinct 12-digit id in the text, plus a valid id from classifier fields."""
    ids: list[str] = []
    if field_id and _ACCOUNT_ID_RE.fullmatch(field_id.strip()):
        ids.append(field_id.strip())
    for match in _ACCOUNT_ID_RE.findall(text or ""):
        if match not in ids:
            ids.append(match)
    return ids


def extract_account_name(text: str) -> str:
    """Account name from 'account <name> (<id>)' phrasing, else ''."""
    match = _NAME_WITH_ID_RE.search(text or "")
    return match.group(1) if match else ""


# ---- resolution ---------------------------------------------------------------

def by_id(account_id: str) -> Account | None:
    for acct in load_accounts():
        if acct.account_id == account_id:
            return acct
    return None


def by_name(name: str) -> Account | None:
    if not name:
        return None
    needle = name.strip().lower()
    for acct in load_accounts():
        if acct.account_name.strip().lower() == needle:
            return acct
    return None


def resolve(text: str, field_id: str = "", field_name: str = "") -> tuple[list[Account], list[str]]:
    """Resolve accounts named in a ticket.

    Returns (matched_accounts, suggestions). If exactly one account is confidently
    matched, suggestions is empty. If nothing matches, suggestions holds fuzzy
    'did you mean' names to put in a clarification.
    """
    matched: list[Account] = []
    for account_id in extract_account_ids(text, field_id):
        acct = by_id(account_id)
        if acct:
            matched.append(acct)

    # Name-based match (from "(id)" phrasing or the classifier's field).
    for name in (field_name, extract_account_name(text)):
        acct = by_name(name)
        if acct and acct not in matched:
            matched.append(acct)

    if matched:
        return matched, []

    # Nothing matched: offer fuzzy suggestions on the account_name column.
    candidates = [a.account_name for a in load_accounts() if a.account_name]
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9._-]{2,}", text or "")
    suggestions: list[str] = []
    for token in tokens:
        for hit in difflib.get_close_matches(token, candidates, n=2, cutoff=0.6):
            if hit not in suggestions:
                suggestions.append(hit)
    return [], suggestions[:3]
