# Contributing to PayLens

PayLens handles financial analytics, so clarity and correctness matter more
than cleverness. A change should be understandable from its name, types,
tests, and explanation of *why* it exists.

## Before changing code

1. Read [docs/START-HERE.md](docs/START-HERE.md).
2. Locate the relevant boundary in [docs/CODEBASE-GUIDE.md](docs/CODEBASE-GUIDE.md).
3. Preserve merchant isolation, currency separation, decimal precision, and
   deterministic results.
4. Never place real credentials or customer payment data in fixtures, logs,
   screenshots, commits, issues, or pull requests.

## Commenting standard

Comments should explain purpose, business meaning, a security boundary, or a
non-obvious trade-off. They should not translate every syntax token into
English. Prefer:

```python
# Keep currencies separate so USD and EUR are never added together.
```

Avoid:

```python
# Loop through transactions.
for transaction in transactions:
```

Every production module should begin with a one-sentence purpose. Public
interfaces and non-obvious functions should have docstrings. Names and small
functions should carry the rest of the explanation.

## Behaviour that must remain true

- The same input and configuration produce the same analytics and insights.
- Monetary arithmetic uses `Decimal`, never binary floating-point arithmetic.
- Monetary totals are returned by currency.
- A zero denominator has an explicit, tested result.
- “Failed attempted payment value” is never renamed to “lost revenue.”
- Every data lookup is scoped to the authenticated merchant.
- APIs never return encrypted credentials, decrypted secrets, raw job payloads,
  or OAuth state secrets.
- Duplicate provider events do not duplicate canonical transactions.

## Local verification checklist

Run the checks relevant to the files you changed. Before merging a cross-layer
change, run all of them.

```powershell
# Backend
pytest

# Frontend
cd frontend
npm test
npm run lint
npm run build

# Infrastructure
cd ..\infrastructure
npm run build
npm audit --omit=dev

# Stripe App manifest/scaffold
cd ..\stripe-app
corepack pnpm install --frozen-lockfile
corepack pnpm check
```

CI repeats the backend, frontend, container, and infrastructure checks on every
push to `main` and on pull requests. Deployment is a separate, protected,
manual workflow.

## Commit guidance

Use a short imperative subject that describes the outcome, for example:

```text
docs: explain payment ingestion flow
fix: preserve webhook processing state on failure
feat: add merchant-scoped provider diagnostics
```

Keep generated CSVs, test reports, `.env` files, credentials, caches, build
output, and dependency folders out of Git.
