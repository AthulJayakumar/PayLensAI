param(
    [string]$Environment = "pilot",
    [string]$Region = "eu-north-1",
    [string]$Profile = ""
)

$ErrorActionPreference = "Stop"
$stack = "PayLens-$Environment"
$profileArgs = if ($Profile) { @("--profile", $Profile) } else { @() }

function Get-Output([string]$Key) {
    $value = aws cloudformation describe-stacks --stack-name $stack --region $Region @profileArgs `
        --query "Stacks[0].Outputs[?OutputKey=='$Key'].OutputValue | [0]" --output text
    if ($LASTEXITCODE -ne 0) { throw "Could not read CloudFormation output $Key." }
    return $value
}

$applicationUrl = Get-Output "ApplicationUrl"
$databaseId = Get-Output "DatabaseInstanceIdentifier"
$webhookDlqUrl = Get-Output "WebhookDeadLetterQueueUrl"

$health = Invoke-RestMethod -Uri "$applicationUrl/health" -Method Get
$databaseJson = aws rds describe-db-instances --db-instance-identifier $databaseId --region $Region @profileArgs `
    --query "DBInstances[0].{Status:DBInstanceStatus,Encrypted:StorageEncrypted,BackupDays:BackupRetentionPeriod,LatestRestorableTime:LatestRestorableTime,DeletionProtection:DeletionProtection}" --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the pilot database." }
$database = $databaseJson
$dlqJson = aws sqs get-queue-attributes --queue-url $webhookDlqUrl --attribute-names ApproximateNumberOfMessages `
    --region $Region @profileArgs --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the webhook dead-letter queue." }
$dlq = $dlqJson

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
