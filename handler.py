"""AWS Lambda entrypoint for the durable orchestrator.

One Lambda handles both the initial ticket and every resume (SNow reply / agent
callback). The run is keyed by correlation_id; state lives in DynamoDB, so the
workflow survives across invocations without Step Functions.
"""

from __future__ import annotations

import json
import os

from .durable import start_or_resume

API_KEY = os.environ.get("SNOW_TEMP_KEY", "")


def lambda_handler(event, context):
    # Only direct API Gateway calls carry a "headers" block; SNS / internal
    # invocations are already constrained to trusted AWS callers.
    if "headers" in event:
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if not API_KEY or headers.get("x-router-secret", "") != API_KEY:
            return {"statusCode": 401, "body": json.dumps({"error": "Unauthorized"})}

    decision = start_or_resume(event)
    print(json.dumps(decision))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(decision),
    }
