# Hybrid Infrastructure & Operational Access - Investigation Guide

## Your Common Scenarios

Based on typical hybrid infrastructure and operational support cases:
1. AWS ↔ On-Prem Connectivity Issues
2. Certificate Expiration/Renewal
3. Access Provisioning (IAM, Security Groups, Network ACLs)
4. Backup and Restore Operations
5. S3 Access Issues
6. VPN/Direct Connect Problems
7. Network Routing Issues
8. Database Connection Failures (on-prem to AWS)

---

## 1. AWS ↔ On-Prem Connectivity Issues

### Template
```
Investigate connectivity problem between AWS and on-premises:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- AWS Side: [VPC_ID, Subnet, Security Group, Transit Gateway, etc.]
- On-Prem Side: [Data Center, IP Range, Firewall]
- Connection Type: [VPN/Direct Connect/VPN over Direct Connect]
- Connection ID: [VPN_ID or DX_ID]
- Symptom: [Cannot reach, intermittent, slow, packet loss]
- Affected Services: [What can't communicate]
- Time: [When started]
- Impact: [Applications/users affected]

Test Results (if available):
- Ping: [result]
- Traceroute: [result]
- Port connectivity: [result]
```

### Example: VPN Tunnel Down
```
Investigate VPN connectivity failure:
- Account: 123456789012
- Region: us-east-1
- AWS Side: VPC vpc-abc123, Virtual Private Gateway vgw-xyz789
- On-Prem Side: Office HQ, 192.168.1.0/24
- Connection Type: Site-to-Site VPN
- Connection ID: vpn-connection-12345
- Symptom: Both tunnels down for 2 hours
- Affected Services: Office cannot access AWS RDS database
- Time: Started today at 10:00 UTC
- Impact: 50 office users cannot access CRM application

Focus on: tunnel status, IKE phase 1/2 failures, recent AWS or on-prem config changes
```

### Example: Direct Connect Flapping
```
Investigate Direct Connect instability:
- Account: 987654321098
- Region: us-west-2
- AWS Side: DX connection dxcon-abc123, Virtual Interface dxvif-xyz789
- On-Prem Side: Equinix SV5, VLAN 100
- Connection Type: Dedicated 10Gbps Direct Connect
- Symptom: Connection flapping every 15-20 minutes
- Affected Services: Data replication from on-prem PostgreSQL to AWS RDS
- Time: Started 6 hours ago
- Impact: Data sync delays, application warnings

Focus on: BGP session stability, CRC errors, physical layer issues, recent maintenance
```

### Example: Transit Gateway Routing
```
Investigate routing issue through Transit Gateway:
- Account: 555666777888
- Region: eu-central-1
- AWS Side: Transit Gateway tgw-123abc, Attachment tgw-attach-456def
- On-Prem Side: Munich office 10.50.0.0/16
- Connection Type: VPN to Transit Gateway
- Symptom: Traffic from VPC-A can reach on-prem, but VPC-B cannot
- Affected Services: VPC-B EC2 instances cannot reach on-prem file server
- Time: Started after Transit Gateway route table update yesterday
- Impact: CI/CD pipeline blocked

Focus on: TGW route tables, VPC route tables, propagation settings, route priorities
```

---

## 2. Certificate Expiration/Renewal

### Template
```
Investigate certificate issue:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- Certificate Type: [ACM, IAM Server Certificate, Self-signed, Third-party]
- Certificate ID/ARN: [CERTIFICATE_ARN or Name]
- Domain(s): [DOMAINS]
- Used By: [ALB, CloudFront, API Gateway, etc.]
- Issue: [Expired, Expiring soon, Not trusted, Mismatch]
- Time Discovered: [WHEN]
- Impact: [Browser warnings, connection failures]

Current State:
- Expiration Date: [DATE if known]
- Status: [ISSUED, EXPIRED, PENDING_VALIDATION]
```

### Example: ALB Certificate Expired
```
Investigate certificate expiration:
- Account: 123456789012
- Region: us-east-1
- Certificate Type: ACM Certificate
- Certificate ARN: arn:aws:acm:us-east-1:123456789012:certificate/abc-123-def
- Domain: api.company.com, *.company.com
- Used By: Application Load Balancer prod-api-alb
- Issue: Certificate expired yesterday
- Time Discovered: This morning, users reporting SSL errors
- Impact: All API traffic showing "Your connection is not private"

Focus on: renewal status, validation records, ACM auto-renewal settings, DNS configuration
```

### Example: Certificate Renewal Failed
```
Investigate ACM certificate renewal failure:
- Account: 987654321098
- Region: eu-west-1
- Certificate ARN: arn:aws:acm:eu-west-1:987654321098:certificate/xyz-789
- Domain: www.portal.company.com
- Used By: CloudFront distribution E123ABC456
- Issue: Auto-renewal failed 5 days ago, expires in 3 days
- Time Discovered: Received AWS health notification today
- Impact: Site will go offline in 3 days if not resolved

Focus on: DNS validation CNAME records, domain ownership verification, Route53 configuration
```

### Example: Certificate for On-Prem Integration
```
Investigate certificate trust issue:
- Account: 111222333444
- Region: us-west-2
- Certificate Type: IAM Server Certificate (uploaded from on-prem CA)
- Certificate Name: onprem-ca-2024
- Used By: VPN connections to on-prem
- Issue: AWS services not trusting on-prem issued certificates
- Time: Started after on-prem CA renewed root certificate
- Impact: API Gateway cannot validate webhooks from on-prem systems

Focus on: certificate chain, intermediate certificates, CA bundle configuration
```

---

## 3. Access Provisioning Requests

### Template
```
Provision/investigate access issue:
- Account: [ACCOUNT_ID]
- Region: [REGION or "global" for IAM]
- Request Type: [IAM User, IAM Role, Security Group, Network ACL, S3 Bucket Policy]
- User/Service: [WHO needs access]
- Resource: [WHAT they need to access]
- Access Level: [Read, Write, Admin, specific permissions]
- Source: [WHERE they're accessing from - IP, VPC, on-prem]
- Reason: [WHY they need access]
- Duration: [Permanent, Temporary until DATE]

Current Issue (if troubleshooting):
- Error Message: [EXACT ERROR]
- What they tried: [ACTIONS ATTEMPTED]
```

### Example: New IAM User Access
```
Provision IAM access for new team member:
- Account: 123456789012
- Region: global
- Request Type: IAM User with MFA
- User: john.smith@company.com
- Resources Needed: 
  - Read access to S3 bucket prod-backups
  - Describe EC2 instances in us-east-1
  - CloudWatch Logs read access for application logs
- Access Level: Read-only
- Source: Office IP 203.0.113.50 and VPN range 10.20.0.0/16
- Reason: New SRE team member needs monitoring access
- Duration: Permanent

Create: IAM user, assign to SRE-ReadOnly group, enable MFA requirement
```

### Example: Security Group Access Request
```
Investigate security group blocking traffic:
- Account: 987654321098
- Region: us-east-1
- Request Type: Security Group inbound rule
- Source: On-prem application server 10.50.30.15
- Target: RDS PostgreSQL instance prod-db-01 (10.0.1.50:5432)
- Current Issue: Connection timeout
- Time: Started after security group audit cleanup yesterday
- Impact: On-prem application cannot connect to database

Focus on: Security group sg-abc123 rules, NACLs, route tables, VPN tunnel status
```

### Example: S3 Cross-Account Access
```
Provision S3 cross-account access:
- Accounts: Source 111222333444, Destination 555666777888
- Region: us-west-2
- Request Type: S3 Bucket Policy + IAM Role
- Source: Partner company AWS account
- Resource: S3 bucket prod-data-share
- Access Level: Read-only to /reports/ prefix
- Reason: Partner needs monthly reports for compliance
- Duration: Permanent, review quarterly

Setup: Bucket policy with account condition, IAM role with assume role policy
```

---

## 4. Backup and Restore Operations

### Template
```
Backup/restore operation:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- Operation: [Backup, Restore, Verify]
- Source: [What's being backed up or restore source]
- Destination: [Where backup goes or restore target]
- Backup Type: [Full, Incremental, Snapshot]
- Schedule: [Ad-hoc, Daily, Weekly]
- Issue (if troubleshooting): [Failure reason, slow, incomplete]
- Time: [When]
- Impact: [RPO/RTO concerns]
```

### Example: RDS Restore Request
```
Restore RDS database from backup:
- Account: 123456789012
- Region: us-east-1
- Operation: Point-in-time restore
- Source: Production RDS instance prod-postgres-01
- Target: New instance dev-postgres-restored
- Restore Point: Yesterday 15:00 UTC (before bad migration)
- Reason: Need to recover data from before failed schema change
- Impact: Development team blocked for 2 hours
- Requirements: Restore to separate instance, not overwrite production

Focus on: available snapshots, automated backup retention, restore time estimate
```

### Example: EC2 Backup Failure
```
Investigate EC2 backup failure:
- Account: 987654321098
- Region: eu-west-1
- Operation: AWS Backup job
- Source: EC2 instances with tag backup:daily
- Destination: Backup vault prod-backups
- Backup Type: EBS snapshot via AWS Backup
- Issue: Backups failing with "insufficient permissions" for 3 days
- Time: Started after IAM policy update last Friday
- Impact: No backups for critical application servers, exceeding RPO

Focus on: AWS Backup service role permissions, backup vault access policy, EC2 instance IAM
```

### Example: On-Prem to S3 Backup Validation
```
Verify on-premises backup to S3:
- Account: 111222333444
- Region: us-west-2
- Operation: Verify backup integrity
- Source: On-prem file server (10TB data)
- Destination: S3 bucket onprem-backups/fileserver/
- Backup Type: Incremental using AWS DataSync
- Issue: Backup completed but need to verify restore capability
- Last Backup: Completed 2 hours ago
- Purpose: Quarterly DR drill

Tasks: Check S3 object count, verify checksums, test restore sample files
```

---

## 5. S3 Access Issues

### Template
```
Investigate S3 access problem:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- Bucket: [BUCKET_NAME]
- User/Role: [WHO is accessing]
- Operation: [GetObject, PutObject, ListBucket, etc.]
- Access Method: [Console, CLI, SDK, Application]
- Error: [EXACT ERROR MESSAGE]
- Source: [AWS service, EC2, Lambda, on-prem, internet]
- Time: [When started]
```

### Example: S3 Access Denied
```
Investigate S3 access denied error:
- Account: 123456789012
- Region: us-east-1
- Bucket: prod-application-data
- User/Role: arn:aws:iam::123456789012:role/AppServerRole
- Operation: s3:PutObject to /uploads/ prefix
- Access Method: Application on EC2 using SDK
- Error: "Access Denied (403)" when uploading files
- Source: EC2 instances in VPC 10.0.0.0/16
- Time: Started after S3 bucket policy update this morning

Focus on: bucket policy, IAM role permissions, S3 block public access, VPC endpoint policy
```

### Example: On-Prem to S3 via VPN
```
Investigate on-prem application cannot write to S3:
- Account: 987654321098
- Region: us-west-2
- Bucket: onprem-upload-staging
- User/Role: IAM user backup-service
- Operation: s3:PutObject (uploading nightly backups)
- Access Method: AWS CLI from on-prem server
- Error: Connection timeout, no response
- Source: On-prem 192.168.50.10 via VPN
- Time: Backups failing for 2 nights

Focus on: VPN tunnel status, route tables, S3 endpoint (public vs VPC), proxy settings
```

### Example: S3 Cross-Region Access
```
Investigate slow S3 access across regions:
- Account: 555666777888
- Region: Source ap-southeast-1, Destination us-east-1
- Bucket: us-east-1-data-lake (in us-east-1)
- User/Role: Lambda function in ap-southeast-1
- Operation: s3:GetObject (reading large files)
- Access Method: boto3 SDK
- Issue: Extremely slow downloads (500KB/s, should be faster)
- Time: Performance degraded over past week

Focus on: cross-region data transfer, S3 Transfer Acceleration, VPC endpoints, region optimization
```

---

## 6. VPN Troubleshooting

### Template
```
Investigate VPN issue:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- VPN Connection ID: [vpn-xxxx]
- VPN Type: [Site-to-Site, Client VPN]
- Tunnels: [Tunnel 1 status, Tunnel 2 status]
- Customer Gateway: [IP address]
- Virtual Private Gateway: [vgw-xxxx] or Transit Gateway: [tgw-xxxx]
- Issue: [Down, Intermittent, Slow, Partial connectivity]
- Time: [When]
- Impact: [What can't work]
```

### Example: Both VPN Tunnels Down
```
Investigate Site-to-Site VPN complete outage:
- Account: 123456789012
- Region: us-east-1
- VPN Connection ID: vpn-0abc123def456
- VPN Type: Site-to-Site VPN
- Tunnels: Tunnel 1 DOWN, Tunnel 2 DOWN
- Customer Gateway: 203.0.113.25 (on-prem firewall)
- Virtual Private Gateway: vgw-xyz789
- Issue: Both tunnels down, cannot establish IKE phase 1
- Time: Started 3 hours ago
- Impact: All office users cannot access AWS resources

Focus on: IKE logs, customer gateway config, pre-shared key, IP allowlist on firewall
```

### Example: Client VPN Authentication Failure
```
Investigate Client VPN login failures:
- Account: 987654321098
- Region: eu-central-1
- Client VPN Endpoint ID: cvpn-endpoint-abc123
- Authentication: Active Directory
- Issue: 15 users unable to authenticate since this morning
- Error: "Authentication failed"
- Time: Started after AD password policy change
- Impact: Remote workers cannot access corporate VPC

Focus on: AD connector status, security group rules, LDAP bind, authorization rules
```

---

## 7. Network Routing Issues

### Template
```
Investigate routing problem:
- Account: [ACCOUNT_ID]
- Region: [REGION]
- Source: [VPC/Subnet/Instance]
- Destination: [IP or resource]
- Route Tables: [rtb-xxxx]
- Gateways: [IGW/NAT/TGW/VGW]
- Issue: [Cannot reach, asymmetric routing, wrong path]
- Traceroute: [results if available]
```

### Example: Internet Access Lost
```
Investigate EC2 instances lost internet access:
- Account: 123456789012
- Region: us-west-2
- Source: Private subnet subnet-abc123 (10.0.10.0/24)
- Destination: Internet (public APIs, package repos)
- Route Tables: rtb-private-123
- NAT Gateway: nat-0xyz789 (in public subnet)
- Issue: Cannot reach internet, was working yesterday
- Time: Started this morning around 08:00 UTC
- Impact: Instances cannot download updates, external API calls failing

Focus on: NAT Gateway status, Elastic IP, route table 0.0.0.0/0 route, NACL rules
```

---

## Quick Commands for Common Tasks

### Check VPN Status
```
Check VPN connection status:
- Account: [ACCOUNT]
- Region: [REGION]
- VPN ID: [vpn-xxxxx]
Show: tunnel status, last status change, IKE/IPsec messages
```

### Verify Certificate Expiration
```
Check certificate expiration dates:
- Account: [ACCOUNT]
- Region: [REGION or "all"]
- Filter: Expiring within 30 days
Show: certificate ARN, domain, expiration date, resources using it
```

### Audit Security Group Rules
```
Review security group for access issue:
- Account: [ACCOUNT]
- Region: [REGION]
- Security Group: [sg-xxxxx]
- Required Access: [Source] to [Port]
Show: current rules, related NACLs, effective permissions
```

### List Available Backups
```
List available backups for restore:
- Account: [ACCOUNT]
- Region: [REGION]
- Resource Type: [RDS, EC2, EBS]
- Resource ID: [identifier]
- Time Range: [past 7 days]
Show: backup type, size, creation time, retention
```

---

## Context Tips for Your Use Cases

### Always Include for Connectivity Issues
- VPN/DX connection IDs
- IP addresses (both AWS and on-prem)
- What worked before vs what's failing now
- Recent changes (firewall, config, AWS updates)

### Always Include for Certificate Issues
- Certificate ARN or identifier
- Domains covered
- Where certificate is used (ALB, CloudFront, etc.)
- Expiration date if known

### Always Include for Access Requests
- Who needs access (user/role/service)
- What they need to access (specific resource ARN)
- From where (IP, VPC, on-prem)
- Why they need it (justification)

### Always Include for Backups
- What needs backup/restore
- When it needs to happen
- RPO/RTO requirements
- Last known good backup timestamp

---

## Common Failure Patterns

### VPN Issues
- Pre-shared key mismatch
- Customer gateway firewall blocking IPsec
- Phase 1 vs Phase 2 IKE failures
- Wrong encryption/hashing algorithms
- IP conflict with VPC CIDR

### Certificate Issues
- DNS validation records not in Route53
- Email validation to unmonitored address
- Certificate issued in wrong region (for ALB/CloudFront)
- Intermediate certificate missing from chain

### Access Issues
- Explicit deny in policy overriding allow
- S3 block public access settings
- Security group vs NACL confusion
- Missing VPC endpoint for S3/DynamoDB
- Cross-account trust not established

### Backup Failures
- Backup vault encryption key permissions
- Service role missing permissions
- Retention period conflict
- Resource tags not matching backup plan selector
