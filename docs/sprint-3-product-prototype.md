# Sprint 3 architecture — local product prototype

## Product flow

```text
Browser CSV upload
       |
       v
FastAPI size/type boundary (64 MiB)
       |
       v
Temporary local file -> canonical CSV validation -> file deleted
       |
       v
Existing KPI + insight engines
       |
       v
AnalysisRepository (in-memory prototype)
       |
       v
KPI / segment / insight APIs
       |
       v
TypeScript dashboard and deterministic explanation detail
```

No client can submit a local filesystem path. Files are streamed in 1 MiB
chunks, rejected after 64 MiB, validated through the Sprint 2 loader, and removed
from temporary storage in a `finally` block.

## Persistence boundary

`AnalysisRepository` has `save` and `get` operations over `AnalysisRecord`.
`InMemoryAnalysisRepository` is thread-safe and intentionally process-local. A
future PostgreSQL implementation can replace it without changing calculations,
detectors, API response builders, or frontend contracts.

The repository retains validated transactions because segmentation endpoints
support arbitrary approved dimension combinations after upload. Uploaded bytes
and temporary paths are not retained.

## API contracts

- `GET /health`
- `POST /analysis/upload`
- `GET /analysis/{analysis_id}`
- `GET /analysis/{analysis_id}/kpis`
- `GET /analysis/{analysis_id}/segments?dimensions=...`
- `GET /analysis/{analysis_id}/insights`
- `GET /analysis/{analysis_id}/insights/{insight_id}`

Segment dimensions are validated against `SegmentDimension`; one to three unique
dimensions are accepted. Insight filters support severity, type, and provider.
Errors always use an `error.code`, merchant-safe message, and details list.

Money and rate Decimals are serialized as strings. The UI only formats these
values and never recalculates financial metrics or severity. Currency maps remain
separate throughout the API and UI.

## Comparison period

For an upload, the end is the midnight immediately following the newest
transaction date. The current window is the preceding 15 days. Everything
earlier is the baseline. Both boundaries are returned in analysis metadata.

## Explanation boundary

`ExplanationProvider` accepts a structured `Insight`. The current
`TemplateExplanationProvider` generates deterministic sections for what
happened, why it matters, and what to investigate. It makes no unsupported
causal claims and describes failures only as affected attempted payment value.

`BedrockExplanationProvider` can later implement the same interface, but no LLM
or cloud integration exists in Sprint 3.

## Frontend routes

- `/` — CSV selection, status, validation/analysis progress, errors.
- `/analysis/[id]` — KPIs, separate currency cards, insight feed, provider,
  method, network, and country tables.
- `/analysis/[id]/insights/[insightId]` — evidence, baseline/current values,
  affected amounts, and deterministic explanation sections.

## Security and operational boundaries

- Local CORS is limited to ports 3000 on localhost and 127.0.0.1.
- No credentials, provider secrets, raw card data, or uploaded CSVs are logged.
- Analyses disappear when the backend process restarts.
- The prototype has no merchant authentication or tenant isolation yet and must
  not be exposed publicly.

