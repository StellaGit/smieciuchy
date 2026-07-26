"""
DevOps Agent broker — ask-for-details OR investigate, replying to SNOW work_notes.

Inbound: SNOW Business Rule posts {incident_sys_id, incident_number, message, user, user_id}.
Behaviour:
  1. Verify shared-secret header.
  2. Cheap guard: empty/trivial request -> ask on the ticket, don't spend agent time.
  3. Get-or-create the per-incident chat session  -> DynamoDB (needed so a user's
     answer to a clarifying question reaches the SAME execution).
  4. Send the request to the agent wrapped in a triage instruction: it either
     runs the investigation OR replies with one clarifying question.
  5. Post whatever comes back (question OR findings) to work_notes (internal).

Fields used are exactly those from the existing Business Rule payload.

Packaging: attach a CURRENT boto3 layer (runtime boto3 doesn't know 'devops-agent').

Env: AWS_REGION, AGENT_SPACE_ID, SESSIONS_TABLE, SNOW_INSTANCE,
     SNOW_SECRET_ID, BROKER_SECRET_ID, SESSION_TTL_SEC (opt), USER_TYPE (opt)
"""

import os
import json
import time
import hmac
import base64
import urllib.request

import boto3

REGION           = os.environ["AWS_REGION"]
AGENT_SPACE_ID   = os.environ["AGENT_SPACE_ID"]
SESSIONS_TABLE   = os.environ["SESSIONS_TABLE"]
SNOW_INSTANCE    = os.environ["SNOW_INSTANCE"]
SNOW_SECRET_ID   = os.environ["SNOW_SECRET_ID"]
BROKER_SECRET_ID = os.environ["BROKER_SECRET_ID"]
SESSION_TTL_SEC  = int(os.environ.get("SESSION_TTL_SEC", "3600"))
USER_TYPE        = os.environ.get("USER_TYPE", "IAM")

# The triage instruction. Kept here so it's testable immediately; the durable
# home for this is a versioned SKILL on the agent (see note in the setup guide) —
# then the broker sends the raw message and this preamble goes away.
TRIAGE_PREAMBLE = (
    "You are the AWS DevOps Agent responding inside a ServiceNow incident. "
    "Your reply is posted back to the incident as an internal work note for "
    "cloud engineers.\n"
    "Decide based on the request below:\n"
    "- If you have enough information to investigate, run the investigation and "
    "report your findings and the most likely root cause, concisely.\n"
    "- If a specific detail is required and missing (e.g. a resource identifier "
    "such as an instance ID or IP, the AWS account, or the exact symptom), do "
    "NOT guess. Reply with a SINGLE concise clarifying question asking only for "
    "what you need, and nothing else.\n\n"
    "Request:\n"
)

agent = boto3.client("devops-agent", region_name=REGION)
ddb   = boto3.client("dynamodb", region_name=REGION)
sm    = boto3.client("secretsmanager", region_name=REGION)

_secret_cache = {}


def _get_secret(secret_id):
    if secret_id not in _secret_cache:
        _secret_cache[secret_id] = json.loads(
            sm.get_secret_value(SecretId=secret_id)["SecretString"]
        )
    return _secret_cache[secret_id]


def _verify_inbound(event):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    provided = headers.get("x-broker-secret", "")
    expected = _get_secret(BROKER_SECRET_ID)["shared_secret"]
    return bool(provided) and hmac.compare_digest(provided, expected)


def _get_or_create_session(incident_sys_id):
    item = ddb.get_item(
        TableName=SESSIONS_TABLE,
        Key={"incident_sys_id": {"S": incident_sys_id}},
    ).get("Item")
    if item and "execution_id" in item:
        return item["execution_id"]["S"]

    execution_id = agent.create_chat(
        agentSpaceId=AGENT_SPACE_ID, userType=USER_TYPE
    )["executionId"]
    now = int(time.time())
    ddb.put_item(
        TableName=SESSIONS_TABLE,
        Item={
            "incident_sys_id": {"S": incident_sys_id},
            "execution_id":    {"S": execution_id},
            "created_at":      {"N": str(now)},
            "expires_at":      {"N": str(now + SESSION_TTL_SEC)},
        },
    )
    return execution_id


def _ask_agent(execution_id, content):
    resp = agent.send_message(
        agentSpaceId=AGENT_SPACE_ID, executionId=execution_id, content=content
    )
    parts = []
    for ev in resp["events"]:
        if "contentBlockStop" in ev and ev["contentBlockStop"].get("text"):
            parts.append(ev["contentBlockStop"]["text"])
        elif "responseFailed" in ev:
            raise RuntimeError(ev["responseFailed"].get("errorMessage", "failed"))
        elif "responseCompleted" in ev:
            break
    return "\n".join(parts).strip()


def _post_worknote(incident_sys_id, text):
    creds = _get_secret(SNOW_SECRET_ID)  # {"user":..., "password":...}
    url = f"https://{SNOW_INSTANCE}/api/now/table/incident/{incident_sys_id}"
    token = base64.b64encode(
        f"{creds['user']}:{creds['password']}".encode()
    ).decode()
    req = urllib.request.Request(
        url, data=json.dumps({"work_notes": text}).encode(), method="PATCH"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def _note(body, requester):
    return (
        "AI-generated (advisory, non-validated) — DevOps Agent\n"
        f"In reply to: {requester}\n\n{body}"
    )


def lambda_handler(event, context):
    if not _verify_inbound(event):
        return {"statusCode": 401, "body": "unauthorized"}

    try:
        body = json.loads(event.get("body") or "{}")
        incident_sys_id = body["incident_sys_id"]
        message = (body.get("message") or "").strip()
        requester = body.get("user", "unknown")
    except (KeyError, ValueError) as e:
        return {"statusCode": 400, "body": f"bad request: {e}"}

    # 2. Cheap guard: nothing to work with -> ask, don't call the agent.
    if len(message) < 3:
        _post_worknote(
            incident_sys_id,
            _note(
                "What would you like me to look into? Please describe the issue "
                "and include the resource (e.g. instance ID or IP) and account "
                "if you know them.",
                requester,
            ),
        )
        return {"statusCode": 200, "body": json.dumps({"ok": True, "asked": True})}

    try:
        execution_id = _get_or_create_session(incident_sys_id)
        reply = _ask_agent(execution_id, TRIAGE_PREAMBLE + message)
        _post_worknote(incident_sys_id, _note(reply, requester))
        return {"statusCode": 200, "body": json.dumps({"ok": True})}
    except Exception as e:
        try:
            _post_worknote(
                incident_sys_id,
                _note(f"Could not complete the request: {e}", requester),
            )
        except Exception:
            pass
        print(f"ERROR: {e}")
        return {"statusCode": 500, "body": json.dumps({"ok": False, "error": str(e)})}
