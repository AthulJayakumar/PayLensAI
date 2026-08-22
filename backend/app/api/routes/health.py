from fastapi import APIRouter, Request
from sqlalchemy import text


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "paylens-api", "version": "0.5.0"}


@router.get("/health/ready")
def ready(request: Request) -> dict:
    engine = getattr(request.app.state, "database_engine", None)
    if engine is not None:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected" if engine is not None else "local-memory"}
