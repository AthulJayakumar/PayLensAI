# Sprint 1 architecture — EPIC 1: Data Foundation

## Scope

Sprint 1 proves that PayLens can represent and generate provider-neutral payment
data. It does not include payment execution, provider APIs, a database, analytics,
AI, a web API, a dashboard, or AWS infrastructure.

## Data flow

```text
GenerationConfig + anomaly rules
              |
              v
  Synthetic transaction generator
              |
              v
   PayLensTransaction validation
              |
              v
       Streaming CSV export
```

Production connectors will later add a raw-provider-data store before the
normaliser. `raw_data_reference`, `provider_status`, and provider failure fields
reserve the link to source material without embedding sensitive payloads in the
canonical record.

## Canonical transaction schema

`PayLensTransaction` groups fields by purpose:

- Identity/tenancy: PayLens ID, merchant ID, provider IDs and reference.
- Lifecycle: creation, authorisation, settlement, and source timestamps.
- Payment: amount, currency, canonical and provider-native status.
- Instrument: method, card network, funding type, and issuer country.
- Failure: canonical category plus provider-native code and message.
- Financials: gross amount, processing/provider/other costs, and net amount.
- Refund/dispute: independent status, amount, reason, and settlement details.
- Provenance: source type, raw-data reference, availability metadata, and internal
  audit timestamps.

All money fields are non-negative `Decimal` values. Currency and country values
use uppercase ISO-style codes. Timestamps must include a timezone. Optional
provider fields accept null because source coverage differs.

Where null alone is ambiguous, `data_availability` can mark a field as
`AVAILABLE`, `NOT_AVAILABLE`, `NOT_APPLICABLE`, `NOT_PROVIDED`, or `PENDING`.

Payment status is deliberately independent of refund and dispute state. A
successful payment can later be refunded or disputed without rewriting the
original payment outcome.

## Synthetic generation

Generation is deterministic for the same configuration, seed, anomaly order,
and PayLens version. The default date range is fixed instead of using the current
clock. Separate transaction records are yielded lazily for bounded memory use.

Anomaly rules select records by provider, network, country, method, currency,
and/or time window. Probability anomalies replace the matching base rate; fee
anomalies multiply matching provider fees. Supported categories are:

- `FAILURE_SPIKE`
- `NETWORK_SPECIFIC_FAILURE`
- `COUNTRY_SPECIFIC_FAILURE`
- `HIGH_PROVIDER_FEES`
- `REFUND_SPIKE`
- `DISPUTE_SPIKE`

These rules are labels for controlled data generation, not precomputed PayLens
insights. Sprint 2 detectors must discover the effects from transaction data.

## Financial assumptions

- `amount` is attempted payment value, not revenue.
- Fees are synthetic estimates charged only on successful payments.
- `gross_amount` is successful processed value; failed attempts have zero gross.
- `net_amount = gross_amount - payment costs - refunds - disputes`, floored at
  zero for this prototype.
- Refund and dispute rates are transaction-event probabilities, not ratios of
  monetary value.
- Failed attempted value must not be described as lost revenue because retries
  and recovery are not modelled yet.

## Known limitations

- Synthetic provider behaviour is plausible, not contractually accurate pricing.
- Currency values are not converted into a reporting currency.
- A payment gets at most one refund and one dispute record summary.
- Raw provider payload storage and reprocessing are deferred.
- CSV ingestion and provider-specific normalisers are Sprint 2 work.

