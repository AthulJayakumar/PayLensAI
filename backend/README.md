# PayLens backend

The backend accepts merchant data, validates it, performs deterministic
analytics, stores results, connects Stripe, and exposes secure HTTP endpoints.

The package is intentionally layered:

```text
HTTP routes -> services -> domain/analytics -> repositories/connectors
```

- Routes translate HTTP requests and responses.
- Services coordinate use cases and authorization-aware work.
- Models, analytics, and insights contain provider-independent business rules.
- Repositories hide storage details.
- Connectors hide payment-provider details.
- `main.py` chooses the local or AWS implementations at startup.
- `worker.py` processes durable background jobs.

This separation lets tests replace PostgreSQL, S3, SQS, Cognito, and Stripe
with in-memory or fake implementations without replacing the business logic.

See [../docs/CODEBASE-GUIDE.md](../docs/CODEBASE-GUIDE.md) for a file-by-file
map and [../CONTRIBUTING.md](../CONTRIBUTING.md) for correctness rules.
