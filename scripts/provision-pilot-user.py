"""Bind an existing Cognito user to one PayLens merchant after migrations."""
import argparse
from app.api.auth import MerchantRole
from app.persistence.database import create_engine_from_url
from app.persistence.pilot_repository import SQLPilotRepository

parser = argparse.ArgumentParser()
parser.add_argument("--database-url", required=True)
parser.add_argument("--subject", required=True)
parser.add_argument("--email", required=True)
parser.add_argument("--merchant-id", required=True)
parser.add_argument("--merchant-name", required=True)
parser.add_argument("--role", choices=[role.value for role in MerchantRole], default="OWNER")
args = parser.parse_args()
SQLPilotRepository(create_engine_from_url(args.database_url)).add_membership(args.subject, args.merchant_id, args.merchant_name, MerchantRole(args.role), args.email)
