# S3 Reports Integration for DevOps Agent

## Overview

The DevOps Agent can access and analyze reports stored in S3 buckets to enhance investigations with:
- Historical incident reports
- Performance baselines
- Architecture diagrams
- Runbook documentation
- Cost optimization reports
- Security audit findings
- Compliance reports

## S3 Bucket Structure (Recommended)

```
s3://my-devops-reports/
├── incidents/
│   ├── 2024-01-15-vpn-tunnel-down.md
│   ├── 2024-02-03-certificate-expired.md
│   └── 2024-03-10-backup-failure.md
├── runbooks/
│   ├── vpn-troubleshooting.md
│   ├── certificate-renewal.md
│   ├── backup-verification.md
│   └── security-group-access.md
├── architecture/
│   ├── service-topology.json
│   ├── api-gateway-design.md
│   └── database-schema.png
├── baselines/
│   ├── backup-requirements.json
│   ├── ec2-inventory.json
│   └── network-topology.json
├── accounts/
│   └── accounts.csv
├── cost-reports/
│   ├── 2024-Q1-cost-analysis.pdf
│   └── ec2-rightsizing-recommendations.md
└── security/
    ├── iam-audit-2024-03.md
    └── security-group-review.json
```

## Setting Up S3 Access

### 1. Grant DevOps Agent Permissions

Add to the agent's IAM role policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-devops-reports",
        "arn:aws:s3:::my-devops-reports/*"
      ]
    }
  ]
}
```

### 2. Configure Agent Space Data Sources

Via AWS Console:
1. Go to DevOps Agent → Your Agent Space
2. Navigate to **Data Sources** or **Knowledge Sources**
3. Click **Add Data Source**
4. Select **S3**
5. Configure:
   - Bucket: `my-devops-reports`
   - Prefix: (optional) `incidents/`, `runbooks/`
   - File types: `.md`, `.json`, `.txt`, `.csv`
   - Sync frequency: Real-time or Scheduled

Via AWS CLI:
```bash
aws devops-agent create-data-source \
  --agent-space-id $AGENT_SPACE_ID \
  --data-source-type S3 \
  --configuration '{
    "bucketName": "my-devops-reports",
    "prefixes": ["incidents/", "runbooks/", "baselines/"],
    "filePatterns": ["*.md", "*.json", "*.txt", "*.csv"],
    "syncSchedule": "rate(1 hour)"
  }' \
  --region us-east-1
```

## Report Formats

### Incident Reports (Markdown)

```markdown
# Incident Report: API Gateway Timeout

**Date**: 2024-03-10
**Duration**: 45 minutes
**Severity**: SEV2
**Impact**: 15% error rate on payment API

## Timeline
- 14:00 UTC: Alerts triggered for high latency
- 14:15 UTC: Error rate increased to 15%
- 14:30 UTC: Root cause identified (DynamoDB throttling)
- 14:45 UTC: Mitigation applied (increased capacity)

## Root Cause
DynamoDB table "PaymentSessions" hit provisioned capacity limit due to:
- Marketing campaign drove 3x normal traffic
- Table configured for 100 WCU (insufficient)
- No auto-scaling enabled

## Resolution
- Immediate: Increased WCU to 500
- Long-term: Enabled auto-scaling (100-1000 WCU)

## Lessons Learned
- Monitor campaign schedules for traffic spikes
- Enable auto-scaling on all production tables
- Set up predictive alerts for capacity

## Related Resources
- Lambda: payment-processor (us-east-1)
- DynamoDB: PaymentSessions table
- CloudWatch Alarm: PaymentTableThrottling
```

### Performance Baselines (JSON)

```json
{
  "service": "payment-processor",
  "type": "lambda",
  "region": "us-east-1",
  "baseline_period": "2024-01-01 to 2024-03-01",
  "metrics": {
    "duration_p50_ms": 150,
    "duration_p99_ms": 450,
    "error_rate_percent": 0.05,
    "cold_start_rate_percent": 2.0,
    "concurrent_executions_avg": 25,
    "concurrent_executions_max": 180,
    "invocations_per_minute_avg": 500,
    "invocations_per_minute_peak": 2000
  },
  "thresholds": {
    "duration_p99_alert_ms": 800,
    "error_rate_alert_percent": 1.0,
    "concurrent_executions_limit": 200
  },
  "dependencies": [
    "dynamodb:PaymentSessions",
    "dynamodb:Users",
    "apigateway:payment-api"
  ]
}
```

### Runbooks (Markdown)

```markdown
# Runbook: Lambda Timeout Troubleshooting

## When to Use
- Lambda functions timing out at configured limit
- Increased execution duration beyond baseline
- Cold start issues affecting performance

## Investigation Steps

### 1. Check Current Metrics (2 min)
```bash
# Get P99 duration for past hour
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=FUNCTION_NAME \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Maximum
```

### 2. Identify Cause (5 min)
- Cold starts: Check Initialization Duration metric
- Downstream latency: Review X-Ray traces
- Memory pressure: Check memory usage vs configured memory
- Timeout too low: Compare duration to timeout setting

### 3. Quick Mitigations
- **Cold starts**: Increase memory or enable provisioned concurrency
- **Downstream**: Implement retries with exponential backoff
- **Memory**: Increase memory configuration
- **Timeout**: Increase timeout limit (if appropriate)

### 4. Long-term Fixes
- Optimize package size (reduce cold start)
- Cache downstream API responses
- Use connection pooling for databases
- Implement async processing for long tasks

## Common Patterns

### Pattern: Third-party API Timeout
**Symptoms**: Consistent timeouts around same duration
**Root Cause**: Downstream API not responding
**Fix**: Add timeout to HTTP client, implement circuit breaker

### Pattern: Database Connection Exhaustion
**Symptoms**: Random timeouts, errors about connections
**Root Cause**: Connection pool exhausted or not reusing connections
**Fix**: Implement connection pooling, reuse connections across invocations

## Related Incidents
- 2024-02-03: Lambda timeout due to DynamoDB throttling
- 2024-01-15: Cold start spike after deployment
```

## Using Reports in Investigations

### Referencing Reports Explicitly

```
Investigate Lambda timeout in payment-processor:
- Account: 123456789012
- Region: us-east-1
- Time: Past 2 hours
- Symptom: P99 duration 8000ms (baseline: 450ms)

Check S3 reports:
- baselines/lambda-performance-baseline.json (for baseline comparison)
- incidents/2024-02-03-lambda-timeout.md (similar past incident)
- runbooks/lambda-troubleshooting.md (investigation steps)
```

### Asking Agent to Find Relevant Reports

```
What historical incidents involving Lambda timeouts do you have in S3?
Compare current payment-processor Lambda performance to baseline in S3.
Show me the runbook for DynamoDB throttling investigations.
```

### Using Reports for Context

```
Investigate RDS performance degradation:
- Account: 987654321098
- Region: us-east-1
- Database: prod-postgres-01
- Time: Past hour

Reference architecture/database-schema.png and 
baselines/rds-performance-baseline.json to understand 
expected behavior and current architecture.
```

## Report Types and Use Cases

| Report Type | Format | Use Case | Example |
|-------------|--------|----------|---------|
| Incident Reports | Markdown | Learn from past issues | Lambda timeout patterns |
| Performance Baselines | JSON | Detect anomalies | Compare current vs baseline |
| Runbooks | Markdown | Investigation procedures | Step-by-step troubleshooting |
| Architecture Diagrams | PNG/JSON | Understand topology | Service dependencies |
| Cost Reports | PDF/CSV | Cost optimization context | Identify expensive resources |
| Security Audits | Markdown/JSON | Security investigations | IAM permission reviews |
| Configuration Snapshots | JSON/YAML | Compare configurations | Before/after deployments |

## Keeping Reports Updated

### Automated Report Generation

Use Lambda functions or scheduled tasks to generate reports:

```python
# Example: Generate weekly baseline report
import boto3
import json
from datetime import datetime, timedelta

cloudwatch = boto3.client('cloudwatch')
s3 = boto3.client('s3')

def generate_lambda_baseline(function_name):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)
    
    # Fetch metrics
    duration_p99 = cloudwatch.get_metric_statistics(
        Namespace='AWS/Lambda',
        MetricName='Duration',
        Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=['Maximum']
    )
    
    baseline = {
        'service': function_name,
        'type': 'lambda',
        'baseline_period': f"{start_time.date()} to {end_time.date()}",
        'metrics': {
            'duration_p99_ms': max([dp['Maximum'] for dp in duration_p99['Datapoints']])
        }
    }
    
    # Upload to S3
    s3.put_object(
        Bucket='my-devops-reports',
        Key=f"baselines/{function_name}-baseline.json",
        Body=json.dumps(baseline, indent=2)
    )
```

### Post-Incident Report Template

After resolving an incident, create a report:

```bash
# Script to create incident report template
cat > /tmp/incident-report.md <<EOF
# Incident Report: [TITLE]

**Date**: $(date +%Y-%m-%d)
**Duration**: [DURATION]
**Severity**: [SEV1/SEV2/SEV3]
**Impact**: [DESCRIPTION]

## Timeline
- [TIME]: [EVENT]

## Root Cause
[DESCRIPTION]

## Resolution
- Immediate: [ACTION]
- Long-term: [ACTION]

## Lessons Learned
- [LESSON]

## Related Resources
- [SERVICE]: [IDENTIFIER]
EOF

# Upload to S3
aws s3 cp /tmp/incident-report.md s3://my-devops-reports/incidents/$(date +%Y-%m-%d)-incident.md
```

## Best Practices

1. **Consistent Naming**: Use date prefixes (YYYY-MM-DD) for chronological sorting
2. **Structured Formats**: Use JSON for metrics, Markdown for narratives
3. **Cross-References**: Link related reports (incidents → runbooks)
4. **Regular Updates**: Automate baseline generation weekly/monthly
5. **Access Control**: Use S3 bucket policies to restrict write access
6. **Versioning**: Enable S3 versioning to track report changes
7. **Metadata Tags**: Tag objects with category, service, severity
8. **Lifecycle Policies**: Archive old reports to Glacier after 1 year

## Verification

After setup, test S3 integration:

```
# Test 1: Check available reports
List all incident reports you have access to in S3

# Test 2: Reference specific report
Using the Lambda timeout runbook in S3, investigate 
timeout issues in payment-processor function

# Test 3: Compare to baseline
Compare current payment-processor Lambda performance 
to the baseline report in S3 baselines/
```

## Troubleshooting

**Agent not finding S3 reports:**
- Verify S3 bucket permissions in IAM role
- Check data source configuration in Agent Space
- Ensure file formats are supported (.md, .json, .txt, .csv)
- Verify bucket name and prefix are correct

**Reports not being referenced:**
- Be explicit in prompts: "Check S3 reports for..."
- Use specific file names or patterns
- Ensure sync schedule has completed
- Check CloudWatch Logs for data source sync errors

**Stale report data:**
- Check sync schedule frequency
- Manually trigger sync in console
- Verify S3 object timestamps
- Check for sync errors in Agent Space logs
