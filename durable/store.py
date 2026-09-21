"""Durable run store.

Persists one item per workflow run keyed by correlation_id. Two backends:
  - "dynamodb": production (table via DURABLE_TABLE_NAME)
  - "memory"  : in-process dict for the offline harness / tests

Item shape (DynamoDB attribute = JSON):
  pk            = "RUN#<correlation_id>"
  status        = running | suspended | completed
  cursor        = index of the next playbook step to run
  step_results  = {step_name: "resolved"|...}   (checkpoints; skip on replay)
  answers       = accumulated user answers keyed by field
  state_json    = serialized PlaybookState-relevant data
  version       = optimistic-lock counter
  updated_at    = iso timestamp
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RunRecord:
    correlation_id: str
    status: str = "running"           # running | suspended | completed
    cursor: int = 0                   # next step index
    category: str = ""
    step_results: dict[str, str] = field(default_factory=dict)
    answers: dict[str, Any] = field(default_factory=dict)
    pending_fields: list[str] = field(default_factory=list)  # fields we last asked for
    state_json: dict[str, Any] = field(default_factory=dict)
    version: int = 0
    updated_at: str = ""

    def to_item(self) -> dict[str, Any]:
        data = asdict(self)
        data["pk"] = f"RUN#{self.correlation_id}"
        return data

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "RunRecord":
        item = {k: v for k, v in item.items() if k != "pk"}
        return cls(**item)


class _MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, cid: str) -> dict | None:
        item = self._data.get(cid)
        return json.loads(json.dumps(item)) if item else None

    def put(self, cid: str, item: dict) -> None:
        self._data[cid] = json.loads(json.dumps(item))

    def clear(self) -> None:
        self._data.clear()


class _DynamoBackend:
    def __init__(self, table_name: str) -> None:
        import boto3

        self._table = boto3.resource("dynamodb").Table(table_name)

    def get(self, cid: str) -> dict | None:
        resp = self._table.get_item(Key={"pk": f"RUN#{cid}"})
        return resp.get("Item")

    def put(self, cid: str, item: dict) -> None:
        # Optimistic lock on version to guard concurrent resumes of the same ticket.
        expected = item.get("version", 0)
        item = dict(item)
        item["version"] = expected + 1
        cond = "attribute_not_exists(pk) OR version = :v"
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=cond,
                ExpressionAttributeValues={":v": expected},
            )
        except Exception as exc:  # ConditionalCheckFailedException
            raise ConcurrentUpdate(cid) from exc


class ConcurrentUpdate(Exception):
    """Raised when two invocations race to resume the same run."""


class RunStore:
    def __init__(self, backend: Any | None = None) -> None:
        if backend is not None:
            self._backend = backend
        elif os.environ.get("DURABLE_BACKEND", "memory").lower() == "dynamodb":
            self._backend = _DynamoBackend(os.environ["DURABLE_TABLE_NAME"])
        else:
            self._backend = _MemoryBackend()

    def load(self, correlation_id: str) -> RunRecord | None:
        item = self._backend.get(correlation_id)
        return RunRecord.from_item(item) if item else None

    def save(self, record: RunRecord) -> None:
        record.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        item = record.to_item()
        self._backend.put(record.correlation_id, item)
        record.version += 1  # reflect the stored increment locally

    # test helper
    def clear(self) -> None:
        if isinstance(self._backend, _MemoryBackend):
            self._backend.clear()
