# PayLens glossary

| Term | Meaning in PayLens |
| --- | --- |
| Analysis | One saved run over a merchant's normalised transactions. |
| Attempted payment value | The amount associated with all payment attempts, whether they succeeded or failed. |
| Baseline | Earlier data used as the comparison point for a current period. |
| Canonical transaction | PayLens's provider-neutral representation of one payment attempt. |
| Cognito | The AWS service that signs users into the deployed pilot. |
| Connector | Code that communicates with a payment provider such as Stripe. |
| Detector | A deterministic rule that decides whether an insight exists. |
| Dispute | A payment challenged through the card/payment-provider process. |
| DLQ / dead letter queue | A holding queue for jobs that exhausted automatic retries. |
| Effective payment cost | Total payment cost divided by successful processed value, calculated separately per currency. |
| Idempotency | The guarantee that safely repeating the same request or event does not duplicate its effect. |
| Insight | Structured evidence that a payment pattern crossed a detector threshold. |
| KPI | Key performance indicator, such as success rate or processing fees. |
| Merchant | The business that owns a set of PayLens data. |
| Normalisation | Converting a provider-specific record into the common PayLens format. |
| OAuth | A consent flow that lets a merchant authorise access without giving PayLens their password. |
| Provider | A payment platform, currently Stripe in the working connector. |
| Raw object | The original provider payload retained for audit/replay before normalisation. |
| Reconciliation | Checking that provider records and PayLens records agree. |
| Refund | Money returned against a previously successful payment. |
| Repository | A code boundary that reads and writes stored data. |
| Segment | A group such as Stripe + Mastercard + United States. |
| Severity | LOW, MEDIUM, HIGH, or CRITICAL priority assigned by fixed rules. |
| SQS | AWS queueing used for background provider, analysis, and webhook jobs. |
| Webhook | A signed message sent by Stripe when a payment-related record changes. |
| Worker | The background process that consumes queued jobs. |
