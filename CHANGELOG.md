# PayLens change log

This file summarizes meaningful product changes. Detailed implementation and
verification evidence lives in the linked sprint documents.

## 0.6.0 — Stripe operational readiness

- Added merchant-safe Stripe pipeline diagnostics and failed-job retry.
- Made webhook receipt and successful processing separately visible.
- Added end-to-end payment, refund, dispute, duplicate, and failure tests.
- Added webhook-delay alarms and automated backup/DLQ deployment checks.

See [Sprint 6](docs/sprint-6-operational-readiness.md).

## 0.5.0 — AWS pilot

- Added reviewed AWS infrastructure, Cognito authentication, asynchronous
  queues/workers, monitoring, budgets, backups, and protected GitHub deployment.

See [Sprint 5](docs/sprint-5-aws-pilot.md).

## 0.4.0 — Stripe and persistent data

- Added PostgreSQL repositories, encrypted Stripe credentials, raw provider
  storage, historical synchronization, signed webhooks, and reconciliation.

See [Sprint 4](docs/sprint-4-stripe-persistence.md).

## 0.3.0 — Product prototype

- Added authenticated FastAPI endpoints and the merchant dashboard for CSV
  upload, KPIs, segments, insight lists, and insight evidence.

See [Sprint 3](docs/sprint-3-product-prototype.md).

## 0.2.0 — Intelligence engine

- Added exact KPIs, segmentation, baseline comparison, deterministic severity,
  and seven structured anomaly detectors.

See [Sprint 2](docs/sprint-2-intelligence-engine.md).

## 0.1.0 — Data foundation

- Added the canonical transaction model, validated CSV handling, and the
  deterministic synthetic payment generator.

See [Sprint 1](docs/sprint-1-architecture.md).
