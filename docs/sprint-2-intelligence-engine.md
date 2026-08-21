# Sprint 2 architecture — PayLens Intelligence Engine

## Scope

Sprint 2 transforms canonical `PayLensTransaction` records into deterministic
merchant payment intelligence. It contains no provider API, payment execution,
database, frontend, cloud, or LLM integration.

```text
Canonical CSV / PayLensTransaction records
                    |
                    v
          KPI and segmentation engine
                    |
                    v
          Baseline/current contexts
                    |
                    v
       Deterministic modular detectors
                    |
                    v
           Structured PayLens insights
```

## KPI definitions and denominators

Rates are represented internally as fractions: `0.08` means 8%. Calculations
use `Decimal` and are rounded to six decimal places.

| KPI | Definition / denominator |
| --- | --- |
| Transaction count | All canonical payment attempts. |
| Attempted payment value | Sum of `amount` for all attempts, per currency. |
| Successful payment value | Sum of `gross_amount` where status is `SUCCEEDED`, per currency. |
| Failed attempted payment value | Sum of `amount` where status is `FAILED`, per currency. This is not lost revenue. |
| Success rate | Successful transaction count / all transaction attempts. |
| Failure rate | Failed transaction count / all transaction attempts. |
| Average transaction value | Attempted value / attempt count in the same currency. |
| Refund amount | Sum of refund amounts, per currency. |
| Refund rate | Transactions with non-`NONE` refund status / successful transaction count. |
| Dispute amount | Sum of dispute amounts, per currency. |
| Dispute rate | Transactions with non-`NONE` dispute status / successful transaction count. |
| Processing fees | Sum of canonical processing fees, per currency. |
| Provider fees | Sum of provider fees, per currency. |
| Total payment cost | Processing fees + provider fees + other cost, per currency. |
| Effective payment cost percentage | Total payment cost / successful processed value in the same currency. |

Count-based zero denominators return zero. Effective cost has no meaningful
denominator when successful value is zero, so it returns `null` for that currency.

Amounts are never totalled across currencies. Until PayLens has explicit FX and
reporting-currency rules, GBP, USD, EUR, CAD, and AUD remain separate.

## Segmentation

The generic grouping engine supports provider, payment method, card network,
issuer country, currency, failure category, and day/week/month. Dimensions can be
combined in arbitrary order, including Mastercard + US, Stripe + Mastercard, and
Stripe + US + Mastercard. Missing optional fields are retained as
`NOT_AVAILABLE` instead of silently dropping records.

## Baseline comparison

The comparison engine accepts explicit baseline and current populations. The
pipeline uses all records before `current_start` as historical baseline and the
half-open `[current_start, current_end)` interval as current.

Failure comparison returns baseline/current rates, absolute difference, relative
change, current failed attempted value by currency, and both period counts.
Relative change is `null` when the baseline rate is zero.

## Detector architecture

Every detector implements the same interface and consumes calculated
`DetectionContext` objects. Built-in categories are:

- `FAILURE_SPIKE`
- `HIGH_FAILURE_SEGMENT`
- `HIGH_PAYMENT_COST`
- `PROVIDER_COST_DIFFERENCE`
- `REFUND_SPIKE`
- `DISPUTE_SPIKE`
- `PAYMENT_METHOD_UNDERPERFORMANCE`

Thresholds enforce minimum baseline/current samples, absolute rate thresholds,
and meaningful absolute/relative changes. Small samples are suppressed. Failure
detectors select root provider/country segments and sufficiently large
network-country localisations; redundant child segments are suppressed when an
existing root finding explains them.

Each insight contains a stable ID, type, severity, segment, metric,
baseline/current value, absolute/relative change, relevant currency-specific
affected amounts, sample counts, deterministic confidence, and evidence.

## Severity

Severity is code-driven. It scores:

- relative magnitude of change;
- current rate;
- largest currency-specific affected value (currencies are not added);
- sample size.

Samples below 100 are always `LOW`. Larger evidence scores map deterministically
to `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`. Confidence is a reproducible evidence
score and must not be described as a statistical probability.

## Verified 100,000-record result

With seed `20260822` and the Sprint 1 anomaly profile, the 16–30 June current
window generates focused findings for:

- Stripe failure spike;
- Germany failure spike;
- US Mastercard failure spike;
- PayPal high cost and provider cost difference in five currencies;
- Visa/GB refund spike;
- Adyen/US dispute spike.

The integration test also asserts the absence of obvious unrelated cost, refund,
dispute, and payment-method findings.

## Known limitations

- One explicit current window is compared with all earlier history; detectors do
  not yet find independent change points for anomalies beginning on different dates.
- Thresholds are deterministic product defaults, not formal statistical tests.
- Seasonal/day-of-week effects are not modelled.
- Multiple currencies are not converted to one merchant reporting currency.
- Detector output is not persisted or acknowledged/suppressed per merchant.
- CSV validation currently loads canonical objects into memory.

