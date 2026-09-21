# AWS DevOps Investigation Framework

## Key Context for Effective Investigations

For best results, investigations should include:
- **AWS Account ID**: Specific account being investigated (if not provided, may default to associated account)
- **Region(s)**: Which AWS region(s) are affected (if unclear, ask before proceeding)
- **Environment**: Production, staging, or development (helps prioritize and scope)
- **Time Range**: When issue started and duration (critical for correlating events)
- **Service Context**: Primary service and related services (guides tool selection)
- **Resource Identifiers**: Specific ARNs, instance IDs, function names (enables precise analysis)
- **Symptoms**: Observable problems (latency, errors, cost spikes) with specific metrics when available
- **Impact**: User-facing, internal, data loss, or financial (helps determine investigation depth)

If critical information is missing, ask clarifying questions before starting detailed analysis.

## Investigation Phases

### Phase 1: Triage (5 minutes)
1. Identify primary symptom and affected resources
2. Check CloudWatch Alarms for active alerts
3. Review recent CloudTrail events for changes
4. Determine time range and scope
5. Check S3 reports for similar historical incidents and relevant runbooks

### Phase 2: Deep Dive (15-30 minutes)
1. Query CloudWatch Logs Insights for error patterns
2. Analyze metrics trends and anomalies
3. Review Application Signals traces (if available)
4. Map service topology and dependencies
5. Check security or configuration events

### Phase 3: Root Cause Analysis (10-20 minutes)
1. Correlate findings across logs, metrics, traces
2. Identify chain of causation
3. Determine if code, configuration, capacity, or external
4. Document timeline of events

### Phase 4: Remediation
1. Propose immediate mitigations
2. Suggest long-term fixes
3. Recommend preventive measures

## Investigation Patterns

### Connectivity Issue Investigation (AWS ↔ On-Prem)
1. Check VPN/Direct Connect tunnel status and uptime
2. Review recent configuration changes (both AWS and on-prem)
3. Verify route tables, security groups, and NACLs
4. Check BGP session status and route propagation
5. Review IKE/IPsec logs for VPN phase failures
6. Test connectivity at different layers (ping, port, application)

### Certificate Issue Investigation
1. Check certificate expiration dates and status
2. Verify DNS validation records (CNAME for ACM)
3. Review certificate usage (ALB, CloudFront, API Gateway)
4. Check certificate chain and intermediate certificates
5. Verify ACM auto-renewal settings and failures
6. Review CloudTrail for certificate-related API calls

### Access Issue Investigation
1. Identify the exact error message and AWS service
2. Review IAM policies, bucket policies, and resource policies
3. Check security group and NACL rules
4. Verify source IP/CIDR is allowed
5. Check for explicit deny statements overriding allows
6. Review VPC endpoints and route tables for private access

### Backup/Restore Investigation
1. Check AWS Backup job status and history
2. Verify backup vault permissions and encryption keys
3. Review service role IAM permissions
4. Check backup plan resource selection (tags, IDs)
5. Verify snapshot retention and lifecycle policies
6. Review available recovery points and timestamps

### High Latency Investigation
1. Check Application Signals for slow traces
2. Identify bottleneck services/operations
3. Review logs for slow requests
4. Check metrics: CPU, memory, network, DB connections
5. Review topology for cascading delays

### Error Rate Spike Investigation
1. Query logs for error patterns and stack traces
2. Check CloudTrail for recent deployments/changes
3. Review Application Signals for fault patterns
4. Analyze metrics around error spike time
5. Check dependency health

### Security Audit Investigation
1. Query CloudTrail for security-relevant events
2. Check for unauthorized access attempts
3. Review IAM changes and permission grants
4. Examine network access patterns
5. Identify security best practice violations

## Tool Selection Guide

| Investigation Type | Primary Data Sources | Key Metrics |
|-------------------|---------------------|-------------|
| Connectivity (VPN/DX) | VPN tunnel status, CloudWatch Logs | Tunnel state, IKE phase, BGP status |
| Certificate Issues | ACM, CloudTrail | Expiration date, validation status |
| Access Issues | CloudTrail, VPC Flow Logs | Access denied events, rejected packets |
| Backup/Restore | AWS Backup, Snapshots | Job status, retention, recovery points |
| Latency/Performance | Application Signals, CloudWatch Metrics | P50/P99 latency, duration |
| Errors/Failures | CloudWatch Logs, Application Signals | Error rate, fault rate |
| Security Audit | CloudTrail | Failed auth, permission changes |
| Network Routing | VPC Flow Logs, Route Tables | Packet flow, rejected connections |

## Multi-Signal Analysis Approach

Always combine:
- **Logs**: Error messages, stack traces, patterns
- **Metrics**: Resource utilization, performance trends
- **Traces**: Request flows, bottlenecks, dependencies
- **Events**: Deployments, configuration changes, security events
- **Historical Reports**: Past incidents, baselines, runbooks from S3

## Context Preservation Guidelines

When analyzing complex issues:
1. Reference previous findings explicitly
2. Maintain key identifiers (account, region, resources)
3. Build on discovered context incrementally
4. Summarize progress before next investigation phase

## Common Root Causes by Symptom

### High Latency
- Database connection pool exhaustion
- Cold starts (Lambda)
- Downstream service degradation
- Network saturation
- Memory pressure causing GC pauses
- Missing database indexes

### Error Spikes
- Recent deployments with bugs
- Dependency failures
- Rate limiting/throttling
- Configuration errors
- Authentication/authorization failures
- Resource exhaustion (memory, connections)

### Cost Increases
- Unintended resource scaling
- Data transfer spikes
- New resource creation
- Inefficient queries
- Over-provisioned capacity
- Missing auto-scaling policies

### Availability Issues
- Health check failures
- Resource limits exceeded
- Security group misconfigurations
- DNS resolution failures
- Certificate expiration
- Service quota exhaustion

## Best Practices

1. **Provide Complete Context Upfront**: Include account ID, region, resource identifiers, time range, and symptoms
2. **Reference Historical Data**: Check S3 reports for performance baselines, similar past incidents, and relevant runbooks
3. **Start Broad, Then Narrow**: Begin with high-level metrics, drill into specifics
4. **Time Correlation**: Align findings with incident timeline
5. **Verify Assumptions**: Don't jump to conclusions without data
6. **Document Context**: State investigation hypotheses clearly
7. **Check Recent Changes**: Always review deployments and config updates
8. **Consider Dependencies**: Issues often originate in upstream/downstream services
9. **Validate Remediation**: Verify fixes with metrics/logs post-implementation

## Anti-Patterns to Avoid

- Investigating without clear hypothesis
- Ignoring related services and dependencies
- Forgetting to check for recent changes
- Analyzing wrong time range or region
- Relying on single data source (ignoring S3 historical reports)
- Not considering external factors (AWS service issues, third-party APIs)
- Not comparing current behavior to baselines
