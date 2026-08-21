# PayLens frontend

Local TypeScript product interface for the PayLens deterministic analytics API.

## Requirements

- Node.js 22.13 or newer
- The PayLens FastAPI backend running at `http://localhost:8000`

## Run

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`.

Set `NEXT_PUBLIC_API_URL` only when the backend uses another local origin.

## Verify

```powershell
npm test
npm run build
```

The frontend formats API-provided values for display. It does not calculate
financial KPIs, insight severity, or affected values.

