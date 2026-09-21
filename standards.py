"""Loader for standards.yaml.

Falls back to a minimal built-in default set if PyYAML isn't installed or the file
is missing, so the offline harness always runs.
"""

from __future__ import annotations

import os
from functools import lru_cache

_DEFAULTS = {
    "new_account": {
        "subnet_cidr": "/24",
        "region_default": "us-east-1",
        "az_by_environment": {"dev": 1, "prod": 2, "default": 2},
    },
    "approval_required": [
        "access_request", "resource_access", "account_lifecycle",
        "network_change", "resource_policy_change", "decommission",
    ],
    "naming_convention": {"pattern": "[location][application][environment][number]"},
}

_PATH = os.path.join(os.path.dirname(__file__), "standards.yaml")


@lru_cache(maxsize=1)
def load_standards() -> dict:
    try:
        import yaml  # optional dependency
    except ImportError:
        return _DEFAULTS
    if not os.path.exists(_PATH):
        return _DEFAULTS
    with open(_PATH, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    # shallow-merge over defaults so missing keys are still present
    merged = dict(_DEFAULTS)
    merged.update(data)
    return merged


def az_for_environment(environment: str) -> int:
    cfg = load_standards()["new_account"]["az_by_environment"]
    return cfg.get((environment or "").lower(), cfg.get("default", 2))


def approval_required(category: str) -> bool:
    return category in load_standards().get("approval_required", [])
