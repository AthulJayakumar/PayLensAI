# Security policy

## Reporting a security problem

Do not open a public GitHub issue containing a vulnerability, credential,
merchant identifier, payment record, or exploit detail. Contact the repository
owner privately and include only the minimum information required to reproduce
the problem.

## Secrets

- Real `.env` files are intentionally ignored by Git.
- Local secrets belong only in `.env` or a secure local credential store.
- AWS secrets belong in AWS Secrets Manager.
- GitHub deployment uses short-lived OIDC credentials, not committed AWS keys.
- Stripe API keys and webhook signing secrets must never appear in source,
  tests, logs, documentation examples, screenshots, or chat.
- If a secret is exposed, rotate it first; removing it from the latest commit
  does not erase it from Git history.

## Data handling

Use synthetic data for development and demonstrations. PayLens stores payment
analytics metadata but should never store full card numbers, CVC values, or
merchant/customer passwords. Raw provider payloads are tenant-isolated and
encrypted at rest in the deployed pilot.

## Access boundaries

Authentication proves who the user is. Merchant membership determines which
business data they may access. Roles determine whether they may perform
sensitive operations. All three checks must remain server-side; a hidden
frontend button is not an authorization control.

## Supported state

This repository is currently a pilot, not a certified payment-processing
system. It does not execute payments and should not be treated as a PCI DSS
card-data environment.
