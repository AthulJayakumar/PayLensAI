from fastapi import APIRouter, Depends, Header, Request

from app.api.dependencies import get_provider_service
from app.api.services.providers import ProviderService


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    return service.process_webhook(await request.body(), stripe_signature)
