# Upload Instructions - DevOps Agent Knowledge Base

## Files to Upload

Upload these 4 files to your DevOps Agent Space:

1. ✅ **investigation-framework.md** - Investigation methodology and patterns
2. ✅ **hybrid-ops-prompts-guide.md** - YOUR use cases (VPN, certs, access, backups, EC2 lookup)
3. ✅ **s3-reports-integration.md** - S3 reports for accounts.csv, backups, incidents
4. ✅ **orchestrator-integration.md** - Ticket routing from your orchestrator

## Quick Upload (AWS CLI)

```bash
cd devops-agent-knowledge

# Set your Agent Space ID
export AGENT_SPACE_ID="your-agent-space-id"
export REGION="us-east-1"

# Upload all 4 files
aws devops-agent upload-knowledge-document \
  --agent-space-id $AGENT_SPACE_ID \
  --file investigation-framework.md \
  --region $REGION

aws devops-agent upload-knowledge-document \
  --agent-space-id $AGENT_SPACE_ID \
  --file hybrid-ops-prompts-guide.md \
  --region $REGION

aws devops-agent upload-knowledge-document \
  --agent-space-id $AGENT_SPACE_ID \
  --file s3-reports-integration.md \
  --region $REGION

aws devops-agent upload-knowledge-document \
  --agent-space-id $AGENT_SPACE_ID \
  --file orchestrator-integration.md \
  --region $REGION
```

## Via AWS Console

1. Go to **AWS Console → DevOps Agent**
2. Select your **Agent Space**
3. Navigate to **Knowledge** or **Documents** section
4. Click **Upload Document**
5. Upload each file:
   - `investigation-framework.md`
   - `hybrid-ops-prompts-guide.md`
   - `s3-reports-integration.md`
   - `orchestrator-integration.md`
6. Add tags: `investigation`, `hybrid-ops`, `orchestrator`, `s3-reports`

## S3 Reports Setup (Required for Your Use Cases)

### 1. Create S3 Bucket Structure

```bash
# Create bucket
aws s3 mb s3://my-devops-reports

# Create folders
aws s3api put-object --bucket my-devops-reports --key accounts/
aws s3api put-object --bucket my-devops-reports --key incidents/
aws s3api put-object --bucket my-devops-reports --key baselines/
aws s3api put-object --bucket my-devops-reports --key runbooks/
```

### 2. Copy accounts.csv from Orchestrator

```bash
# Copy from orchestrator bucket to DevOps Agent bucket
aws s3 cp s3://runner_reports/accounts.csv s3://my-devops-reports/accounts/accounts.csv
```

### 3. Grant DevOps Agent Access

Add to agent's IAM role:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::my-devops-reports",
    "arn:aws:s3:::my-devops-reports/*"
  ]
}
```

### 4. Configure S3 Data Source

```bash
aws devops-agent create-data-source \
  --agent-space-id $AGENT_SPACE_ID \
  --data-source-type S3 \
  --configuration '{
    "bucketName": "my-devops-reports",
    "prefixes": ["accounts/", "incidents/", "baselines/", "runbooks/"],
    "filePatterns": ["*.md", "*.json", "*.csv", "*.txt"],
    "syncSchedule": "rate(1 hour)"
  }' \
  --region $REGION
```

## Test After Upload

### Test 1: Account Lookup
```
Find account owner for account ID 123456789012.
Check s3://my-devops-reports/accounts/accounts.csv
```

Expected: Agent accesses accounts.csv and returns owner information

### Test 2: EC2 by IP
```
Find EC2 instance with private IP 10.0.50.25 in account 123456789012, us-east-1
```

Expected: Agent searches EC2 and returns instance details

### Test 3: Backup Validation
```
Verify backup plan for RDS instance db-prod-01 in account 123456789012.
Check if restore points exist and reference S3 reports for last restore test.
```

Expected: Agent checks AWS Backup and references S3 reports

### Test 4: VPN Investigation
```
Investigate VPN connectivity issue using hybrid ops guide:
- VPN ID: vpn-0abc123
- Account: 123456789012
- Both tunnels down
```

Expected: Agent follows VPN troubleshooting from hybrid-ops-prompts-guide.md

## Orchestrator Configuration

Update your orchestrator environment:

```bash
# Route to DevOps Agent
export AGENT_BACKEND=agent_space
export DEVOPS_AGENT_SPACE_ARN=arn:aws:devops-agent:us-east-1:123456789012:agentspace/abc123
export MIN_INVESTIGATION_CONFIDENCE=0.6

# Accounts validation (shared with DevOps Agent)
export ACCOUNTS_CSV_S3_BUCKET=runner_reports
export ACCOUNTS_CSV_S3_KEY=accounts.csv
```

## Verification Checklist

- [ ] 4 knowledge documents uploaded to Agent Space
- [ ] S3 bucket created: `my-devops-reports`
- [ ] accounts.csv copied to S3
- [ ] IAM permissions granted to agent
- [ ] S3 data source configured and synced
- [ ] Test 1 passed: account lookup works
- [ ] Test 2 passed: EC2 by IP works
- [ ] Test 3 passed: backup validation works
- [ ] Test 4 passed: VPN investigation follows guide
- [ ] Orchestrator AGENT_BACKEND=agent_space configured

## What You Get

### Your Real Scenarios Covered
✅ Account owner lookup for approvals (from accounts.csv in S3)  
✅ EC2 instance search by IP address  
✅ Backup plan and checkpoint validation  
✅ VPN/Direct Connect troubleshooting  
✅ Certificate expiration/renewal  
✅ Access provisioning (IAM, Security Groups, S3)  
✅ S3 access issues  
✅ Network routing problems  

### Orchestrator Integration
✅ Ticket classification → investigation routing  
✅ Entity extraction passed to agent  
✅ Confidence thresholds for routing  
✅ Context preservation across systems  

### Historical Context
✅ Past incidents from S3 reports  
✅ Backup compliance tracking  
✅ Runbooks for common issues  
✅ Performance baselines  

## Support

- **Hybrid ops scenarios**: See `hybrid-ops-prompts-guide.md`
- **S3 reports setup**: See `s3-reports-integration.md`
- **Orchestrator routing**: See `orchestrator-integration.md`
- **Investigation methodology**: See `investigation-framework.md`

You're ready! Upload the 4 files and configure S3 reports. 🚀
