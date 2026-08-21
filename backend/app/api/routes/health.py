from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "paylens-api", "version": "0.3.0"}

