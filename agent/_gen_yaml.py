"""Temporary script to generate builtin_hunts.yaml v2."""

import pathlib

import yaml
import yaml as _y

CAT_IAM = "\U0001f511 Identity & Access"
CAT_DET = "\U0001f6e1 Detection & Response"
CAT_DAT = "\U0001faa3 Data & Storage"
CAT_NET = "\U0001f310 Network & Infrastructure"
CAT_THR = "\U0001f575 Threat Patterns"
CAT_ACT = "\U0001f4ca Activity & Baseline"
CAT_COM = "\u26a1 Compute & Serverless"
CAT_IAC = "\u2601 IaC & Platform"

entries = [
    # ── Identity & Access ────────────────────────────────────────────────────
    {
        "category": CAT_IAM,
        "label": "\U0001f511 Root Account Activity",
        "description": "Detects any API call made by the root account. Root should never be used in production.",
        "prompt": (
            "List all API calls made by the root account. Include event_time, event_name,\n"
            "source_ip_address, and aws_region. Order by most recent first.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, event_source,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE user_identity_type = 'Root'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f464 New IAM Users / Keys",
        "description": "Identifies IAM user and access key creation events. Unexpected creation may indicate persistence.",
        "prompt": (
            "Identify all IAM CreateUser, CreateAccessKey, and CreateLoginProfile events.\n"
            "Show who created them, when, and from which IP. Flag anything created outside\n"
            "business hours or from unexpected IPs.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.userName') AS new_user,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN ('CreateUser', 'CreateAccessKey', 'CreateLoginProfile')\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f310 Console Logins",
        "description": "Lists all console login attempts. Brute force = multiple failures followed by success.",
        "prompt": (
            "List all ConsoleLogin events including successes and failures.\n"
            "Identify accounts with multiple failed attempts followed by a success\n"
            "(possible brute force). Include source IP and user agent.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, source_ip_address,\n"
            "    aws_region, user_agent,\n"
            "    json_extract_string(raw_event, '$.responseElements.ConsoleLogin') AS login_result,\n"
            "    error_code, error_message\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source = 'signin.amazonaws.com'\n"
            "  AND event_name   = 'ConsoleLogin'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 200\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f513 Console Login without MFA",
        "description": "Detects console logins where MFA was not used. High-risk indicator of account compromise.",
        "prompt": (
            "Find all ConsoleLogin events where MFA was not used. Include user identity,\n"
            "source IP, region, and the MFAUsed flag from additionalEventData.\n"
            "MFA-less logins are a high-priority alert.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, source_ip_address, aws_region,\n"
            "    json_extract_string(raw_event, '$.additionalEventData.MFAUsed') AS mfa_used,\n"
            "    json_extract_string(raw_event, '$.additionalEventData.LoginTo')  AS login_to\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source = 'signin.amazonaws.com'\n"
            "  AND event_name   = 'ConsoleLogin'\n"
            "  AND json_extract_string(raw_event, '$.additionalEventData.MFAUsed') = 'No'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f504 Privilege Escalation (IAM)",
        "description": "Detects IAM policy attachment and role manipulation events used for privilege escalation.",
        "prompt": (
            "Detect potential IAM privilege escalation: look for PutUserPolicy,\n"
            "AttachUserPolicy, PutRolePolicy, AttachRolePolicy, CreatePolicyVersion,\n"
            "and SetDefaultPolicyVersion events. Show caller, target resource, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.userName')  AS target_user,\n"
            "    json_extract_string(request_parameters, '$.roleName')  AS target_role,\n"
            "    json_extract_string(request_parameters, '$.policyArn') AS policy_arn,\n"
            "    source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'PutUserPolicy', 'AttachUserPolicy',\n"
            "    'PutRolePolicy', 'AttachRolePolicy',\n"
            "    'CreatePolicyVersion', 'SetDefaultPolicyVersion'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f510 AssumeRole Cross-Account",
        "description": "Shows AssumeRole events where caller and target are in different AWS accounts. Indicates lateral movement.",
        "prompt": (
            "Show all AssumeRole events where the assumed role ARN is in a different\n"
            "AWS account than the caller. Include session duration and external ID if present.\n"
            "Cross-account role assumptions can indicate lateral movement.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn,\n"
            "    user_identity_account_id                                     AS caller_account,\n"
            "    recipient_account_id,\n"
            "    json_extract_string(request_parameters, '$.roleArn')         AS assumed_role_arn,\n"
            "    json_extract_string(request_parameters, '$.externalId')      AS external_id,\n"
            "    json_extract_string(request_parameters, '$.durationSeconds') AS duration_seconds,\n"
            "    source_ip_address\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name = 'AssumeRole'\n"
            "  AND user_identity_account_id IS NOT NULL\n"
            "  AND recipient_account_id     IS NOT NULL\n"
            "  AND user_identity_account_id != recipient_account_id\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001fa9e Self AssumeRole Detection",
        "description": "Detects roles that assume themselves. Often a code bug; counts toward STS API quotas.",
        "prompt": (
            "Find all AssumeRole events where the caller's session issuer ARN matches the\n"
            "target role ARN (self-assume). These waste STS quota and may indicate\n"
            "misconfigured automation.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn,\n"
            "    json_extract_string(raw_event, '$.userIdentity.sessionContext.sessionIssuer.arn') AS session_issuer_arn,\n"
            "    source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source       = 'sts.amazonaws.com'\n"
            "  AND event_name         = 'AssumeRole'\n"
            "  AND user_identity_type = 'AssumedRole'\n"
            "  AND error_code         IS NULL\n"
            "  AND json_extract_string(raw_event, '$.userIdentity.sessionContext.sessionIssuer.arn')\n"
            "      = json_extract_string(raw_event, '$.resources[0].ARN')\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f451 User Added to Admin Group",
        "description": "Detects users added to groups with 'admin' in the name. Classic privilege escalation technique.",
        "prompt": (
            "Find all AddUserToGroup events where the group name contains 'admin'.\n"
            "Show who performed the action, the target user, group name, and time.\n"
            "This is a classic privilege escalation indicator.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.userName')  AS target_user,\n"
            "    json_extract_string(request_parameters, '$.groupName') AS group_name,\n"
            "    source_ip_address, aws_region\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name = 'AddUserToGroup'\n"
            "  AND lower(json_extract_string(request_parameters, '$.groupName')) LIKE '%admin%'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f510 MFA & Password Changes",
        "description": "Detects MFA deactivation and password resets. Strong indicator of account takeover.",
        "prompt": (
            "Detect changes to authentication settings: CreateVirtualMFADevice,\n"
            "DeactivateMFADevice, DeleteVirtualMFADevice, EnableMFADevice,\n"
            "ChangePassword, UpdateLoginProfile, DeleteLoginProfile.\n"
            "MFA deactivation or password resets may indicate account takeover.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.userName') AS target_user,\n"
            "    source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'CreateVirtualMFADevice', 'DeactivateMFADevice', 'DeleteVirtualMFADevice',\n"
            "    'EnableMFADevice', 'ChangePassword', 'UpdateLoginProfile', 'DeleteLoginProfile'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f5dd Access Key Abuse",
        "description": "Detects access keys used from 3+ distinct source IPs in 7 days. Strong indicator of key leak.",
        "prompt": (
            "Find access key lifecycle events: CreateAccessKey, DeleteAccessKey,\n"
            "UpdateAccessKey, GetAccessKeyLastUsed. Also check for keys used from\n"
            "multiple source_ip_address values, which may indicate key compromise.\n"
            "Show the user_identity_arn, event_time, and source_ip_address.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn,\n"
            "    COUNT(DISTINCT source_ip_address) AS distinct_source_ips,\n"
            "    MIN(event_time) AS first_seen,\n"
            "    MAX(event_time) AS last_seen,\n"
            "    COUNT(*)        AS total_events\n"
            "FROM cloudtrail_events\n"
            "WHERE event_time >= NOW() - INTERVAL '7 days'\n"
            "  AND user_identity_arn IS NOT NULL\n"
            "  AND source_ip_address IS NOT NULL\n"
            "GROUP BY user_identity_arn\n"
            "HAVING COUNT(DISTINCT source_ip_address) >= 3\n"
            "ORDER BY distinct_source_ips DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f504 Credential Report & Enumeration",
        "description": "Detects IAM enumeration activity that maps the entire IAM landscape. Common in early attack stages.",
        "prompt": (
            "Detect IAM enumeration activity: GenerateCredentialReport,\n"
            "GetCredentialReport, ListUsers, ListRoles, ListPolicies,\n"
            "GetAccountAuthorizationDetails. These calls collectively map the\n"
            "entire IAM landscape. Group by caller and time window.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'GenerateCredentialReport', 'GetCredentialReport',\n"
            "    'ListUsers', 'ListRoles', 'ListPolicies',\n"
            "    'GetAccountAuthorizationDetails'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 200\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f3e2 Cross-Account Access",
        "description": "Finds events where the caller account differs from the recipient account. Lateral movement signal.",
        "prompt": (
            "Find all events where the caller's AWS account ID differs from the\n"
            "recipient account ID. This includes cross-account role assumptions\n"
            "and resource access. Show caller account, recipient account, event details.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, event_source,\n"
            "    user_identity_account_id AS caller_account,\n"
            "    recipient_account_id, user_identity_arn, source_ip_address\n"
            "FROM cloudtrail_events\n"
            "WHERE user_identity_account_id IS NOT NULL\n"
            "  AND recipient_account_id     IS NOT NULL\n"
            "  AND user_identity_account_id != recipient_account_id\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_IAM,
        "label": "\U0001f4cb Top IAM Actions by Principal",
        "description": "Ranks principals by IAM API call volume. High volume may indicate enumeration or approaching service limits.",
        "prompt": (
            "Identify the top callers of the IAM service by number of API calls.\n"
            "Show principal ARN, event names, account ID, and call count.\n"
            "High IAM activity may indicate enumeration or service limit pressure.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn, event_name, recipient_account_id,\n"
            "    COUNT(*) AS api_count\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source      = 'iam.amazonaws.com'\n"
            "  AND user_identity_arn IS NOT NULL\n"
            "GROUP BY user_identity_arn, event_name, recipient_account_id\n"
            "ORDER BY api_count DESC\n"
            "LIMIT 30\n"
        ),
    },
    # ── Detection & Response ─────────────────────────────────────────────────
    {
        "category": CAT_DET,
        "label": "\U0001f6ab Access Denied Errors",
        "description": "Groups AccessDenied errors by identity and API. Top offenders may indicate credential misuse.",
        "prompt": (
            "Show all AccessDenied and UnauthorizedAccess errors in the logs.\n"
            "Group by user identity and event_name to find the top offenders.\n"
            "This can indicate credential misuse or privilege escalation attempts.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn, event_name, event_source,\n"
            "    COUNT(*)        AS denied_count,\n"
            "    MIN(event_time) AS first_seen,\n"
            "    MAX(event_time) AS last_seen\n"
            "FROM cloudtrail_events\n"
            "WHERE error_code IN ('AccessDenied', 'AccessDeniedException', 'UnauthorizedAccess')\n"
            "GROUP BY user_identity_arn, event_name, event_source\n"
            "ORDER BY denied_count DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_DET,
        "label": "\U0001f6d1 CloudTrail Tampering",
        "description": "Detects any attempt to stop or modify CloudTrail. The most critical alert — indicates cover-up.",
        "prompt": (
            "Check for any attempts to disable or modify CloudTrail:\n"
            "StopLogging, DeleteTrail, UpdateTrail, PutEventSelectors.\n"
            "Also check for CloudWatch Logs deletion or GuardDuty DisableDetector.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.name')     AS trail_name,\n"
            "    json_extract_string(request_parameters, '$.trailARN') AS trail_arn,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'CreateTrail', 'UpdateTrail', 'DeleteTrail',\n"
            "    'StartLogging', 'StopLogging', 'PutEventSelectors',\n"
            "    'DeleteLogGroup', 'DisableDetector'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_DET,
        "label": "\u274c Top Error Codes (Last 7 Days)",
        "description": "Ranks error codes by frequency over the last 7 days. Error spikes can signal probing or outage.",
        "prompt": (
            "Find the most frequent API error codes and messages in the past 7 days.\n"
            "Show error count, number of affected identities, first and last occurrence.\n"
            "Error spikes may indicate probing, misconfiguration, or an outage.\n"
        ),
        "sql": (
            "SELECT\n"
            "    error_code, error_message,\n"
            "    COUNT(*)                          AS event_count,\n"
            "    COUNT(DISTINCT user_identity_arn) AS affected_identities,\n"
            "    MIN(event_time)                   AS first_seen,\n"
            "    MAX(event_time)                   AS last_seen\n"
            "FROM cloudtrail_events\n"
            "WHERE error_code IS NOT NULL\n"
            "  AND event_time >= NOW() - INTERVAL '7 days'\n"
            "GROUP BY error_code, error_message\n"
            "ORDER BY event_count DESC\n"
            "LIMIT 20\n"
        ),
    },
    {
        "category": CAT_DET,
        "label": "\u2614 AWS Support Role Access",
        "description": "Detects when AWS Support assumed the AWSServiceRoleForSupport role. Required for data sovereignty audits.",
        "prompt": (
            "Show any events where AWS Support has taken over the AWSServiceRoleForSupport\n"
            "role. This is relevant for data sovereignty and compliance requirements.\n"
            "Include event source, name, region, resource ARN, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_source, event_name, aws_region,\n"
            "    source_ip_address, user_agent, user_identity_type, recipient_account_id\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source = 'sts.amazonaws.com'\n"
            "  AND user_agent LIKE '%support.amazonaws.com%'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    # ── Data & Storage ───────────────────────────────────────────────────────
    {
        "category": CAT_DAT,
        "label": "\U0001faa3 S3 Data Access Anomalies",
        "description": "Detects bulk GetObject calls (>=100/hour) that may indicate data exfiltration.",
        "prompt": (
            "Find unusual S3 activity: large numbers of GetObject calls from a single\n"
            "IP or user within a short time window (potential exfiltration).\n"
            "Also flag DeleteBucket, DeleteObject, and PutBucketPolicy events.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn, source_ip_address,\n"
            "    DATE_TRUNC('hour', event_time) AS hour_bucket,\n"
            "    COUNT(*) AS call_count\n"
            "FROM cloudtrail_events\n"
            "WHERE event_source = 's3.amazonaws.com'\n"
            "  AND event_name   = 'GetObject'\n"
            "GROUP BY user_identity_arn, source_ip_address, hour_bucket\n"
            "HAVING COUNT(*) >= 100\n"
            "ORDER BY call_count DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_DAT,
        "label": "\U0001f512 Unencrypted EBS Snapshot",
        "description": "Finds EBS snapshots created without encryption. Compliance violation and data exposure risk.",
        "prompt": (
            "Find all CreateSnapshot and CreateSnapshots events where the resulting\n"
            "snapshot is not encrypted. Show volume ID, snapshot ID, region, and caller.\n"
            "Unencrypted snapshots may violate compliance requirements.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, aws_region,\n"
            "    json_extract_string(request_parameters, '$.volumeId')   AS volume_id,\n"
            "    json_extract_string(response_elements,  '$.snapshotId') AS snapshot_id,\n"
            "    json_extract_string(response_elements,  '$.encrypted')  AS encrypted,\n"
            "    source_ip_address\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN ('CreateSnapshot', 'CreateSnapshots')\n"
            "  AND (\n"
            "      json_extract_string(response_elements, '$.encrypted') = 'false'\n"
            "      OR json_extract_string(response_elements, '$.encrypted') IS NULL\n"
            "  )\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_DAT,
        "label": "\U0001f4a3 RDS Deleted without Final Snapshot",
        "description": "Detects RDS instance/cluster deletion with skipFinalSnapshot=true. Potential data destruction.",
        "prompt": (
            "Find all DeleteDBInstance and DeleteDBCluster events where the final\n"
            "snapshot was skipped. This may indicate data destruction or a destructive\n"
            "attack. Show DB name, caller, region, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, aws_region, event_name,\n"
            "    json_extract_string(request_parameters, '$.dBInstanceIdentifier') AS db_instance,\n"
            "    json_extract_string(request_parameters, '$.dBClusterIdentifier')  AS db_cluster,\n"
            "    source_ip_address\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN ('DeleteDBInstance', 'DeleteDBCluster')\n"
            "  AND json_extract_string(request_parameters, '$.skipFinalSnapshot') = 'true'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_DAT,
        "label": "\U0001f513 S3 Public Access Block Disabled",
        "description": "Detects S3 public access block settings being disabled. Immediate data exposure risk.",
        "prompt": (
            "Find all PutPublicAccessBlock events where any of the four block settings\n"
            "were set to false. This exposes S3 buckets to public access.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, aws_region,\n"
            "    json_extract_string(request_parameters, '$.bucketName')                     AS bucket_name,\n"
            "    json_extract_string(request_parameters, '$.PublicAccessBlockConfiguration') AS block_config,\n"
            "    source_ip_address\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name = 'PutPublicAccessBlock'\n"
            "  AND (\n"
            "      request_parameters LIKE '%\"blockPublicAcls\":false%'\n"
            "      OR request_parameters LIKE '%\"blockPublicPolicy\":false%'\n"
            "      OR request_parameters LIKE '%\"ignorePublicAcls\":false%'\n"
            "      OR request_parameters LIKE '%\"restrictPublicBuckets\":false%'\n"
            "  )\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_DAT,
        "label": "\U0001f513 KMS Key Operations",
        "description": "Flags sensitive KMS operations including key deletion and high-volume Decrypt calls.",
        "prompt": (
            "Find sensitive KMS operations: DisableKey, ScheduleKeyDeletion,\n"
            "CreateGrant, PutKeyPolicy, Decrypt (high volume from single source).\n"
            "Attackers may disable encryption or decrypt stolen data.\n"
            "Show caller identity, key ID from request_parameters, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.keyId') AS key_id,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'DisableKey', 'ScheduleKeyDeletion', 'CancelKeyDeletion',\n"
            "    'CreateGrant', 'PutKeyPolicy', 'Decrypt'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_DAT,
        "label": "\U0001f4e7 Data Exfiltration Channels",
        "description": "Detects high-volume SNS/SQS/SES/S3 PutObject calls (>=50/hour) that may indicate exfiltration.",
        "prompt": (
            "Look for potential data exfiltration via messaging/storage services:\n"
            "SNS Publish, SQS SendMessage, SES SendEmail, and any PutObject to\n"
            "S3 buckets. Focus on high-volume calls from a single identity in a\n"
            "short time window. Filter by event_source for sns, sqs, ses, s3.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn, event_source, event_name,\n"
            "    DATE_TRUNC('hour', event_time) AS hour_bucket,\n"
            "    COUNT(*) AS call_count\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN ('Publish', 'SendMessage', 'SendEmail', 'PutObject')\n"
            "  AND event_source IN (\n"
            "      'sns.amazonaws.com', 'sqs.amazonaws.com',\n"
            "      'ses.amazonaws.com', 's3.amazonaws.com'\n"
            "  )\n"
            "GROUP BY user_identity_arn, event_source, event_name, hour_bucket\n"
            "HAVING COUNT(*) >= 50\n"
            "ORDER BY call_count DESC\n"
            "LIMIT 50\n"
        ),
    },
    # ── Network & Infrastructure ─────────────────────────────────────────────
    {
        "category": CAT_NET,
        "label": "\U0001f525 Security Group Modifications",
        "description": "Detects security group rule changes, especially rules allowing 0.0.0.0/0 on any port.",
        "prompt": (
            "Find all security group changes: AuthorizeSecurityGroupIngress,\n"
            "AuthorizeSecurityGroupEgress, RevokeSecurityGroupIngress,\n"
            "RevokeSecurityGroupEgress, CreateSecurityGroup, DeleteSecurityGroup.\n"
            "Check request_parameters for rules opening 0.0.0.0/0 or port 22/3389.\n"
            "Show caller identity, time, and the specific changes made.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn, aws_region,\n"
            "    json_extract_string(request_parameters, '$.groupId') AS security_group_id,\n"
            "    source_ip_address, request_parameters\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'AuthorizeSecurityGroupIngress', 'AuthorizeSecurityGroupEgress',\n"
            "    'RevokeSecurityGroupIngress',    'RevokeSecurityGroupEgress',\n"
            "    'CreateSecurityGroup',           'DeleteSecurityGroup',\n"
            "    'ModifySecurityGroupRules'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_NET,
        "label": "\U0001f30d Security Group Opened to Internet",
        "description": "Finds security group rules that allow traffic from 0.0.0.0/0. Direct public exposure risk.",
        "prompt": (
            "Find security group rules that allow traffic from 0.0.0.0/0 (any IP).\n"
            "This includes AuthorizeSecurityGroupIngress and ModifySecurityGroupRules.\n"
            "Show the security group ID, caller, region, and full rule parameters.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn, aws_region,\n"
            "    json_extract_string(request_parameters, '$.groupId') AS security_group_id,\n"
            "    source_ip_address, request_parameters\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'AuthorizeSecurityGroupIngress',\n"
            "    'AuthorizeSecurityGroupEgress',\n"
            "    'ModifySecurityGroupRules'\n"
            ")\n"
            "  AND request_parameters LIKE '%0.0.0.0/0%'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_NET,
        "label": "\U0001f4e1 Network Infrastructure Changes",
        "description": "Detects VPC and network-level changes that may establish attacker-controlled infrastructure.",
        "prompt": (
            "Detect VPC and network changes: CreateVpc, DeleteVpc, CreateSubnet,\n"
            "CreateInternetGateway, AttachInternetGateway, CreateNatGateway,\n"
            "CreateVpcPeeringConnection, AcceptVpcPeeringConnection,\n"
            "ModifyVpcAttribute. Show caller, region, and parameters.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    aws_region, source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'CreateVpc', 'DeleteVpc', 'CreateSubnet', 'DeleteSubnet',\n"
            "    'CreateInternetGateway', 'AttachInternetGateway', 'DetachInternetGateway',\n"
            "    'CreateNatGateway', 'DeleteNatGateway',\n"
            "    'CreateVpcPeeringConnection', 'AcceptVpcPeeringConnection',\n"
            "    'ModifyVpcAttribute'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_NET,
        "label": "\U0001f5a5 Write Events from Management Console",
        "description": "Identifies mutating API calls made via the AWS console. Useful when CLI-only access is expected.",
        "prompt": (
            "List all write (mutating) API calls made via the AWS Management Console.\n"
            "These may be unexpected if your environment only uses CLI/SDK access.\n"
            "Show caller, service, action, region, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, event_source, event_name,\n"
            "    aws_region, source_ip_address, user_agent\n"
            "FROM cloudtrail_events\n"
            "WHERE read_only = false\n"
            "  AND (\n"
            "      json_extract_string(raw_event, '$.sessionCredentialFromConsole') = 'true'\n"
            "      OR user_agent LIKE '%signin.amazonaws.com%'\n"
            "  )\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 200\n"
        ),
    },
    {
        "category": CAT_NET,
        "label": "\U0001f512 TLS Downgrade Detection",
        "description": "Finds API calls using TLS 1.1 or older. Support ended June 2023; usage may indicate legacy clients.",
        "prompt": (
            "Find all API calls that used TLS version 1.1 or lower. These clients\n"
            "must be upgraded as older TLS is deprecated by AWS. Show event source,\n"
            "TLS version, source IP, and call count.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_source,\n"
            "    json_extract_string(raw_event, '$.tlsDetails.tlsVersion') AS tls_version,\n"
            "    source_ip_address, recipient_account_id,\n"
            "    COUNT(*) AS call_count\n"
            "FROM cloudtrail_events\n"
            "WHERE json_extract_string(raw_event, '$.tlsDetails.tlsVersion') LIKE 'TLSv%'\n"
            "  AND TRY_CAST(\n"
            "      replace(\n"
            "          json_extract_string(raw_event, '$.tlsDetails.tlsVersion'),\n"
            "          'TLSv', ''\n"
            "      ) AS DOUBLE\n"
            "  ) <= 1.1\n"
            "GROUP BY event_source, tls_version, source_ip_address, recipient_account_id\n"
            "ORDER BY call_count DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_NET,
        "label": "\U0001f6a7 VPC Endpoint Access Denied",
        "description": "Detects access denied errors via VPC endpoints. May indicate misconfigured endpoint policy.",
        "prompt": (
            "Find access denied errors that occurred via VPC endpoints. These may\n"
            "indicate misconfigured VPC endpoint policies or unauthorized access attempts.\n"
            "Show the VPC endpoint ID, service, caller, and error details.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, event_source, user_identity_arn,\n"
            "    source_ip_address, error_code, error_message,\n"
            "    json_extract_string(raw_event, '$.vpcEndpointId') AS vpc_endpoint_id\n"
            "FROM cloudtrail_events\n"
            "WHERE error_code IN ('AccessDenied', 'AccessDeniedException')\n"
            "  AND json_extract_string(raw_event, '$.vpcEndpointId') IS NOT NULL\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    # ── Threat Patterns ──────────────────────────────────────────────────────
    {
        "category": CAT_THR,
        "label": "\U0001f575 First-Time API Calls (24h)",
        "description": "Finds API calls seen in the last 24h but never before. Novel operations may indicate attacker tooling.",
        "prompt": (
            "Find API calls that appear in the last 24 hours but have never been seen\n"
            "before in the entire log dataset. These novel operations may indicate\n"
            "attacker reconnaissance or tooling.\n"
        ),
    },
    {
        "category": CAT_THR,
        "label": "\U0001f319 Off-Hours Activity",
        "description": "Flags mutating API calls outside business hours (JST 22:00-06:00). Human logins at night may be compromised.",
        "prompt": (
            "Find API calls made between 10 PM and 6 AM local time (UTC 13:00-23:00 JST).\n"
            "Filter for write/mutating operations (read_only = false).\n"
            "Off-hours activity by human users may indicate compromise.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, event_source, user_identity_arn,\n"
            "    source_ip_address, aws_region\n"
            "FROM cloudtrail_events\n"
            "WHERE read_only = false\n"
            "  AND (\n"
            "      EXTRACT(HOUR FROM event_time AT TIME ZONE 'Asia/Tokyo') >= 22\n"
            "      OR EXTRACT(HOUR FROM event_time AT TIME ZONE 'Asia/Tokyo') < 6\n"
            "  )\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 200\n"
        ),
    },
    {
        "category": CAT_THR,
        "label": "\U0001f50d Reconnaissance Pattern",
        "description": "Identifies callers who ran 10+ distinct read-only API calls in one hour. Common early attack phase.",
        "prompt": (
            "Identify potential reconnaissance: callers who executed 10 or more distinct\n"
            "Describe*, List*, or Get* API calls within any 1-hour window.\n"
            "This pattern is common in the early stages of an attack.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn,\n"
            "    DATE_TRUNC('hour', event_time) AS hour_bucket,\n"
            "    COUNT(DISTINCT event_name)     AS distinct_api_calls,\n"
            "    COUNT(*)                       AS total_calls\n"
            "FROM cloudtrail_events\n"
            "WHERE (\n"
            "    event_name LIKE 'Describe%'\n"
            "    OR event_name LIKE 'List%'\n"
            "    OR event_name LIKE 'Get%'\n"
            ")\n"
            "GROUP BY user_identity_arn, hour_bucket\n"
            "HAVING COUNT(DISTINCT event_name) >= 10\n"
            "ORDER BY distinct_api_calls DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_THR,
        "label": "\U0001f30d Multi-Region Activity",
        "description": "Detects identities performing writes in 3+ regions in one day. Geographic spread may indicate compromise.",
        "prompt": (
            "Identify user identities (user_identity_arn) that performed write operations\n"
            "(read_only = false) in 3 or more distinct aws_region values within the\n"
            "same day. Unusual geographic spread may indicate compromised credentials\n"
            "being used from multiple attacker locations.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn,\n"
            "    CAST(event_time AS DATE)       AS activity_date,\n"
            "    COUNT(DISTINCT aws_region)     AS distinct_regions,\n"
            "    array_agg(DISTINCT aws_region) AS regions\n"
            "FROM cloudtrail_events\n"
            "WHERE read_only = false\n"
            "  AND user_identity_arn IS NOT NULL\n"
            "GROUP BY user_identity_arn, CAST(event_time AS DATE)\n"
            "HAVING COUNT(DISTINCT aws_region) >= 3\n"
            "ORDER BY distinct_regions DESC\n"
            "LIMIT 50\n"
        ),
    },
    {
        "category": CAT_THR,
        "label": "\U0001f916 Unusual User Agents",
        "description": "Lists rare user agents (<5 events). Custom tooling like Pacu or curl may indicate attacker tooling.",
        "prompt": (
            "List all distinct user_agent values with their event counts.\n"
            "Flag user agents that appear fewer than 5 times — they may indicate\n"
            "custom attack tooling (e.g., Pacu, Prowler misuse, or curl/wget).\n"
            "Also flag any user_agent containing 'python', 'boto', or 'script'.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_agent,\n"
            "    COUNT(*)                          AS event_count,\n"
            "    COUNT(DISTINCT user_identity_arn) AS distinct_callers,\n"
            "    MIN(event_time)                   AS first_seen,\n"
            "    MAX(event_time)                   AS last_seen\n"
            "FROM cloudtrail_events\n"
            "WHERE user_agent IS NOT NULL\n"
            "GROUP BY user_agent\n"
            "HAVING COUNT(*) < 5\n"
            "    OR lower(user_agent) LIKE '%pacu%'\n"
            "    OR lower(user_agent) LIKE '%boto%'\n"
            "    OR lower(user_agent) LIKE '%python%'\n"
            "    OR lower(user_agent) LIKE '%curl%'\n"
            "    OR lower(user_agent) LIKE '%wget%'\n"
            "ORDER BY event_count ASC\n"
            "LIMIT 100\n"
        ),
    },
    # ── Activity & Baseline ──────────────────────────────────────────────────
    {
        "category": CAT_ACT,
        "label": "\U0001f4ca Top Callers This Week",
        "description": "Shows the 20 most active IAM entities by event count over the past 7 days.",
        "prompt": (
            "Show the top 20 most active IAM entities (by event count) in the past 7 days.\n"
            "Break down by read vs write operations. Flag any service accounts performing\n"
            "an unusually high number of mutating calls.\n"
        ),
        "sql": (
            "SELECT\n"
            "    user_identity_arn,\n"
            "    COUNT(*)                                    AS total_events,\n"
            "    COUNT(*) FILTER (WHERE read_only = true)    AS read_events,\n"
            "    COUNT(*) FILTER (WHERE read_only = false)   AS write_events,\n"
            "    COUNT(DISTINCT aws_region)                  AS regions_active,\n"
            "    MAX(event_time)                             AS last_seen\n"
            "FROM cloudtrail_events\n"
            "WHERE event_time >= NOW() - INTERVAL '7 days'\n"
            "  AND user_identity_arn IS NOT NULL\n"
            "GROUP BY user_identity_arn\n"
            "ORDER BY total_events DESC\n"
            "LIMIT 20\n"
        ),
    },
    {
        "category": CAT_ACT,
        "label": "\u274c Error Spike Detection",
        "description": "Finds 1-hour windows where error count exceeds the daily average by 3x. Signals scanning or outage.",
        "prompt": (
            "Find time windows (1-hour buckets) where the total number of API errors\n"
            "(error_code IS NOT NULL) exceeds the daily average by 3x or more.\n"
            "Show the time bucket, error count, top error codes, and the user\n"
            "identities generating the most errors.\n"
        ),
    },
    {
        "category": CAT_ACT,
        "label": "\U0001f4ca Activity by Region",
        "description": "Counts API calls per AWS region. Unexpected regions may indicate unauthorized resource creation.",
        "prompt": (
            "Show the total number of API calls broken down by AWS region.\n"
            "Highlight regions with unusually high activity or regions that are\n"
            "not normally used by this account (potential unauthorized resource creation).\n"
        ),
        "sql": (
            "SELECT\n"
            "    aws_region,\n"
            "    COUNT(*)                                    AS total_events,\n"
            "    COUNT(*) FILTER (WHERE read_only = false)   AS write_events,\n"
            "    COUNT(DISTINCT user_identity_arn)            AS distinct_callers,\n"
            "    MIN(event_time)                              AS first_event,\n"
            "    MAX(event_time)                              AS last_event\n"
            "FROM cloudtrail_events\n"
            "GROUP BY aws_region\n"
            "ORDER BY total_events DESC\n"
        ),
    },
    {
        "category": CAT_ACT,
        "label": "\U0001f50d Events with Errors (24h)",
        "description": "Lists all error events in the past 24 hours. Quick overview of what is failing right now.",
        "prompt": (
            "Show all API calls in the past 24 hours that resulted in errors.\n"
            "Include caller, service, action, region, error code and message.\n"
            "Useful for quickly identifying what is failing or being probed.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, event_source, event_name,\n"
            "    aws_region, source_ip_address, user_agent, error_code, error_message\n"
            "FROM cloudtrail_events\n"
            "WHERE error_code IS NOT NULL\n"
            "  AND event_time >= NOW() - INTERVAL '24 hours'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 200\n"
        ),
    },
    # ── Compute & Serverless ─────────────────────────────────────────────────
    {
        "category": CAT_COM,
        "label": "\U0001f5a5 EC2 Instance Launches",
        "description": "Lists all RunInstances events. Unexpected launches in unusual regions may indicate cryptomining.",
        "prompt": (
            "List all RunInstances events. Show who launched the instances, when,\n"
            "from which IP, and in which region. Flag launches by unexpected users\n"
            "or in regions not normally used by this account. Include instance type\n"
            "from request_parameters if available.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, user_identity_arn, aws_region,\n"
            "    json_extract_string(request_parameters, '$.instanceType') AS instance_type,\n"
            "    source_ip_address, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name = 'RunInstances'\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    {
        "category": CAT_COM,
        "label": "\u26a1 Lambda Function Tampering",
        "description": "Detects Lambda creation, code updates, and permission changes. Attackers use Lambda for persistence.",
        "prompt": (
            "Find Lambda-related events: CreateFunction, UpdateFunctionCode,\n"
            "UpdateFunctionConfiguration, AddPermission, CreateEventSourceMapping.\n"
            "Attackers may deploy malicious functions for persistence or crypto mining.\n"
            "Show caller, function details from request_parameters, and time.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.functionName') AS function_name,\n"
            "    json_extract_string(request_parameters, '$.runtime')      AS runtime,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'CreateFunction20150331', 'CreateFunction',\n"
            "    'UpdateFunctionCode20150331v2', 'UpdateFunctionCode',\n"
            "    'UpdateFunctionConfiguration20150331v2', 'UpdateFunctionConfiguration',\n"
            "    'AddPermission20150331v2', 'AddPermission',\n"
            "    'CreateEventSourceMapping'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
    # ── IaC & Platform ───────────────────────────────────────────────────────
    {
        "category": CAT_IAC,
        "label": "\U0001f3d7 CloudFormation / IaC Abuse",
        "description": "Detects CloudFormation stack operations. Attackers may use IaC to rapidly deploy malicious infrastructure.",
        "prompt": (
            "Find CloudFormation stack operations: CreateStack, UpdateStack,\n"
            "DeleteStack, CreateChangeSet. Attackers may use IaC to rapidly deploy\n"
            "malicious infrastructure. Show stack name from request_parameters,\n"
            "caller identity, and whether the operation succeeded or failed.\n"
        ),
        "sql": (
            "SELECT\n"
            "    event_time, event_name, user_identity_arn,\n"
            "    json_extract_string(request_parameters, '$.stackName') AS stack_name,\n"
            "    source_ip_address, aws_region, error_code\n"
            "FROM cloudtrail_events\n"
            "WHERE event_name IN (\n"
            "    'CreateStack', 'UpdateStack', 'DeleteStack',\n"
            "    'CreateChangeSet', 'ExecuteChangeSet'\n"
            ")\n"
            "ORDER BY event_time DESC\n"
            "LIMIT 100\n"
        ),
    },
]

header = (
    "# Built-in Threat Hunting Queries — v2\n"
    "#\n"
    "# Schema:\n"
    "#   category:    Sidebar grouping label\n"
    "#   label:       Display name shown in the UI\n"
    "#   description: One-line explanation of what this query detects and why it matters\n"
    "#   prompt:      Natural language prompt sent to the AI agent (requires API key)\n"
    "#   sql:         (optional) Pre-built DuckDB SQL for direct execution (no API key needed)\n"
    "#\n"
    "# SQL convention:\n"
    "#   - Table: cloudtrail_events\n"
    "#   - JSON extraction: json_extract_string(column, '$.field')\n"
    "#   - All column names are snake_case (e.g. event_name, user_identity_arn)\n\n"
)

out = header + yaml.dump(
    entries,
    allow_unicode=True,
    default_flow_style=False,
    sort_keys=False,
    width=120,
)

pathlib.Path("builtin_hunts.yaml").write_text(out, encoding="utf-8")

# Verify

data = _y.safe_load(out)
sql_count = sum(1 for e in data if e.get("sql"))
print(f"Written: {len(data)} entries, {sql_count} with direct SQL")
