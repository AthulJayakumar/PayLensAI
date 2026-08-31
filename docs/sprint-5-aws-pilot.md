# Sprint 5 — AWS pilot architecture and runbook

Status date: 2026-08-31. Region: `eu-north-1` (Stockholm). The stack supports
`dev` and `pilot`; use `pilot` for the merchant-facing environment.

Deployment status: **BLOCKED**. The latest local AWS check returns
`InvalidClientTokenId`; an administrator-approved short-lived session must be
established first. The earlier identity
`arn:aws:iam::169133351222:user/Athul` also lacked
`cloudformation:DescribeStacks` on `CDKToolkit`. Grant or assume a reviewed CDK
deployment role with CloudFormation and bootstrap permissions, then follow the
deployment procedure below. No Sprint 5 AWS resources were created by these
checks.

## Decision

PayLens uses ECS Fargate for the FastAPI API, one SQS worker service, and the
Vinext server-rendered frontend.

| Option | Fit | Decision |
|---|---|---|
| ECS Fargate | Native containers, long-lived FastAPI/webhook process, SQS workers, 64 MiB upload contract, predictable pilot operations | Selected |
| App Runner | Simple HTTP deployment, but a VPC connector needs private subnets and NAT for Stripe/public AWS endpoints; no first-class non-HTTP worker | Rejected for pilot cost/worker fit |
| Lambda/API Gateway | Scales to zero, but synchronous Lambda request/response payloads are 6 MB and the current CSV contract is 64 MiB; 15-minute execution and a second runtime model would force unnecessary redesign | Rejected |

AWS documents the [Fargate public-IP/private-subnet networking behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html),
[App Runner VPC outbound/NAT behavior](https://docs.aws.amazon.com/apprunner/latest/dg/network-vpc.html),
and [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).

The existing Vinext application emits a server runtime and dynamic routes, not
standalone HTML. S3 + CloudFront static hosting therefore cannot run it.
Amplify can accept a custom SSR adapter under its
[deployment specification](https://docs.aws.amazon.com/amplify/latest/userguide/ssr-deployment-specification.html),
but Vinext has no maintained Amplify adapter in this repository. A 0.25-vCPU
Fargate frontend behind the same ALB is the smallest verified option and avoids
building an unowned adapter. CloudFront remains the HTTPS/cache/security edge.

## Architecture

```text
Browser / Stripe
      |
      | TLS 1.2+, CloudFront HTTPS
      v
CloudFront ---- origin verification header ----> public ALB (HTTP origin)
      |                                           | default response: 403
      |                                           +--> frontend ECS :3000
      +-- /api/* and /health -------------------->+--> FastAPI ECS :8000
                                                        |
                    public subnets, public task IPs     +--> SQS (sync/analysis/webhook)
                    no inbound task rules               +--> S3 (KMS raw/input)
                                                        +--> Stripe HTTPS
                                                        +--> RDS PostgreSQL TLS
                                                                 ^
SQS --> worker ECS (1–3 tasks) -------------------------------+  |
                                                                |
                                      isolated DB subnets, private RDS
```

There is no NAT Gateway. ECS tasks are in public subnets with assigned public
IPs solely for outbound internet/AWS access. Their security group has no public
ingress; only the ALB security group reaches ports 8000/3000. RDS is in isolated
subnets, is not publicly accessible, and accepts 5432 only from the task security
group. This trades public task interfaces for roughly $35–$45/month NAT savings.

## Resources and security

- RDS PostgreSQL 17, `db.t4g.micro`, 20 GiB gp3 autoscaling to 50 GiB, encrypted,
  automated backups (1 day dev, 7 days pilot), retained snapshot on deletion,
  PostgreSQL logs, minor upgrades, SSL required by the application URL.
- S3 raw/input bucket: KMS encryption, TLS-only bucket policy, Block Public
  Access, versioning, opaque SHA-256 tenant/object partitions. Temporary CSV
  inputs expire after 7 days; raw objects transition to Standard-IA after 30.
- SQS provider-sync, analysis, and webhook queues: KMS-managed encryption,
  long polling, 4 receive attempts, separate 14-day DLQs. Jobs are persisted in
  PostgreSQL before dispatch; `(merchant, deduplication_key)` is unique.
- Cognito User Pool: invitation-only, email sign-in, 12-character strong
  passwords, optional TOTP, one-hour access tokens. PostgreSQL stores users and
  tenant memberships with `OWNER`, `ADMIN`, `ANALYST`, and `VIEWER` roles.
  Tenant identity comes from server-side membership lookup, never a request ID.
- Secrets Manager holds RDS credentials, the application credential master,
  and Stripe settings. ECS roles receive only required secret/S3/SQS/KMS actions;
  workloads contain no static AWS keys.
- Provider tokens remain field-encrypted with Fernet. The key is derived from a
  high-entropy Secrets Manager value protected by the rotating KMS data key.
  This is KMS-protected key storage, not per-record envelope encryption; direct
  KMS data-key envelopes are a post-pilot hardening item.
- CloudFront enforces HTTPS. Its default `cloudfront.net` certificate uses an
  AWS-fixed compatibility policy; a custom domain plus ACM certificate is needed
  to enforce TLS 1.2 at the viewer edge and is a merchant-pilot gate. The ALB returns 403 without a deploy-time
  origin verification header. FastAPI adds security headers, a 120-request/minute
  pilot limiter, explicit CORS, and the existing 64 MiB upload cap. WAF is not
  enabled: its fixed Web ACL/rule charges are disproportionate at pilot traffic;
  enable it when abuse data or a public launch justifies the extra cost.
- JSON logs deliberately contain IDs, paths, status, timings, and safe error
  types—not tokens or provider/payment payloads. CloudWatch retains API/worker
  logs 30 days and frontend logs 7 days. Alarms cover ALB 5xx, worker failures,
  each DLQ, and high DB connections; a dashboard covers latency, errors, and queues.

## Deployment

Prerequisites: AWS CLI, Docker, Node 24, an operator email, and a random
32+ character origin value. CDK creates all critical infrastructure. The ECR
repository stack is intentionally first so immutable images exist before ECS
service stabilization.

```powershell
cd infrastructure
npm ci
$env:CDK_DEFAULT_ACCOUNT=(aws sts get-caller-identity --query Account --output text)
$env:CDK_DEFAULT_REGION="eu-north-1"
npx cdk bootstrap "aws://$env:CDK_DEFAULT_ACCOUNT/eu-north-1"
npx cdk bootstrap "aws://$env:CDK_DEFAULT_ACCOUNT/us-east-1"
npx cdk deploy PayLens-pilot-Images --require-approval never -c environment=pilot

$tag=(git rev-parse --short=12 HEAD)
$registry="$env:CDK_DEFAULT_ACCOUNT.dkr.ecr.eu-north-1.amazonaws.com"
aws ecr get-login-password | docker login --username AWS --password-stdin $registry
docker build -t "$registry/paylens-pilot-backend:$tag" -f ..\Dockerfile ..
docker push "$registry/paylens-pilot-backend:$tag"
docker build -t "$registry/paylens-pilot-frontend:$tag" -f ..\frontend\Dockerfile ..\frontend
docker push "$registry/paylens-pilot-frontend:$tag"

$origin=[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
npx cdk deploy PayLens-pilot PayLens-pilot-Costs --require-approval never -c environment=pilot -c imageTag=$tag `
  --parameters PayLens-pilot:BudgetAlertEmail="you@example.com" `
  --parameters PayLens-pilot:OriginVerifyHeader="$origin" `
  --parameters PayLens-pilot-Costs:BudgetAlertEmail="you@example.com"
```

Run the migration exactly once as an ECS one-off task, never from API startup:

```powershell
bash ..\scripts\run-migrations.sh pilot
bash ..\scripts\smoke-aws.sh pilot
```

Create the first Cognito user with `aws cognito-idp admin-create-user`, obtain
its `sub` with `admin-get-user`, then run the packaged command below as a
one-off API task with `OWNER`:

```text
python -m app.admin.provision_user --subject <cognito-sub> --email <email> \
  --merchant-id <merchant-id> --merchant-name <merchant-name> --role OWNER
```

The command reads the same secret-injected database environment as the API.
Do not expose RDS or pass its password on a command line.

The operational wrapper resolves the deployed private network and task
definition from CloudFormation outputs:

```powershell
bash ..\scripts\provision-pilot-user.sh pilot <cognito-sub> <email> `
  <merchant-id> "<merchant-name>" OWNER
```

The GitHub workflow uses reviewed `workflow_dispatch`, OIDC (no AWS access-key
secret), immutable commit tags, an explicit migration task, service stability
waits, and HTTP smoke tests. Configure environment secrets:
`AWS_DEPLOY_ROLE_ARN`, `BUDGET_ALERT_EMAIL`, and `ORIGIN_VERIFY_HEADER`.

## Stripe test-mode deployment gate

The deployed Stripe secret is deliberately initialized to `NOT_CONFIGURED`.
Before a merchant pilot:

1. Create a Stripe App test/sandbox client and set its redirect URL to
   `https://<CloudFront-domain>/api/providers/stripe/oauth/callback`.
2. Create a Stripe test webhook endpoint at
   `https://<CloudFront-domain>/api/webhooks/stripe` for PaymentIntent, refund,
   and dispute events.
3. Update the `paylens-pilot/stripe` secret JSON keys `appClientId`,
   `developerApiKey`, and `webhookSecret`; force new API/worker deployments.
4. Sign in as the test merchant, authorize Stripe, and confirm encrypted token
   ciphertext in RDS without printing it.
5. Start sync. Confirm API returns `QUEUED`; observe RUNNING/COMPLETED, canonical
   rows, S3 raw objects, analysis/insights, and dashboard values.
6. Use Stripe CLI test-mode fixtures/events. Confirm public webhook returns
   quickly, signature failures are 400, processing is queued, canonical state
   updates, and replaying the same event reports duplicate with one DB event/job.
7. Disconnect. Confirm provider deauthorization is attempted, local credentials
   are removed even if Stripe returns an error, and `STRIPE_DISCONNECTED` audit exists.

No Stripe credentials were available during implementation, so this gate is
not claimed as executed.

## Migration, backup, restore, rollback

Before migration, verify the latest automated RDS backup and consider a manual
snapshot. Run `alembic upgrade head` in the one-off API task. Alembic downgrade
exists for schema rollback, but prefer forward fixes after data-bearing changes;
never downgrade without reviewing destructive operations and taking a snapshot.

Restore test procedure: restore an automated snapshot to a new private instance,
attach a temporary task security group, run `SELECT count(*)` and application
read smoke tests from a one-off ECS task, then remove the temporary instance.
This procedure is documented but has not yet been executed against pilot data.
S3 versioning protects replacement/deletion errors; retained objects and the KMS
key survive stack deletion.

Application rollback uses the previous immutable ECR tag:

```powershell
npx cdk deploy PayLens-pilot -c environment=pilot -c imageTag=<previous-tag> --parameters ...
```

Destruction (retained ECR, S3, KMS, Cognito and DB snapshot require deliberate
separate cleanup):

```powershell
npx cdk destroy PayLens-pilot -c environment=pilot
npx cdk destroy PayLens-pilot-Costs -c environment=pilot
npx cdk destroy PayLens-pilot-Images -c environment=pilot
```

## Approximate monthly pilot cost

Estimates are planning ranges for Stockholm, low traffic, 730 hours, and exclude
tax. Verify with AWS Pricing Calculator before approval.

| Component | Approx. USD/month | Main driver |
|---|---:|---|
| API Fargate (0.5 vCPU/1 GiB) | 18–25 | always on |
| Worker Fargate (1 vCPU/2 GiB, min 1) | 35–50 | always on; scale-out adds cost |
| Frontend Fargate (0.25 vCPU/0.5 GiB) | 9–14 | always on |
| RDS `db.t4g.micro` + 20 GiB | 18–30 | instance/storage/backups |
| ALB | 18–25 | hourly + LCU |
| CloudFront/data transfer | 1–8 | traffic dependent |
| S3 + SQS | <1–3 | storage/requests |
| CloudWatch | 3–12 | log volume/metrics |
| Secrets Manager + KMS | 4–8 | secrets/keys/API calls |
| Cognito | 0–2 | pilot MAU usually free-tier eligible |
| NAT Gateway | **0** | deliberately omitted |
| Total | **106–177 USD** (about **£79–£132**) | within £50–£150 target |

The always-on worker, ALB, RDS, and verbose logs are the largest risks. Scale
the worker to zero on a schedule only after validating webhook latency; do not
remove the DLQ/monitoring path. AWS promotional credits generally apply to
eligible AWS service usage but not taxes, support, Marketplace purchases, or
expired/ineligible charges. This repository cannot inspect the account's credit
balance; confirm it in Billing and Cost Management.

## Pilot verification and load behavior

Use synthetic data only. Generate the deterministic 100k file, authenticate as
the provisioned merchant, upload it, poll the job, and compare the completed
analytics with the local verified engine. Run three concurrent uploads and a
signed duplicate webhook burst. Record API acceptance latency, QUEUED→RUNNING
delay, total analysis time, ECS memory, RDS CPU/connections, and error/DLQ count.
Do not load-test Stripe APIs.

AWS smoke/load results remain blocked until the pilot stack, membership, and
Stripe sandbox settings are deployed and configured.
