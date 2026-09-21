# Orchestrator + DevOps Agent Integration

## Overview

This guide explains how your ticket orchestrator routes requests to the AWS DevOps Agent and how to optimize investigations based on orchestrator classifications.

## Orchestrator Classification → DevOps Agent Mapping

Your orchestrator classifies tickets into categories and routes them appropriately. Here's how each category maps to DevOps Agent workflows:

### 1. **Incidents** → Deep Investigation (Backlog Task)
**Orchestrator Classification:**
- Keywords: "not working", "unreachable", "broken", "error", "down", "timeout", "failure"
- Confidence: Usually 0.6-0.8 (keyword mode) or 0.7-0.95 (Bedrock mode)

**DevOps Agent Action:**
```python
# When orchestrator classifies as "incident", route to investigation
AGENT_BACKEND = "agent_space"
MIN_INVESTIGATION_CONFIDENCE = 0.6

# Create backlog task for deep investigation
aws devops-agent create-backlog-task \
  --agent-space-id $DEVOPS_AGENT_SPACE_ID \
  --task-type INVESTIGATION \
  --title "[FROM TICKET] Service connectivity issue" \
  --priority HIGH \
  --description "Original ticket context from orchestrator: ..." \
  --region us-east-1
```

**Investigation Prompt Template:**
```
Investigate incident from ticket classification:
- Account: [FROM orchestrator accounts.csv lookup]
- Region: [FROM ticket or default]
- Issue Type: [orchestrator classification: network/connectivity/access]
- Original Description: [full ticket text]
- Affected Resources: [FROM orchestrator entity extraction]
- Time: [ticket creation time]
- Impact: [FROM ticket priority/severity]

Context from orchestrator:
- Classification confidence: [0.0-1.0]
- Detected entities: [accounts, resources, AD groups]
- Fast-path check: [AWS Health hit: yes/no]
```

### 2. **Network Changes** → Architecture Review (Chat)
**Orchestrator Classification:**
- Keywords: "security group", "firewall", "ports", "connectivity", "routing", "VPN", "Direct Connect"

**DevOps Agent Action:**
```
# Use chat for architecture understanding
Review network change request:
- Account: [ACCOUNT]
- Region: [REGION]
- Change Type: [security group/firewall/routing]
- Source: [FROM ticket]
- Destination: [FROM ticket]
- Justification: [FROM ticket]

Validate: check current configuration, identify conflicts, recommend approach
```

### 3. **Resource Access** → Access Review (Chat + Audit)
**Orchestrator Classification:**
- Keywords: "S3", "bucket", "topic", "queue", "access to", "permission"

**DevOps Agent Action:**
```
Review resource access request:
- Account: [ACCOUNT]
- Resource: [bucket/topic/queue name FROM orchestrator]
- Requester: [FROM ticket]
- Access Level: [read/write/admin]
- Justification: [FROM ticket]

Tasks:
1. Check current resource policy
2. Verify requester identity in accounts.csv
3. Identify security concerns
4. Recommend least-privilege policy
```

### 4. **Account Lifecycle** → Chat + Validation
**Orchestrator Classification:**
- Keywords: "new account", "close account", "rename account"

**DevOps Agent Action:**
```
Process account lifecycle request:
- Operation: [new/close/rename]
- Account Details: [FROM ticket]
- Validation: Check against accounts.csv in S3
- Compliance: Verify naming standards, tagging requirements

Provide: pre-flight checklist, potential issues, recommended actions
```

### 5. **Access Requests** → IAM Policy Review (Chat)
**Orchestrator Classification:**
- Keywords: "access to", "admin group", "permission set", "role", "AD group"

**DevOps Agent Action:**
```
Review IAM/AD access request:
- Target Identity: [AD group/IAM role FROM orchestrator extraction]
- User/Service: [requester]
- Requested Access: [permissions]
- Resources: [what they need to access]
- Environment: [dev/prod/test FROM orchestrator]

Tasks:
1. Review current permissions
2. Check for over-permissive access
3. Validate against least-privilege principles
4. Generate IAM policy/AD group membership change
```

### 6. **Read-Only Investigations** → Chat (Fast)
**Orchestrator Classification:**
- Keywords: "identify", "confirm", "list", "audit", "export", "check"

**DevOps Agent Action:**
```
Perform read-only audit:
- Account: [ACCOUNT]
- Region: [REGION]
- Audit Type: [FROM orchestrator classification]
- Scope: [resources/services/configurations]

Provide: current state, findings, no recommendations for changes
```

## Orchestrator Entity Extraction → DevOps Agent Context

The orchestrator extracts entities during ticket processing. Pass these to DevOps Agent:

### Extracted by Orchestrator
```python
# reply_extract.py output
{
    "pa_account_confirmed": "yes",        # → Pass to DevOps Agent as verified
    "environment": "prod",                 # → Use for investigation priority
    "ad_group": "aws-s3-admins",          # → Include in access review
    "resources": ["my-data-bucket"],      # → Target for investigation
    "accounts": ["123456789012"],         # → Account context
    "design": "Need read access for..."   # → Include as justification
}
```

### Transformed for DevOps Agent
```
Investigate based on ticket orchestrator classification:
- Verified Account: 123456789012 (PA confirmed: yes)
- Environment: production (high priority)
- Target Resources: S3 bucket my-data-bucket
- Access Request: AD group aws-s3-admins needs read access
- Justification: Need read access for compliance audit exports
- Classification Confidence: 0.75 (orchestrator keyword match)
```

## Integration Flow

```
┌─────────────────┐
│  ServiceNow     │
│  Ticket Created │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Orchestrator (classifier.py)   │
│  - Fast-path check              │
│  - Keyword/Bedrock classify     │
│  - Entity extraction            │
└────────┬────────────────────────┘
         │
         ├─────► classification = "incident"
         │       confidence > 0.6
         │       → Route to DevOps Agent Investigation
         │
         ├─────► classification = "resource_access"
         │       entities: ["bucket-name", "account-123"]
         │       → Route to DevOps Agent Access Review (Chat)
         │
         ├─────► classification = "network_change"
         │       → Route to DevOps Agent Architecture Review (Chat)
         │
         └─────► classification = "read_only"
                 → Route to DevOps Agent Audit (Chat)

┌──────────────────────────────────────┐
│  DevOps Agent Space                  │
│  - Receives context from orchestrator│
│  - Performs investigation/review     │
│  - Returns findings                  │
└────────┬─────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Orchestrator (reply_extract.py)    │
│  - Extract answers from findings    │
│  - Update ticket with resolution    │
└─────────────────────────────────────┘
```

## Orchestrator Config for DevOps Agent

### Production Configuration
```bash
# DevOps Agent backend (required for investigations)
export AGENT_BACKEND=agent_space

# Your DevOps Agent Space
export DEVOPS_AGENT_SPACE_ARN=arn:aws:devops-agent:us-east-1:123456789012:agentspace/abc123
export DEVOPS_AGENT_LOGIN_URL=https://console.aws.amazon.com/devops/home

# Investigation routing
export MIN_INVESTIGATION_CONFIDENCE=0.6  # Route to DevOps Agent if confidence >= 0.6
export DEVOPS_AGENT_MODEL_TIER=balanced  # balanced | performance | cost_optimized
export DEVOPS_AGENT_TASK_PRIORITY=MEDIUM # LOW | MEDIUM | HIGH | CRITICAL

# Classification mode
export BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0  # or empty for keyword mode

# Accounts lookup (for entity verification)
export ACCOUNTS_CSV_S3_BUCKET=runner_reports
export ACCOUNTS_CSV_S3_KEY=accounts.csv

# Storage
export DYNAMODB_TABLE_NAME=orch_runs
export DYNAMODB_REGION=us-east-1
```

### Testing Configuration (No AWS Costs)
```bash
# Test orchestrator classification without DevOps Agent
export AGENT_BACKEND=stub
unset BEDROCK_MODEL_ID  # Use deterministic keyword classification
# Don't set DYNAMODB_TABLE_NAME (uses in-memory store)

# Test classification accuracy
python orchestrator/classifier.py --test
```

## Runbooks Integration

Your orchestrator has runbook retrieval modes that can enhance DevOps Agent investigations:

### Keyword Mode (Default)
```bash
export RUNBOOK_RETRIEVAL_MODE=keyword
export RUNBOOK_CONFIG='{"mode": "keyword"}'
export RUNBOOK_MANIFEST_CONFIG=s3://runbooks-bucket/manifest.json
```

When orchestrator matches a runbook, include it in DevOps Agent context:
```
Investigate VPN connectivity issue:
- Account: 123456789012
- Region: us-east-1
- Issue: Both VPN tunnels down

Runbook matched by orchestrator:
- Title: VPN Tunnel Recovery
- Location: s3://runbooks-bucket/vpn-troubleshooting.md
- Match confidence: 0.85

Use this runbook to guide investigation steps.
```

### Bedrock Knowledge Base Mode (Advanced)
```bash
export RUNBOOK_RETRIEVAL_MODE=bedrock_kb
export BEDROCK_KB_ID=ABCDEF123456
export RUNBOOK_SELECTOR_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
```

Orchestrator retrieves relevant runbooks from Bedrock KB, passes to DevOps Agent.

## Confidence Thresholds

Map orchestrator confidence to DevOps Agent action:

| Confidence | Orchestrator Action | DevOps Agent Action |
|-----------|-------------------|-------------------|
| 0.9 - 1.0 | Auto-route to agent | Full investigation (5-8 min) |
| 0.7 - 0.9 | Route to agent | Standard investigation |
| 0.6 - 0.7 | Route if MIN_INVESTIGATION_CONFIDENCE met | Chat triage first, escalate if needed |
| 0.4 - 0.6 | Keyword match only | Chat for clarification |
| < 0.4 | Manual review | Don't auto-route |

### Configuration
```bash
# Only route to DevOps Agent if confidence >= 0.6
export MIN_INVESTIGATION_CONFIDENCE=0.6

# Second-pass for ambiguous tickets (0.55-0.7)
export SECOND_PASS_THRESHOLD=0.55
```

## Error Handling

### Bedrock "High Volume of Traffic" Errors

If orchestrator classification fails with traffic errors:

```python
# classifier.py automatically falls back to keyword_classify()
try:
    result = _bedrock_call(text, context_block)
except Exception as exc:
    # Falls back to keywords
    return keyword_classify(text)
```

**DevOps Agent Impact:**
- Lower confidence scores (0.4-0.7 vs 0.7-0.95)
- May require explicit classification in prompt

**Workaround:**
```
Investigate ticket (orchestrator keyword-classified as "incident"):
- Classification: incident (confidence: 0.65, mode: keyword)
- [rest of context]

Note: Classification used keyword mode due to Bedrock throttling
```

### DevOps Agent Investigation Failures

If DevOps Agent task fails:

```python
# Check task status
response = devops_agent.get_backlog_task(
    agentSpaceId=SPACE_ID,
    taskId=TASK_ID
)

if response['status'] == 'FAILED':
    # Fall back to orchestrator stub agent
    AGENT_BACKEND = 'stub'
    # Return deterministic response
```

## Accounts CSV Integration

Your orchestrator validates accounts against `s3://runner_reports/accounts.csv`:

### Upload to DevOps Agent S3 Reports

```bash
# Copy accounts.csv to DevOps Agent S3 bucket
aws s3 cp s3://runner_reports/accounts.csv s3://my-devops-reports/accounts/accounts.csv

# Configure DevOps Agent data source
aws devops-agent create-data-source \
  --agent-space-id $DEVOPS_AGENT_SPACE_ID \
  --data-source-type S3 \
  --configuration '{
    "bucketName": "my-devops-reports",
    "prefixes": ["accounts/"],
    "filePatterns": ["*.csv"],
    "syncSchedule": "rate(1 hour)"
  }' \
  --region us-east-1
```

### Reference in Investigations
```
Investigate account access issue:
- Account ID: 123456789012
- Account Name: [FROM accounts.csv]
- PA Account: [FROM orchestrator pa_account_confirmed]
- Owner: [FROM accounts.csv]

Validate: account exists in accounts.csv before provisioning access
```

## ServiceNow Integration

Pass ServiceNow ticket metadata to DevOps Agent:

```
Investigate incident from ServiceNow ticket:
- Ticket Number: INC0012345
- Priority: P2 (High)
- Created: 2024-03-15 14:30 UTC
- Reporter: john.smith@company.com
- Assignment Group: Cloud Operations

Original ticket text:
[FULL TICKET DESCRIPTION]

Orchestrator classification:
- Category: incident
- Confidence: 0.78
- Entities: account=123456789012, resource=my-vpc
- Environment: production
```

## Example Integration: VPN Connectivity

### 1. Ticket Created
```
Subject: VPN tunnels down - office cannot reach AWS
Description: Both VPN tunnels to us-east-1 are down. 
Office IP 203.0.113.50 cannot reach VPC 10.0.0.0/16.
VPN ID: vpn-0abc123
Started: 2 hours ago
```

### 2. Orchestrator Classification
```python
# classifier.py
classification = "incident"
confidence = 0.72  # keyword match: "down", "cannot reach"
entities = {
    "vpn_id": "vpn-0abc123",
    "network": "10.0.0.0/16",
    "external_ip": "203.0.113.50"
}
```

### 3. Route to DevOps Agent
```python
# Since confidence (0.72) > MIN_INVESTIGATION_CONFIDENCE (0.6)
if confidence >= MIN_INVESTIGATION_CONFIDENCE:
    # Create DevOps Agent investigation
    response = devops_agent.create_backlog_task(
        agentSpaceId=DEVOPS_AGENT_SPACE_ARN,
        taskType='INVESTIGATION',
        title='VPN tunnels down - office connectivity',
        priority='HIGH',
        description=f"""
Investigate VPN connectivity failure from orchestrator ticket:
- Account: [FROM accounts.csv]
- Region: us-east-1
- VPN Connection: vpn-0abc123
- Customer Gateway: 203.0.113.50
- Target VPC: 10.0.0.0/16
- Issue: Both tunnels down for 2 hours
- Impact: Office users cannot access AWS resources

Orchestrator context:
- Classification: incident (confidence: 0.72)
- Ticket: INC0012345
- Priority: P2

Focus on: tunnel status, IKE logs, recent configuration changes
        """
    )
```

### 4. DevOps Agent Investigation
Follows the investigation framework from `investigation-framework.md` and hybrid ops patterns from `hybrid-ops-prompts-guide.md`:
- Check VPN tunnel status
- Review CloudTrail for recent changes
- Check IKE/IPsec logs
- Verify customer gateway reachability
- Identify root cause

### 5. Extract Findings
```python
# reply_extract.py
# Extract findings from DevOps Agent response
findings = {
    "root_cause": "Customer gateway firewall blocking UDP 500/4500",
    "resolution": "Firewall rule added to allow IPsec traffic",
    "validation": "Both tunnels UP, connectivity restored"
}
```

### 6. Update ServiceNow Ticket
```
Resolution:
Root Cause: Customer gateway firewall configuration blocked IPsec traffic (UDP 500/4500) after security policy update.

Actions Taken:
1. Verified VPN tunnel status - both tunnels DOWN
2. Reviewed IKE logs - Phase 1 negotiation timeouts
3. Checked customer gateway - firewall blocking UDP 500/4500
4. Coordinated with network team to add firewall exception

Resolution: Firewall rules updated to allow IPsec. Both tunnels now UP.
Validation: Successful ping from office to VPC resources.

Investigation Time: 12 minutes
Downtime: 2 hours 18 minutes
```

## Best Practices

### 1. Pass Full Context
Always include orchestrator classification, confidence, and entities in DevOps Agent prompts:
```
✅ GOOD: "Investigate incident (orchestrator confidence: 0.78, entities: vpn-123, account-456)"
❌ BAD: "Investigate VPN issue"
```

### 2. Use Confidence for Routing
- High confidence (>0.7): Direct to investigation
- Medium (0.6-0.7): Start with chat, escalate if needed
- Low (<0.6): Manual review before routing

### 3. Sync Runbooks
Keep runbooks in both locations:
- Orchestrator: `s3://runbooks-bucket/` for routing
- DevOps Agent: `s3://my-devops-reports/runbooks/` for investigation

### 4. Update accounts.csv
Single source of truth for account validation:
- Orchestrator reads from: `s3://runner_reports/accounts.csv`
- DevOps Agent references same data via S3 data source

### 5. Monitor Classification Accuracy
Track orchestrator confidence scores and investigation outcomes:
- If investigations frequently find "incorrect classification", tune orchestrator keywords
- If low confidence (<0.6) tickets often need investigation, lower MIN_INVESTIGATION_CONFIDENCE

## Troubleshooting

### Orchestrator Routes to Wrong Agent Action
**Symptom:** Incident classified as "read_only", should be "incident"

**Fix:** Add keywords to `classifier.py`:
```python
# Add to INCIDENT_KEYWORDS
"vpn down", "cannot connect", "connection refused"
```

### DevOps Agent Missing Orchestrator Context
**Symptom:** Agent asks for account/region already in orchestrator extraction

**Fix:** Include orchestrator entities explicitly:
```python
description = f"""
Account: {entities.get('account', 'unknown')}
Region: {entities.get('region', 'us-east-1')}
VPN ID: {entities.get('vpn_id', 'unknown')}
...
"""
```

### Low Confidence Classifications
**Symptom:** Orchestrator confidence < 0.6, tickets not routed

**Options:**
1. Lower `MIN_INVESTIGATION_CONFIDENCE` to 0.5
2. Enable Bedrock mode: `export BEDROCK_MODEL_ID=anthropic.claude-3-haiku...`
3. Add keywords to classifier.py for your common patterns
