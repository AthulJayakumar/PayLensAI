# PayLens AI

PayLens is a merchant-owned payment-intelligence product. It normalises CSV or
authorised Stripe data into one canonical model, calculates deterministic
currency-safe metrics, and surfaces structured findings. It does not process or
route payments.

The verified Sprints 1–5 include:

- canonical Pydantic transactions and deterministic 100,000-row synthetic data;
- exact KPIs, segmentation, baselines, seven detectors, and deterministic severity;
- FastAPI upload/provider APIs and a TypeScript dashboard;
- PostgreSQL persistence behind the unchanged `AnalysisRepository` boundary;
- merchant-scoped local development authentication and authorization;
- Stripe Apps OAuth 2.0, paginated/resumable sync, signed webhooks, and reconciliation;
- encrypted provider credentials and S3-replaceable JSONB raw-object storage;
- both CSV and Stripe feeding the same analytics and insight engine.
- reproducible low-cost AWS pilot infrastructure with ECS, RDS, S3, SQS,
  Cognito, CloudFront, audit events, monitoring, budgets, and reviewed CI/CD.

Architecture documentation: [Sprint 1](docs/sprint-1-architecture.md),
[Sprint 2](docs/sprint-2-intelligence-engine.md),
[Sprint 3](docs/sprint-3-product-prototype.md), and
[Sprint 4](docs/sprint-4-stripe-persistence.md), and
[Sprint 5](docs/sprint-5-aws-pilot.md).

## Local setup

Python 3.11+, Node.js 22.13+, Docker, and Docker Compose are required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env.local
docker compose up -d postgres
alembic upgrade head
```

Replace all `.env` placeholders. The frontend's
`NEXT_PUBLIC_PAYLENS_DEV_API_KEY` must match the backend's
`PAYLENS_DEV_API_KEY` for this local-only auth adapter.

Start the backend:

```powershell
python -m uvicorn app.api.main:app --app-dir backend --reload --port 8000
```

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` for CSV or `http://localhost:3000/providers` for
Stripe. API documentation is at `http://localhost:8000/docs`.

## Tests

```powershell
$env:PAYLENS_TEST_DATABASE_URL="postgresql+psycopg://paylens:<your-local-password>@localhost:5432/paylens"
pytest
cd frontend
npm test
npm run lint
npm run build
```

Automated Stripe tests use mocks and require no provider credentials.

## Synthetic data and verification

```powershell
paylens-generate --count 100000 --seed 20260822 --output synthetic-data/paylens-transactions.csv
python backend/scripts/verify_sprint3.py --input synthetic-data/paylens-transactions.csv
```

Use `--anomaly-config synthetic-data/anomalies.example.json` for a custom profile
or `--no-anomalies` for a baseline. Generated CSV and analysis output are ignored.

## Repository layout

```text
backend/app/models/       Canonical transaction contract
backend/app/synthetic/    Generator, anomalies, CSV export, CLI
backend/app/analytics/    KPIs, segmentation, comparison, pipeline
backend/app/insights/     Detectors, severity, structured findings
backend/app/api/          FastAPI auth, routes, services, explanations
backend/app/persistence/  SQLAlchemy schema and PostgreSQL repositories
backend/app/providers/    Provider boundaries and Stripe implementation
backend/migrations/       Alembic migrations
backend/tests/            Deterministic unit and integration tests
frontend/                 CSV, dashboard, insights, and provider UI
docs/                     Sprint architecture and operational documentation
```

## Deferred scope

AWS deployment access, bootstrap permissions, and the GitHub OIDC role design
are documented in `docs/aws-deployment-access.md`.

PayPal, Adyen, Bedrock/LLM explanations, Chrome extension, payment routing, and
payment execution remain deferred. Actual pilot deployment and real Stripe
test-mode verification are tracked as explicit Sprint 5 gates.
