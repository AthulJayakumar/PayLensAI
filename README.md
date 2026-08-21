# PayLens AI

PayLens AI is a payment-intelligence platform. It collects payment-provider data,
normalises it into a common model, calculates deterministic metrics, and surfaces
actionable findings. It does **not** process or route payments.

This repository contains the verified **Data Foundation**, **Intelligence Engine**,
and local **Product Prototype** (Sprints 1–3):

- a canonical Pydantic transaction model;
- a deterministic synthetic payment-data generator;
- configurable failure, fee, refund, and dispute anomalies;
- streaming CSV export suitable for 100,000+ rows;
- automated schema and generator tests;
- exact, currency-safe merchant KPIs;
- single and combined segmentation analytics;
- period-over-period baseline comparisons;
- seven modular deterministic insight detectors;
- deterministic severity classification and structured insight output;
- a FastAPI CSV upload and analysis API;
- replaceable in-memory analysis persistence;
- deterministic merchant explanation templates;
- a TypeScript web application for upload, dashboards, performance, and insights.

See [the Sprint 1 architecture](docs/sprint-1-architecture.md) for the schema and
design decisions and [the Sprint 2 architecture](docs/sprint-2-intelligence-engine.md)
for analytics denominators, detection rules, and limitations. See
[the Sprint 3 architecture](docs/sprint-3-product-prototype.md) for API and web
application boundaries.

## Local setup

Python 3.11 or newer is required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## Generate synthetic data

Generate the default 100,000-row dataset with all example anomalies:

```powershell
paylens-generate --count 100000 --seed 20260822 --output synthetic-data/paylens-transactions.csv
```

Equivalent module command:

```powershell
python -m app.synthetic.cli --count 100000 --seed 20260822 --output synthetic-data/paylens-transactions.csv
```

Use a custom anomaly profile:

```powershell
paylens-generate --anomaly-config synthetic-data/anomalies.example.json
```

Generate a baseline dataset without injected anomalies:

```powershell
paylens-generate --no-anomalies --output synthetic-data/baseline.csv
```

The generator writes rows as they are produced rather than holding the entire
dataset in memory. Existing output files are replaced only after generation
completes successfully.

## Run tests

```powershell
pytest
```

## Start the local backend

```powershell
python -m uvicorn app.api.main:app --app-dir backend --reload --port 8000
```

API documentation is available at `http://localhost:8000/docs`.

## Start the local frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Node.js 22.13 or newer is required.

## Analyse synthetic data

```powershell
paylens-analyse `
  --input synthetic-data/paylens-transactions.csv `
  --current-start 2026-06-16T00:00:00Z `
  --current-end 2026-07-01T00:00:00Z `
  --output synthetic-data/sprint2.analysis.json
```

The output contains overall KPIs, structured insights, and separate timings for
CSV validation/loading, KPI calculation, and insight detection.

## Repository layout

```text
backend/app/models/       Canonical enums and PayLensTransaction
backend/app/synthetic/    Generator, anomaly configuration, CSV export, CLI
backend/app/analytics/    KPI, segmentation, comparison, CSV loading, pipeline
backend/app/insights/     Severity, detector interface, detectors, orchestration
backend/app/api/          FastAPI routes, services, repository, explanations
backend/tests/            Deterministic analytics and API tests
frontend/                 TypeScript upload, dashboard, and insight application
synthetic-data/           Generator profiles and ignored generated CSV files
docs/                     Architecture and schema documentation
```

## Verify the 100k product path

```powershell
python backend/scripts/verify_sprint3.py --input synthetic-data/paylens-transactions.csv
```

## Deferred components

PostgreSQL, merchant authentication, live provider connectors, LLM explanations,
payment routing, and AWS infrastructure remain intentionally deferred.

