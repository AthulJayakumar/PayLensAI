param(
    [string]$Environment = "pilot",
    [string]$Region = "eu-north-1",
    [string]$Profile = "paylens-bootstrap"
)

$ErrorActionPreference = "Stop"
$stack = "PayLens-$Environment"

function Get-Output([string]$Key) {
    aws cloudformation describe-stacks --stack-name $stack --region $Region --profile $Profile `
        --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" --output text
}

$applicationUrl = Get-Output "ApplicationUrl"
$databaseId = Get-Output "DatabaseInstanceIdentifier"
$webhookDlqUrl = Get-Output "WebhookDeadLetterQueueUrl"

$health = Invoke-RestMethod -Uri "$applicationUrl/health" -Method Get
$database = aws rds describe-db-instances --db-instance-identifier $databaseId --region $Region --profile $Profile `
    --query "DBInstances[0].{Status:DBInstanceStatus,Encrypted:StorageEncrypted,BackupDays:BackupRetentionPeriod,LatestRestorableTime:LatestRestorableTime,DeletionProtection:DeletionProtection}" --output json | ConvertFrom-Json
$dlq = aws sqs get-queue-attributes --queue-url $webhookDlqUrl --attribute-names ApproximateNumberOfMessages `
    --region $Region --profile $Profile --output json | ConvertFrom-Json

$result = [ordered]@{
    application_health = $health.status
    database_status = $database.Status
    database_encrypted = $database.Encrypted
    backup_retention_days = $database.BackupDays
    latest_restorable_time = $database.LatestRestorableTime
    deletion_protection = $database.DeletionProtection
    webhook_dead_letter_messages = [int]$dlq.Attributes.ApproximateNumberOfMessages
}

$result | ConvertTo-Json

if ($health.status -ne "ok" -or $database.Status -ne "available" -or -not $database.Encrypted `
    -or $database.BackupDays -lt 1 -or -not $database.LatestRestorableTime -or $result.webhook_dead_letter_messages -gt 0) {
    throw "Pilot readiness verification failed. Review the JSON result above."
}
