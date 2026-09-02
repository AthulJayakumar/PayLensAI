# PayLens in plain English

This page explains the whole application without assuming a software
background.

## The problem PayLens solves

A merchant may receive payments through several providers, countries, card
networks, and payment methods. Each provider describes its records differently.
That makes simple questions surprisingly difficult:

- Are more payments failing this week than last week?
- Is Mastercard in the United States behaving differently from other cards?
- Which provider costs more for comparable payments?
- Are refunds or disputes rising?

PayLens turns those different records into one common language and answers the
questions with fixed, reviewable calculations.

## The six parts of the system

### 1. Input

Data arrives either as a CSV file uploaded by a merchant or as authorised
Stripe data. A Stripe connection can import historical records. Stripe
webhooks notify PayLens about later changes such as a successful payment,
refund, or dispute.

### 2. Normalisation

“Normalisation” means translating each provider's terminology into the common
PayLens transaction format. For example, a Stripe `PaymentIntent` becomes a
PayLens transaction with a provider, amount, currency, status, fees, payment
method, card network, country, refund information, and dispute information.

Provider-specific source data is retained separately for audit and replay. It
is not mixed into the analytics contract.

### 3. Storage and ownership

Every stored analysis, provider connection, job, and transaction belongs to a
merchant. Authentication identifies the signed-in person; membership records
identify the merchant and the person's role. Repository methods enforce this
boundary so one merchant cannot request another merchant's records.

The AWS pilot stores structured data in PostgreSQL, raw provider records in an
encrypted S3 bucket, credentials in Secrets Manager, and queued work in SQS.

### 4. Analytics

The analytics engine calculates counts, attempted and successful values,
failure rates, refunds, disputes, fees, and effective payment cost. Money is
kept separate by currency; PayLens never adds dollars and euros together.

Percentages use documented denominators. Failed attempted value is exactly
that—it is not labelled “lost revenue,” because a failed attempt is not proof
that the sale was permanently lost.

### 5. Insights

Detectors compare a current period with earlier baseline data. Each detector
has explicit thresholds and produces structured evidence. The built-in rules
look for failure spikes, high-failure segments, high payment cost, provider
cost differences, refund spikes, dispute spikes, and underperforming payment
methods.

Severity is also rule-based. It considers the size of the change, the payment
value affected, and the sample size. No language model decides severity.

### 6. Dashboard and operations

The browser dashboard lets a merchant upload data, review KPIs and segments,
open individual insights, manage Stripe, and inspect pipeline health. Longer
work runs as a job so the browser does not need to remain connected.

Operational diagnostics show safe metadata such as the latest sync, webhook
processing time, recent jobs, and canonical transaction count. They never
return stored credentials or raw job payloads.

## A Stripe event, step by step

```text
Stripe signs and sends a webhook
        |
        v
PayLens verifies the signature and records receipt
        |
        v
PayLens places a small job reference on the webhook queue
        |
        v
The worker loads the event, stores the raw source, and normalises it
        |
        v
The canonical transaction is inserted or updated idempotently
        |
        v
The webhook is marked processed and new analytics can use it
```

“Idempotently” means receiving the same event twice does not create two
transactions. Failed jobs retry automatically and eventually move to a dead
letter queue for investigation instead of being silently discarded.

## Security model

- Local development uses an explicit development-only API key.
- The deployed pilot uses Amazon Cognito tokens.
- Roles control sensitive operations; retrying failed jobs requires OWNER or
  ADMIN access.
- Provider credentials are encrypted and are never returned by the API.
- Stripe webhook signatures are verified before an event is accepted.
- CloudFront is the public entrance; direct load-balancer requests are denied.
- AWS resources use encryption, backups, deletion protection, alarms, and
  short-lived GitHub OIDC deployment credentials.

## What PayLens deliberately does not do

PayLens does not charge cards, transfer funds, retry customer payments, or
change checkout routing. It reports evidence to a merchant, who remains in
control of business decisions.

For the technical map, continue with [CODEBASE-GUIDE.md](CODEBASE-GUIDE.md).
