# Sprint 6 — Stripe end-to-end validation and operational readiness

Sprint 6 separates webhook receipt from successful processing and gives each
authenticated merchant a safe diagnostics view. Provider payloads, credentials,
and stored job payloads are never returned by the diagnostics API.

## Acceptance path

1. Stripe signs and sends an event to `/api/webhooks/stripe`.
2. PayLens verifies the exact request bytes, stores the raw event, and creates a
   unique webhook-ledger row with `processed_at = NULL`.
3. The API persists an idempotent background job and acknowledges the event.
4. The worker normalises or refreshes the PaymentIntent and performs a canonical
   upsert keyed by merchant, provider, and provider transaction ID.
5. Only successful or deliberately ignored processing sets `processed_at`.
6. `/api/providers/stripe/diagnostics` exposes the safe event ID, event type,
   receive/process times, canonical count, latest sync, and recent job statuses.

The automated suite covers successful, failed, processing, canceled, refunded,
dispute-created, and dispute-closed events. It also proves duplicate delivery
creates neither a second webhook job nor a second canonical transaction.

## Retry and failure handling

SQS retries each delivery four times before moving it to its dedicated 14-day
dead-letter queue. Failed jobs remain visible in the diagnostics page. Owners
and administrators can request one idempotent manual retry; analysts and viewers
cannot mutate job state. A CloudWatch alarm fires when a webhook has waited more
than five minutes, when a DLQ receives a message, or when the worker logs a job
failure.

## Operator verification

Run the read-only readiness check after deployment:

```powershell
.\scripts\verify-pilot-readiness.ps1 -Environment pilot -Region eu-north-1 -Profile paylens-bootstrap
```

It checks public health, RDS availability/encryption/deletion protection,
backup retention and the latest restorable time, plus the webhook DLQ count.
It does not create or delete infrastructure. The protected deployment workflow
runs the same check with its short-lived GitHub OIDC session after every smoke
test, so local AWS credentials are not required for deployment verification.

A true restore drill still requires restoring a new temporary RDS instance,
running read-only application checks, and then deliberately removing that
temporary instance. Because this creates billable infrastructure and later
deletes it, it remains an explicitly approved operator exercise rather than an
automatic deployment action.
