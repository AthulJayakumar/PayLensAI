# Sprint 4 — Stripe sandbox and persistent data foundation

## Stripe architecture decision

PayLens uses **Stripe Apps OAuth 2.0** for new merchant-authorised connections.
It fits software installed on an existing merchant Stripe account: the merchant
selects their account on Stripe, accepts granular read permissions, and Stripe
redirects with a one-time code.

Legacy Connect platform OAuth was rejected. Stripe says it is not recommended
for new Connect platforms, and general `read_only` scope is limited to legacy
extensions. Stripe Apps replaced new Connect extensions and provides OAuth
tokens, rolling refresh tokens, install links, and explicit object permissions.

Official references verified on 22 August 2026:

- <https://docs.stripe.com/stripe-apps/api-authentication/oauth>
- <https://docs.stripe.com/stripe-apps/reference/permissions>
- <https://docs.stripe.com/connect/oauth-standard-accounts>
- <https://docs.stripe.com/connect/oauth-reference>
- <https://docs.stripe.com/api/pagination>
- <https://docs.stripe.com/webhooks/signature>

The sandbox app should request only `payment_intent_read`, `charge_read`,
`dispute_read`, and `balance_transaction_source_read`. Stripe-hosted installation
collects consent. PayLens never collects a Stripe password.

## Authorization and security

1. An authenticated local merchant requests `POST /providers/stripe/authorize`.
2. PayLens creates a random, signed, ten-minute state and stores only its nonce
   hash with merchant ownership and expiry.
3. The browser opens Stripe's
   `https://marketplace.stripe.com/oauth/v2/authorize` install page.
4. Stripe redirects to the configured backend callback with a one-time code.
5. PayLens verifies state signature, expiry, merchant binding and one-time use,
   then exchanges the code at `POST /v1/oauth/token` using the app developer key.
6. Access and rolling refresh tokens are Fernet-encrypted before persistence.
   Access tokens are refreshed shortly before their one-hour expiry.

Persistent mode refuses to start without the local API key, encryption key, and
OAuth state secret. Secrets are environment values only. API routes derive the
merchant from `X-PayLens-Dev-Key`; query/body merchant IDs are never trusted.
Cross-merchant resource lookup returns not found.

## Database schema and migration

| Table | Purpose |
|---|---|
| `merchants` | Organisation ownership root, ready for future memberships |
| `analyses` | Merchant-owned status, source, periods, metadata and performance |
| `analysis_insights` | Persisted structured detector results |
| `canonical_transactions` | Unique merchant/provider/provider-ID canonical inputs |
| `provider_connections` | Connection state, encrypted tokens, sync/webhook metadata |
| `sync_jobs` | Cursor, status, timestamps, counts, safe errors and analysis link |
| `raw_provider_objects` | Original JSONB plus provider/type/id/source/schema metadata |
| `webhook_events` | Unique Stripe event IDs for delivery idempotency |
| `oauth_states` | Hashed, expiring, single-use CSRF nonces |

Derived KPIs are recalculated from canonical transactions. Insights are
persisted because the Sprint requires their historical structured output. The
initial Alembic migration is
`aa4e231fa1b0_create_merchant_provider_persistence_.py`.

JSONB keeps local raw writes transactional and queryable. The
`RawProviderDataStore` interface is independent of SQLAlchemy so S3 can replace
it later without changing connector, normalizer, sync, or webhook services.

## Stripe to PayLens field mapping

| Stripe source | Canonical field | Behaviour |
|---|---|---|
| `payment_intent.id` | `provider_transaction_id` | Stable idempotency/reconciliation key |
| `created` | `transaction_created_at` | UTC epoch conversion |
| `amount`, `currency` | `amount`, `currency` | Minor units, including zero-decimal currencies |
| `status` | `status`, `provider_status` | Native retained; canonical mapped deterministically |
| `last_payment_error` | failure fields | Native code/message retained; category mapped |
| `latest_charge.id` | `provider_reference` | Missing remains `None` |
| payment method details | method/network/funding/country | Wallet/card values mapped when present |
| balance transaction fee | `processing_fee` | No fee fabricated if expansion is unavailable |
| `amount_refunded` | refund fields | Full/partial from actual amounts |
| dispute data | dispute fields | Mapped after lifecycle refresh when available |
| raw object reference | `raw_data_reference` | Points to preserved provider JSON |

Unavailable settlement date, payout reference and provider-fee split remain
`None`/zero with explicit `NOT_AVAILABLE` metadata.

## Historical synchronization

Each request fetches at most 100 PaymentIntents. Stripe's cursor-based
`starting_after` value is saved after each complete page. Raw JSON is written
before normalization; canonical upsert uses the merchant/provider/provider-ID
unique key. Partial failure stores its cursor and a safe exception class. The
same job resumes without duplicating canonical records.

On completion, all merchant Stripe canonical transactions enter the verified
analytics and insight engines. The new analysis is persisted and opens in the
existing dashboard. The prototype executes synchronization inside the API
request; a background worker is deferred.

## Webhooks and reconciliation

`POST /webhooks/stripe` reads untouched bytes and verifies `Stripe-Signature`
with Stripe's official SDK. Invalid signatures are rejected. The raw event is
stored and its Stripe event ID is inserted under a unique constraint before
lifecycle processing, making repeat delivery a safe duplicate response.

Supported lifecycle events:

- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `payment_intent.canceled`
- `payment_intent.processing`
- `charge.refunded`
- `charge.dispute.created`
- `charge.dispute.closed`

Charge/dispute events refresh the related PaymentIntent before canonical
replacement. Events without a usable PaymentIntent reference are preserved and
ignored rather than guessed.

Reconciliation fetches up to 20 pages for the last 30 days, detects duplicate
provider objects, missing canonical records, and material
status/amount/refund/dispute changes, then repairs missing/stale records through
the same raw-store and normalizer path. It supplements webhook delivery.

## Local Stripe sandbox setup

1. Copy `.env.example` to `.env`, copy `frontend/.env.example` to
   `frontend/.env.local`, and replace every placeholder. Generate keys:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Start and migrate PostgreSQL:

   ```powershell
   docker compose up -d postgres
   alembic upgrade head
   ```

3. In Stripe test/sandbox mode, create a public Stripe App with OAuth API
   access. Add the four read permissions above and this exact redirect:
   `http://localhost:8000/providers/stripe/oauth/callback`.

4. Configure the listed PaymentIntent, charge/refund and dispute events for
   `http://localhost:8000/webhooks/stripe`; use Stripe CLI forwarding locally.
   Copy only the client ID, app developer test key, and webhook signing secret
   into local environment values.

5. Start the backend and frontend, open `http://localhost:3000/providers`,
   choose **Connect Stripe**, then **Sync now**.

Automated tests mock Stripe and require no credentials. No Stripe credentials
were available during Sprint 4, so a live sandbox authorization/API call was not
performed.

## Known limitations

- Development auth is a local API key abstraction, not user login/membership.
- Sync and reconciliation are synchronous prototype operations.
- One Stripe connection exists per merchant; one webhook secret is shared.
- Raw JSONB has no retention lifecycle; S3 is deferred.
- Disconnect deletes local encrypted credentials but does not yet revoke the
  grant at Stripe.
- No write permission, payment processing, routing, or execution is present.
