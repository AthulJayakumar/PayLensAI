"""Expose the non-secret Cognito settings required by the browser client."""

import os
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/config")
def authentication_config() -> dict:
    """Return public Cognito identifiers only; no credentials or secrets."""
    return {
        "region": os.environ.get("AWS_REGION"),
        "user_pool_id": os.environ.get("COGNITO_USER_POOL_ID"),
        "client_id": os.environ.get("COGNITO_CLIENT_ID"),
        "environment": os.environ.get("PAYLENS_ENV", "local"),
    }
