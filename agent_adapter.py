"""Adapter for the DevOps agent (AWS DevOps Agent Space).

Matches the contract of the existing Node.js invoke_agent (index.mjs):

  - Client:  AWS DevOps Agent (CreateBacklogTask / SendMessage / ListAssociations),
             NOT bedrock-agent-runtime.invoke_agent.
  - Async:   the first call CREATES an INVESTIGATION backlog task and returns
             immediately with status QUEUED / resolution_status "in_progress" and
             an Agent Space URL. Findings arrive later; the orchestrator resumes to
             evaluate / continue them (mirrors the index.mjs iteration loop).
  - Account association: the agent can only investigate an account that is
             ASSOCIATED with the Agent Space; otherwise it returns a blocker.
  - Runbook selection: Supports keyword, catalog_llm, and bedrock_kb modes.
  - Findings streaming: Uses SendMessageCommand with streaming response.
  - Evaluation: Second Bedrock model evaluates findings to determine resolution status.
  - Continuation: Iteration loop with max_iterations limit.

The rest of the orchestrator depends only on the DevOpsAgent protocol, so swapping
StubAgent <-> DevOpsAgentSpaceAgent is a single env var (AGENT_BACKEND).

Env vars (align with index.mjs):
  DEVOPS_AGENT_SPACE_ARN, DEVOPS_AGENT_LOGIN_URL, DEVOPS_AGENT_MODEL_TIER,
  DEVOPS_AGENT_TASK_PRIORITY, RUNBOOK_RETRIEVAL_MODE, RUNBOOK_CONFIG,
  RUNBOOK_MANIFEST_CONFIG, BEDROCK_KB_ID, RUNBOOK_SELECTOR_MODEL_ID,
  INVESTIGATION_EVALUATOR_MODEL_ID, MIN_INVESTIGATION_CONFIDENCE, MAX_ITERATIONS.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Protocol

from .models import Account, Envelope


def build_agent_context(envelope: Envelope, accounts: list[Account], objective: str) -> dict[str, Any]:
    """Account-scoped context handed to the agent (INVENTORY_CONTEXT in index.mjs)."""
    account = accounts[0] if accounts else None
    account_id = account.account_id if account else ""
    return {
        "correlation_id": envelope.correlation_id or envelope.external_id,
        "objective": objective,
        "account": {
            "account_id": account_id,
            "account_name": account.account_name if account else "",
            "environment": account.environment if account else "",
            "owner": account.owner if account else "",
        } if account else {},
        # index.mjs validates a strict 12-digit id and refuses to zero-pad.
        "account_id_format_valid": bool(re.fullmatch(r"\d{12}", account_id)),
        "ticket_text": envelope.text,
        "read_only": True,
    }


class DevOpsAgent(Protocol):
    def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Create/continue a read-only investigation and return current status."""
        ...
    
    def continue_investigation(self, 
                              task_id: str, 
                              execution_id: str,
                              iteration: int,
                              continuation_prompt: str | None = None) -> dict[str, Any]:
        """Collect streamed findings and evaluate them (for async agent completion)."""
        ...


class StubAgent:
    """Deterministic stand-in so the pipeline is fully testable without AWS."""

    def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        account = context.get("account", {})
        account_id = account.get("account_id", "")
        if account_id and not context.get("account_id_format_valid", True):
            return {
                "status": "blocked",
                "resolution_status": "blocked",
                "issue_resolved": False,
                "account_id": account_id,
                "blockers": [{"code": "INVALID_ACCOUNT_ID",
                              "message": "Account id is not a valid 12-digit id."}],
                "findings": [],
                "note": "Stub agent: invalid account id.",
            }
        return {
            "status": "QUEUED",
            "resolution_status": "in_progress",
            "issue_resolved": False,
            "task_id": "stub-task-" + (account_id or "0"),
            "execution_id": "stub-exec-1",
            "account_id": account_id,
            "iteration": 0,
            "findings": [
                f"[stub] Read-only investigation queued for account "
                f"{account_id or 'unknown'} on: {context.get('objective', '')}.",
            ],
            "verified_facts": [],
            "remaining_hypotheses": [],
            "blockers": [],
            "note": "Stub agent - replace with DevOpsAgentSpaceAgent for live runs.",
        }

    def continue_investigation(self, 
                              task_id: str, 
                              execution_id: str,
                              iteration: int,
                              continuation_prompt: str | None = None) -> dict[str, Any]:
        """Stub continuation - returns completed findings."""
        return {
            "status": "completed",
            "resolution_status": "resolved",
            "issue_resolved": True,
            "task_id": task_id,
            "execution_id": execution_id,
            "iteration": iteration + 1,
            "findings": [
                f"[stub iteration {iteration + 1}] Investigation completed. "
                f"EC2 security group misconfigured - port 22 not open to user's IP."
            ],
            "verified_facts": [
                "Security group sg-12345 attached to instance",
                "Inbound rule only allows 10.0.0.0/8",
            ],
            "remaining_hypotheses": [],
            "confirmed_cause": "Security group sg-12345 missing ingress rule for user IP",
        }


class DevOpsAgentSpaceAgent:
    """Live AWS DevOps Agent Space call. Mirrors index.mjs CreateBacklogTask flow.

    This creates the INVESTIGATION task and returns the QUEUED handoff. Collecting
    streamed findings, evaluating them, and iterating are handled via continue_investigation
    on later durable resumes, matching the async nature of the original Lambda.
    """

    def __init__(self) -> None:
        self.agent_space_arn = os.environ.get("DEVOPS_AGENT_SPACE_ARN", "")
        self.login_url = os.environ.get("DEVOPS_AGENT_LOGIN_URL", "")
        self.model_tier = os.environ.get("DEVOPS_AGENT_MODEL_TIER", "balanced")
        self.task_priority = os.environ.get("DEVOPS_AGENT_TASK_PRIORITY", "MEDIUM")
        self.runbook_mode = os.environ.get("RUNBOOK_RETRIEVAL_MODE", "keyword")
        self.runbook_config = json.loads(os.environ.get("RUNBOOK_CONFIG", '{"mode": "keyword"}'))
        self.evaluator_model_id = os.environ.get("INVESTIGATION_EVALUATOR_MODEL_ID", "")
        self.min_confidence = float(os.environ.get("MIN_INVESTIGATION_CONFIDENCE", "0.6"))
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "3"))

    def _agent_space_id(self) -> str:
        match = re.search(r"agentspace/([^/]+)$", self.agent_space_arn)
        if not match:
            raise RuntimeError("DEVOPS_AGENT_SPACE_ARN must be an Agent Space ARN")
        return match.group(1)

    def _client_token(self, correlation_id: str, title: str, description: str) -> str:
        payload = f"{correlation_id}|{title}|{description}|{self.task_priority}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        return f"{correlation_id[:31]}-{digest}"

    def _check_account_association(self, client: Any, account_id: str) -> list[dict]:
        """Check if account is associated with Agent Space. Returns blockers if not."""
        if not account_id or not re.fullmatch(r"\d{12}", account_id):
            return [{"code": "INVALID_ACCOUNT_ID",
                     "message": "Account id is not a valid 12-digit id."}]
        
        try:
            agent_space_id = self._agent_space_id()
            resp = client.list_associations(
                agentSpaceId=agent_space_id,
                resourceType="ACCOUNT",
            )
            associated = any(a.get("resourceId") == account_id 
                           for a in resp.get("associations", []))
            if not associated:
                return [{"code": "ACCOUNT_NOT_ASSOCIATED",
                         "message": f"Account {account_id} is not associated with this Agent Space."}]
        except Exception as exc:
            return [{"code": "ASSOCIATION_CHECK_FAILED",
                     "message": f"Could not verify account association: {exc}"}]
        return []

    def _select_runbook(self, context: dict[str, Any]) -> str | None:
        """Select runbook based on configured retrieval mode."""
        if self.runbook_mode == "keyword":
            # Simple keyword matching from ticket text
            text = context.get("ticket_text", "").lower()
            if "ec2" in text or "connectivity" in text or "unreachable" in text:
                return "ec2_connectivity_diagnostics"
            elif "s3" in text or "bucket" in text:
                return "s3_access_diagnostics"
            elif "network" in text or "security group" in text:
                return "network_diagnostics"
            return None
        
        elif self.runbook_mode == "catalog_llm":
            # Would call a Bedrock model to select from runbook catalog
            # Not implemented yet - requires RUNBOOK_SELECTOR_MODEL_ID
            return None
        
        elif self.runbook_mode == "bedrock_kb":
            # Would query Bedrock Knowledge Base for relevant runbooks
            # Not implemented yet - requires BEDROCK_KB_ID
            return None
        
        return None

    def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Create initial investigation task (async - returns immediately)."""
        import boto3

        client = boto3.client("devops-agent")  # region from env
        
        # Check account association before creating task
        account_id = context.get("account", {}).get("account_id", "")
        blockers = self._check_account_association(client, account_id)
        if blockers:
            return {
                "status": "blocked",
                "resolution_status": "blocked",
                "issue_resolved": False,
                "account_id": account_id,
                "blockers": blockers,
                "findings": [],
                "verified_facts": [],
                "remaining_hypotheses": [],
            }

        # Select runbook if configured
        runbook = self._select_runbook(context)
        
        agent_space_id = self._agent_space_id()
        correlation_id = context.get("correlation_id", "")
        objective = context.get("objective", "ServiceNow investigation")
        title = f"{correlation_id} {objective}"[:200]
        description = context.get("ticket_text", "")[:10000]

        # Add runbook to description if selected
        if runbook:
            description = f"[RUNBOOK: {runbook}]\n\n{description}"

        task = client.create_backlog_task(
            agentSpaceId=agent_space_id,
            taskType="INVESTIGATION",
            title=title,
            description=description,
            priority=self.task_priority,
            clientToken=self._client_token(correlation_id, title, description),
        )["task"]
        
        return {
            "status": task.get("status", "QUEUED"),
            "resolution_status": "in_progress",
            "issue_resolved": False,
            "task_id": task.get("taskId", ""),
            "execution_id": task.get("executionId", ""),
            "agent_space_url": self.login_url,
            "account_id": account_id,
            "runbook": runbook,
            "iteration": 0,
            "findings": [],
            "verified_facts": [],
            "remaining_hypotheses": [],
            "blockers": [],
        }

    def continue_investigation(self, 
                              task_id: str, 
                              execution_id: str,
                              iteration: int,
                              continuation_prompt: str | None = None) -> dict[str, Any]:
        """Collect findings via streaming and evaluate them.
        
        This is called on durable resume when the ticket comes back with findings
        ready or when continuing an investigation after evaluation says "continue".
        """
        import boto3

        if iteration >= self.max_iterations:
            return {
                "status": "completed",
                "resolution_status": "human_handoff",
                "issue_resolved": False,
                "findings": [f"Reached max iterations ({self.max_iterations}) without resolution."],
                "confirmed_cause": None,
            }

        devops_client = boto3.client("devops-agent")
        agent_space_id = self._agent_space_id()

        # Collect streamed findings using SendMessageCommand
        findings_text = self._collect_findings_stream(
            devops_client, 
            agent_space_id, 
            task_id, 
            execution_id,
            continuation_prompt
        )

        if not findings_text:
            return {
                "status": "in_progress",
                "resolution_status": "in_progress",
                "issue_resolved": False,
                "findings": ["Investigation in progress, no findings yet."],
            }

        # Evaluate findings with second Bedrock model
        evaluation = self._evaluate_findings(findings_text, iteration)
        
        return {
            "status": evaluation["status"],
            "resolution_status": evaluation["resolution_status"],
            "issue_resolved": evaluation["issue_resolved"],
            "task_id": task_id,
            "execution_id": execution_id,
            "iteration": iteration + 1,
            "findings": [findings_text],
            "verified_facts": evaluation.get("verified_facts", []),
            "remaining_hypotheses": evaluation.get("remaining_hypotheses", []),
            "confirmed_cause": evaluation.get("confirmed_cause"),
            "suggested_continuation": evaluation.get("suggested_continuation"),
        }

    def _collect_findings_stream(self,
                                 client: Any,
                                 agent_space_id: str,
                                 task_id: str,
                                 execution_id: str,
                                 prompt: str | None) -> str:
        """Stream findings from SendMessageCommand (mirrors index.mjs stream handling)."""
        try:
            message_input = prompt or "Provide current investigation findings."
            
            response = client.send_message(
                agentSpaceId=agent_space_id,
                taskId=task_id,
                executionId=execution_id,
                message=message_input,
            )
            
            # Collect streaming content blocks
            findings_parts = []
            if "stream" in response:
                for event in response["stream"]:
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"].get("delta", {})
                        if "text" in delta:
                            findings_parts.append(delta["text"])
            
            return "".join(findings_parts).strip()
        
        except Exception as exc:
            print(f"[agent_adapter] failed to collect findings stream: {exc}")
            return ""

    def _evaluate_findings(self, findings_text: str, iteration: int) -> dict[str, Any]:
        """Evaluate findings with Bedrock model to determine resolution status.
        
        Returns resolution_status: resolved | continue | blocked | human_handoff
        """
        if not self.evaluator_model_id or not findings_text:
            # No evaluator configured - default to human handoff
            return {
                "status": "completed",
                "resolution_status": "human_handoff",
                "issue_resolved": False,
                "verified_facts": [],
                "remaining_hypotheses": [],
                "confirmed_cause": None,
            }

        try:
            import boto3
            bedrock = boto3.client("bedrock-runtime")

            system_prompt = """You evaluate investigation findings and determine resolution status.
Return ONLY a JSON object:
{
  "resolution_status": "resolved | continue | blocked | human_handoff",
  "issue_resolved": true/false,
  "confidence": 0.0-1.0,
  "verified_facts": ["<facts confirmed by investigation>"],
  "remaining_hypotheses": ["<what still needs checking>"],
  "confirmed_cause": "<root cause if identified>",
  "suggested_continuation": "<next investigation step if status=continue>"
}

Status meanings:
- resolved: root cause found and issue is resolvable
- continue: made progress but need more investigation
- blocked: hit a blocker (permissions, resource unavailable, etc.)
- human_handoff: too complex or uncertain, needs human review"""

            user_prompt = f"""Investigation iteration {iteration + 1}:

<findings>
{findings_text[:4000]}
</findings>

Evaluate these findings and determine the resolution status."""

            response = bedrock.converse(
                modelId=self.evaluator_model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": 500, "temperature": 0},
            )

            raw = response["output"]["message"]["content"][0]["text"]
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))

            resolution_status = data.get("resolution_status", "human_handoff")
            confidence = float(data.get("confidence", 0.5))
            issue_resolved = data.get("issue_resolved", False)

            # Apply minimum confidence threshold
            if confidence < self.min_confidence and resolution_status == "resolved":
                resolution_status = "human_handoff"
                issue_resolved = False

            status = "completed" if resolution_status in ("resolved", "blocked", "human_handoff") else "in_progress"

            return {
                "status": status,
                "resolution_status": resolution_status,
                "issue_resolved": issue_resolved,
                "verified_facts": data.get("verified_facts", []),
                "remaining_hypotheses": data.get("remaining_hypotheses", []),
                "confirmed_cause": data.get("confirmed_cause"),
                "suggested_continuation": data.get("suggested_continuation"),
            }

        except Exception as exc:
            print(f"[agent_adapter] evaluation failed: {exc}")
            return {
                "status": "completed",
                "resolution_status": "human_handoff",
                "issue_resolved": False,
                "verified_facts": [],
                "remaining_hypotheses": [],
                "confirmed_cause": None,
            }


def get_agent() -> DevOpsAgent:
    backend = os.environ.get("AGENT_BACKEND", "stub").lower()
    if backend in ("devops_agent", "agent_space", "bedrock"):
        return DevOpsAgentSpaceAgent()
    return StubAgent()
