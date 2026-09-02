# PayLens frontend

This directory contains the merchant-facing React interface. It deliberately
does not calculate payment KPIs or decide insights; it asks the backend for
typed results and presents them.

- `app/` defines routes such as upload, login, analysis, insight detail, and
  provider management.
- `components/` contains reusable user-interface sections.
- `lib/api.ts` is the single typed HTTP client and authentication boundary.
- `lib/format.ts` formats already-calculated values for people to read.
- `tests/` verifies important states and user flows without calling live AWS or
  Stripe services.

Run `npm test`, `npm run lint`, and `npm run build` before publishing a change.
The `.openai/hosting.json` and Vinext files are retained for compatible preview
and hosting tooling; the verified PayLens pilot itself is deployed through AWS.
