"""Bind an existing Cognito subject to a PayLens merchant.

This module is packaged into the backend wheel so operators can run it using
the same ECS task definition, private network, and Secrets Manager values as the
API. Database credentials are intentionally not accepted as command arguments.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.api.auth import MerchantRole
from app.persistence.database import create_engine_from_url, database_url_from_environment
from app.persistence.pilot_repository import SQLPilotRepository


def build_parser() -> argparse.ArgumentParser:
    """Describe the non-secret identity and merchant values accepted by the CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Cognito user's immutable sub claim")
    parser.add_argument("--email", required=True, help="Cognito user's verified email")
    parser.add_argument("--merchant-id", required=True, help="Stable internal merchant identifier")
    parser.add_argument("--merchant-name", required=True, help="Merchant display name")
    parser.add_argument(
        "--role",
        choices=[role.value for role in MerchantRole],
        default=MerchantRole.OWNER.value,
        help="Merchant authorization role (default: OWNER)",
    )
    return parser


def provision_membership(
    *,
    subject: str,
    email: str,
    merchant_id: str,
    merchant_name: str,
    role: MerchantRole,
    engine=None,
) -> None:
    """Create or update one membership without exposing database credentials."""

    owned_engine = engine is None
    if engine is None:
        database_url = database_url_from_environment()
        if database_url is None:
            raise RuntimeError(
                "Database configuration is required through DATABASE_URL or DB_HOST settings."
            )
        engine = create_engine_from_url(database_url)

    try:
        SQLPilotRepository(engine).add_membership(
            subject,
            merchant_id,
            merchant_name,
            role,
            email,
        )
    finally:
        if owned_engine:
            engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse operator input and provision the merchant membership."""

    args = build_parser().parse_args(argv)
    provision_membership(
        subject=args.subject,
        email=args.email,
        merchant_id=args.merchant_id,
        merchant_name=args.merchant_name,
        role=MerchantRole(args.role),
    )
    print("Merchant membership provisioned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
