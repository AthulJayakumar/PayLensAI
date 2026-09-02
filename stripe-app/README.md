# PayLens Stripe App declaration

This directory is the Stripe-generated application scaffold used to declare
PayLens's OAuth callback and minimum read-only permissions.

The manifest requests access to payment intents, charges, disputes, and balance
transaction sources because those records supply payment outcomes, refunds,
disputes, and fees. It does not request permission to create charges or move
money.

No Stripe key belongs in this directory. Local Stripe CLI authentication stays
in the user's private Stripe CLI configuration; deployed credentials stay in
AWS Secrets Manager.

`stripe-app.yaml` currently points to the verified AWS pilot callback. Public
multi-merchant installation remains gated by Stripe business verification.

Run `corepack pnpm check` to build, lint, and test this scaffold.
