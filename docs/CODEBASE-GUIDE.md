# PayLens codebase guide

This guide is a map of the working code. It explains the responsibility of
each production file in plain language and shows where to start when changing
one part of the product.

## How to read the code

Python files normally follow this order:

1. A module docstring explains why the file exists.
2. Imports name the capabilities it uses.
3. Models define the shape and validation rules for data.
4. Small functions contain one calculation or transformation.
5. Services coordinate several smaller pieces.

TypeScript/React files follow a similar pattern: types first, small helper
functions next, and the exported screen/component last. AWS CDK files use
named resource sections and comments because their job is to describe a whole
cloud system rather than process one request.

Do not try to understand every file at once. Follow one journey, such as a CSV
upload or Stripe webhook, using the maps below.

## Journey 1: CSV upload to insight

```text
frontend/components/UploadPanel.tsx
  -> backend/app/api/routes/analysis.py
  -> backend/app/api/services/analysis.py
  -> backend/app/analytics/csv_loader.py
  -> backend/app/models/transaction.py
  -> backend/app/analytics/kpis.py
  -> backend/app/insights/engine.py
  -> backend/app/insights/detectors.py
  -> backend/app/persistence/analysis_repository.py
  -> frontend analysis pages and components
```

The frontend sends a file. The API service checks its size and content, the
loader creates canonical transactions, analytics calculate exact results,
detectors generate evidence, and the repository saves the merchant-owned
analysis. The frontend only presents those results.

## Journey 2: Stripe webhook to canonical transaction

```text
backend/app/api/routes/webhooks.py
  -> backend/app/api/services/providers.py
  -> backend/app/jobs.py
  -> AWS SQS webhook queue
  -> backend/app/worker.py
  -> backend/app/providers/stripe/normalizer.py
  -> backend/app/persistence/provider_repository.py
  -> common analytics engine
```

The route accepts the body quickly. The provider service verifies Stripe's
signature and records receipt. The worker processes the queued reference,
stores the raw source, normalises the event, and marks it processed only after
successful completion.

## Journey 3: Browser request and merchant security

```text
frontend/lib/api.ts
  -> backend/app/api/middleware.py
  -> backend/app/api/auth.py
  -> backend/app/api/dependencies.py
  -> one route and service
  -> merchant-scoped repository call
```

The deployed browser sends a Cognito access token. The backend validates it,
loads active merchant membership, and creates a request context. Repository
calls include that merchant identifier. Role checks protect administrative
actions such as retrying failed jobs.

## Backend files

### Common transaction model — `backend/app/models/`

| File | Responsibility |
| --- | --- |
| `transaction.py` | Defines enums and the validated provider-neutral transaction. It enforces uppercase codes, timestamps, amounts, failure fields, refunds, disputes, and fee consistency. |
| `__init__.py` | Provides the model names imported by the rest of the application. |

This is the central contract. Provider adapters may change, but analytics
should continue to receive this format.

### Synthetic data — `backend/app/synthetic/`

| File | Responsibility |
| --- | --- |
| `config.py` | Defines generation probabilities and explicit anomaly windows. Validation prevents impossible configurations. |
| `generator.py` | Produces repeatable transactions from a seed and injects configured failure, refund, dispute, and cost anomalies. |
| `csv_export.py` | Streams canonical records to a temporary file and atomically publishes the completed CSV. |
| `cli.py` | Implements the `paylens-generate` command and its arguments. |
| `__init__.py` | Exposes the generator package's public API. |

The generator is deliberately deterministic: a seed and configuration are a
reproducible test fixture, not random demo data that changes on every run.

### Analytics — `backend/app/analytics/`

| File | Responsibility |
| --- | --- |
| `models.py` | Defines typed KPI, segmented KPI, and baseline-comparison results. |
| `csv_loader.py` | Reads CSV rows, rejects malformed input, and constructs canonical transactions. |
| `kpis.py` | Calculates counts, currency-separated amounts, fees, averages, and rates using exact decimal arithmetic. |
| `segmentation.py` | Groups transactions by one to three dimensions and calculates KPIs for each group. |
| `baseline.py` | Compares current and historical failure performance, including absolute/relative change and affected value. |
| `pipeline.py` | Runs loading, KPIs, and insights in sequence while measuring each stage. |
| `cli.py` | Implements the `paylens-analyse` command. |
| `__init__.py` | Exposes analytics package names. |

Important denominators in `kpis.py`:

- success and failure rate: all payment attempts;
- average transaction value: attempts in the same currency;
- refund and dispute rate: successful payment transactions;
- effective payment cost: successful processed value in the same currency.

### Insight engine — `backend/app/insights/`

| File | Responsibility |
| --- | --- |
| `models.py` | Defines insight type, severity, confidence, segment, evidence, and detector context. |
| `base.py` | Defines the detector interface and shared insight-building helpers. |
| `detectors.py` | Implements the seven built-in deterministic detectors and their thresholds. |
| `severity.py` | Converts magnitude, affected value, and sample size into fixed severity/confidence labels. |
| `engine.py` | Splits baseline/current periods, creates segment combinations, runs detectors, removes duplicates, and sorts results. |
| `__init__.py` | Exposes insight package names. |

Adding a detector should not require changing the API or frontend contract. A
new detector implements the shared interface and returns the same structured
insight model.

### HTTP API — `backend/app/api/`

| File | Responsibility |
| --- | --- |
| `main.py` | Application composition root. It chooses local or AWS authentication, storage, queues, encryption, Stripe mode, middleware, and routes from environment configuration. |
| `auth.py` | Validates either the explicit local development key or deployed Cognito token and returns user/merchant/role context. |
| `middleware.py` | Adds request IDs, structured security logs, security headers, origin checks, rate limiting, and safe error behavior. |
| `dependencies.py` | Supplies authenticated context, repositories, and merchant-owned analyses to routes. |
| `repositories.py` | Defines the analysis-storage interface and its in-memory implementation. |
| `serialization.py` | Converts exact Python result types into lossless API-safe values. |
| `explanations.py` | Converts structured insight evidence into deterministic human-readable wording. |
| `errors/__init__.py` | Defines consistent error codes and installs exception handlers. |

#### API routes — `backend/app/api/routes/`

| File | Responsibility |
| --- | --- |
| `health.py` | Reports process liveness and dependency readiness without exposing secrets. |
| `auth_config.py` | Gives the browser only the non-secret Cognito region and client identifier it needs. |
| `analysis.py` | Creates, queues, lists, and retrieves merchant-owned analyses. |
| `kpis.py` | Returns the stored overall KPI result for an analysis. |
| `segments.py` | Returns requested one-, two-, or three-dimensional segment performance. |
| `insights.py` | Lists, filters, orders, and retrieves structured insights. |
| `providers.py` | Starts Stripe connection/sync, disconnects, reconciles, and returns safe diagnostics. |
| `webhooks.py` | Accepts signature-verified Stripe event bodies and queues processing. |
| `jobs.py` | Returns safe job state and permits role-protected, idempotent retry of failed jobs. |
| `__init__.py` | Marks and documents the route package. |

#### API services — `backend/app/api/services/`

| File | Responsibility |
| --- | --- |
| `analysis.py` | Coordinates upload validation, analytics, persistence, job submission, and audit events. |
| `providers.py` | Coordinates OAuth/sandbox connection, credential storage, sync checkpoints, raw storage, normalisation, webhook lifecycle, reconciliation, diagnostics, and auditing. |
| `__init__.py` | Marks and documents the service package. |

Routes stay small so the services can be tested without an HTTP server.

### Provider integration — `backend/app/providers/`

| File | Responsibility |
| --- | --- |
| `base.py` | Defines provider capabilities without forcing every provider to support every operation. |
| `models.py` | Defines connections, credentials, raw objects, sync jobs, async jobs, reconciliation results, and status enums. |
| `repository.py` | Defines provider persistence operations and supplies an in-memory implementation for tests/local use. |
| `raw_storage.py` | Defines raw provider storage and an in-memory implementation. |
| `s3_storage.py` | Stores encrypted, tenant-separated raw provider objects in S3. |
| `security.py` | Encrypts provider credentials and creates signed, expiring, one-use OAuth state tokens. |
| `stripe/connector.py` | Calls Stripe OAuth and paginated PaymentIntent APIs through a narrow adapter. |
| `stripe/normalizer.py` | Maps Stripe fields, refunds, disputes, cards, failures, and fees into canonical transactions without guessing absent data. |
| `stripe/__init__.py` | Exposes the Stripe connector and normaliser. |
| `__init__.py` | Marks and documents the provider package. |

### Persistence — `backend/app/persistence/`

| File | Responsibility |
| --- | --- |
| `database.py` | Defines SQLAlchemy tables for merchants, memberships, analyses, provider data, jobs, webhook events, and audits; also builds database connections. |
| `analysis_repository.py` | Saves and loads merchant analyses and canonical transactions in PostgreSQL. |
| `provider_repository.py` | Saves connections, encrypted credentials, raw objects, sync checkpoints, webhook state, and reconciliation records. |
| `pilot_repository.py` | Saves identity memberships, asynchronous jobs, and audit events; includes an in-memory equivalent. |
| `__init__.py` | Exposes persistence package names. |

Alembic migrations in `backend/migrations/versions/` are the ordered history of
database schema changes. Never rewrite an already-deployed migration; add a new
one.

### Jobs and administration

| File | Responsibility |
| --- | --- |
| `backend/app/jobs.py` | Creates job records, sends minimal references to the correct SQS queue, stores large uploads in S3, and executes a job once. |
| `backend/app/worker.py` | Long-polls all pilot queues, runs jobs, updates state, and leaves failed messages available for configured retries/DLQ handling. |
| `backend/app/admin/provision_user.py` | Binds an existing Cognito subject to a merchant and role as an audited one-off task. It does not create or reveal passwords. |

## Frontend files

### Routes — `frontend/app/`

| File | Responsibility |
| --- | --- |
| `layout.tsx` | Defines global metadata, stylesheet, and the shared HTML document shell. |
| `page.tsx` | Introduces PayLens and submits a canonical CSV for analysis. |
| `login/page.tsx` | Performs Cognito sign-in and password-reset request/confirmation flows. |
| `providers/page.tsx` | Loads the Stripe connection manager and operational diagnostics. |
| `analysis/[id]/page.tsx` | Loads and displays KPIs, segment tables, insights, and timing for one analysis. |
| `analysis/[id]/insights/[insightId]/page.tsx` | Loads the evidence and explanation for one insight. |
| `globals.css` | Defines brand tokens, layouts, responsive behavior, states, and reusable visual classes. |

### Components — `frontend/components/`

| File | Responsibility |
| --- | --- |
| `AppHeader.tsx` | Shared PayLens navigation and current-analysis context. |
| `UploadPanel.tsx` | Selects a CSV, displays validation/progress, submits it, and waits for an asynchronous job when needed. |
| `DashboardView.tsx` | Composes the main analysis result without owning network requests. |
| `PerformanceTable.tsx` | Displays comparable metrics for any segment dimension. |
| `InsightsFeed.tsx` | Displays prioritised structured insights. |
| `InsightDetailView.tsx` | Displays one insight's segment, evidence, comparison, severity, and explanation. |
| `ProviderConnections.tsx` | Manages Stripe connect, sandbox connect, sync, disconnect, and asynchronous status. |
| `ProviderDiagnostics.tsx` | Displays safe pipeline health and retries eligible failed jobs. |

### Frontend support

| File | Responsibility |
| --- | --- |
| `lib/api.ts` | Owns API URLs, browser authentication, typed request/response contracts, error translation, and job polling. |
| `lib/format.ts` | Formats exact API values for display without recalculating analytics. |
| `tests/frontend.test.tsx` | Verifies important rendering, error, upload, provider, diagnostics, and retry behavior. |
| `tests/setup.ts` | Installs browser-style assertions and cleans the DOM after tests. |
| `vite.config.ts` | Configures Vinext and compatible local/Sites worker bindings. |
| `vitest.config.ts` | Configures the browser-like unit-test environment. |
| `next.config.ts` | Reserved framework configuration boundary. |
| `worker/index.ts` | Cloudflare-compatible worker entry point used by the Sites/Vinext toolchain. |

## AWS infrastructure files

| File | Responsibility |
| --- | --- |
| `infrastructure/bin/paylens.ts` | Chooses the environment and composes the image, application, and cost stacks. |
| `infrastructure/lib/image-repositories-stack.ts` | Creates retained, immutable ECR repositories before image publication. |
| `infrastructure/lib/paylens-pilot-stack.ts` | Defines network, RDS, S3/KMS, SQS/DLQs, Cognito, ECS, load balancing, CloudFront, scaling, alarms, dashboard, and outputs. |
| `infrastructure/lib/cost-controls-stack.ts` | Defines actual/forecast budget notifications in the required AWS region. |
| `infrastructure/iam/*.json` | Documents bootstrap and GitHub deployment policy examples. |

Infrastructure code describes desired state. GitHub Actions assumes a
short-lived AWS role, publishes commit-tagged containers, applies CDK, runs an
explicit database migration, waits for stable services, and verifies health,
backups, encryption, deletion protection, and the webhook DLQ.

## Root configuration and operational scripts

| File | Responsibility |
| --- | --- |
| `.env.example` | Lists local configuration names with safe placeholders. A real `.env` is ignored. |
| `pyproject.toml` | Declares the Python package, dependencies, commands, and pytest settings. |
| `Dockerfile` | Builds the backend/worker production image and bundles the compiled frontend image. |
| `frontend/Dockerfile` | Builds the standalone frontend production image. |
| `compose.yaml` | Starts the local PostgreSQL database with development-only defaults. |
| `alembic.ini` | Points Alembic to migration code and logging configuration. |
| `scripts/run-migrations.sh` | Starts a one-off ECS task and waits for database migration success. |
| `scripts/smoke-aws.sh` | Refreshes ECS services, waits for stability, and probes the public application. |
| `scripts/provision-pilot-user.sh` | Runs the restricted user-to-merchant membership command in ECS. |
| `scripts/verify-pilot-readiness.ps1` | Verifies live health, RDS availability/encryption/backups/protection, and an empty webhook DLQ. |
| `.github/workflows/ci.yml` | Runs backend, frontend, image, and infrastructure checks on pushes/PRs. |
| `.github/workflows/deploy-pilot.yml` | Performs the manually confirmed, protected pilot deployment. |

## Stripe App files

`stripe-app/stripe-app.yaml` is the important human-reviewed file. It declares
the application name, OAuth callback, and read-only Stripe permissions. The
remaining files are the Stripe-supported TypeScript workspace, lint, formatting,
and test configuration used to validate that manifest.

No API key, webhook secret, access token, or password should ever appear in
this folder.

## Tests

Backend tests are grouped by capability rather than mirroring every source
file. They use deterministic fixtures and fake boundaries for speed, while the
configured PostgreSQL suite verifies real persistence and migrations. Important
coverage includes:

- canonical validation and CSV round trips;
- synthetic anomaly injection and 100,000-row determinism;
- every KPI, denominator, segment, comparison, detector, and severity tier;
- empty, missing, zero-denominator, and small-sample cases;
- upload/API authorization and merchant isolation;
- Stripe mapping, pagination, checkpoints, signatures, duplicates, refunds,
  disputes, reconciliation, encryption, jobs, retries, and diagnostics;
- PostgreSQL repositories and migrations;
- AWS stack security and deployment contracts.

Tests explain what the system promises. When a business rule changes, update
the rule, its documentation, and its deterministic tests together.
