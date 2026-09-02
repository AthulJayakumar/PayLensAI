# PayLens AI

PayLens helps a merchant understand how well their online payments are working.
It reads payment records, converts them into one consistent format, calculates
performance figures, and highlights unusual patterns such as a sudden rise in
failed payments or processing costs.

PayLens **does not** collect money, move money, or replace a payment provider.
It is an analytics and monitoring product.

## Start here

You do not need to be a programmer to understand the project:

1. Read [PayLens in plain English](docs/START-HERE.md) for the product story.
2. Read the [codebase guide](docs/CODEBASE-GUIDE.md) to learn what every major
   folder and file is responsible for.
3. Use the [glossary](docs/GLOSSARY.md) whenever an unfamiliar term appears.

Developers should then read [CONTRIBUTING.md](CONTRIBUTING.md) before changing
the project and [SECURITY.md](SECURITY.md) before handling credentials or
merchant data. Product history is summarized in [CHANGELOG.md](CHANGELOG.md).

## What happens to a payment record?

```text
CSV upload or Stripe event
          |
          v
Validate and convert to the common PayLens transaction format
          |
          v
Store merchant-owned data and calculate exact KPIs
          |
          v
Compare periods and segments using deterministic rules
          |
          v
Show structured insights and operational status in the dashboard
```

“Deterministic” means the same input always produces the same result. An AI
model does not decide the numbers, whether an anomaly exists, or its severity.

## Current capabilities

- One provider-neutral transaction format for CSV and Stripe data.
- A deterministic 100,000-row synthetic-data generator with known anomalies.
- Currency-safe KPIs, segmentation, baseline comparison, and seven detectors.
- A FastAPI backend and a TypeScript/React dashboard.
- PostgreSQL persistence with merchant separation and role-based access.
- Stripe sandbox/OAuth connection, historical sync, signed webhooks, refunds,
  disputes, reconciliation, diagnostics, and safe failed-job retries.
- An AWS pilot using ECS, RDS, S3, SQS, Cognito, CloudFront, monitoring,
  encrypted secrets, backups, cost alerts, and reviewed GitHub deployment.

The verified implementation history is documented in [Sprint 1](docs/sprint-1-architecture.md),
[Sprint 2](docs/sprint-2-intelligence-engine.md), [Sprint 3](docs/sprint-3-product-prototype.md),
[Sprint 4](docs/sprint-4-stripe-persistence.md), [Sprint 5](docs/sprint-5-aws-pilot.md),
and [Sprint 6](docs/sprint-6-operational-readiness.md).

## Repository map

| Location | Plain-English purpose |
| --- | --- |
| `backend/app/models/` | Defines what one PayLens transaction looks like. |
| `backend/app/synthetic/` | Creates repeatable fake payment data for testing. |
| `backend/app/analytics/` | Calculates KPIs, segments, and period comparisons. |
| `backend/app/insights/` | Finds anomalies using explicit business rules. |
| `backend/app/api/` | Exposes PayLens features as secure HTTP endpoints. |
| `backend/app/providers/` | Connects provider data, currently Stripe, to PayLens. |
| `backend/app/persistence/` | Stores data in PostgreSQL and raw objects in S3. |
| `frontend/` | Provides the browser interface used by merchants. |
| `infrastructure/` | Describes the AWS pilot as reviewable TypeScript code. |
| `stripe-app/` | Declares the Stripe permissions and OAuth callback. |
| `backend/tests/`, `frontend/tests/` | Prove calculations and user flows still work. |
| `docs/` | Explains architecture, operations, and sprint decisions. |

## Local development

Requirements: Python 3.11+, Node.js 22.13+, Docker, and Docker Compose.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env.local
docker compose up -d postgres
alembic upgrade head
```

Replace every placeholder in the copied environment files. The local
frontend key must equal the backend key. Never commit either populated file.

Start the backend:

```powershell
python -m uvicorn app.api.main:app --app-dir backend --reload --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Interactive API documentation is available at
`http://localhost:8000/docs`.

## Verification

```powershell
# Backend unit and integration tests
$env:PAYLENS_TEST_DATABASE_URL="postgresql+psycopg://paylens:<local-password>@localhost:5432/paylens"
pytest

# Frontend tests, code checks, and production build
cd frontend
npm test
npm run lint
npm run build

# AWS infrastructure TypeScript compilation
cd ..\infrastructure
npm run build
```

Stripe tests use fake provider responses and require no real Stripe secret.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete pre-commit checklist.

## Generate safe test data

```powershell
paylens-generate --count 100000 --seed 20260822 --output synthetic-data/paylens-transactions.csv
python backend/scripts/verify_sprint3.py --input synthetic-data/paylens-transactions.csv
```

Generated datasets and result reports are intentionally excluded from Git.

## Not implemented yet

PayPal, Adyen, Bedrock/LLM explanations, the Chrome extension, payment routing,
and payment execution remain outside the current product. Multi-merchant
Stripe OAuth is still gated by Stripe business verification.
