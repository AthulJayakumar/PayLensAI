from fastapi import APIRouter, Depends, Header, Request

from app.api.dependencies import get_provider_service
from app.api.services.providers import ProviderService
from app.providers.models import JobType


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    payload = await request.body()
    jobs = getattr(request.app.state, "job_service", None)
    if jobs is None:
        return service.process_webhook(payload, stripe_signature)
    if not service.webhook_secret:
        from app.api.errors import APIError
        raise APIError(status_code=503, code="STRIPE_WEBHOOK_NOT_CONFIGURED", message="Stripe webhook verification is not configured.")
    try:
        event = service._configured_connector().verify_webhook(payload, stripe_signature, service.webhook_secret)
    except Exception as error:
        from app.api.errors import APIError
        raise APIError(status_code=400, code="INVALID_WEBHOOK_SIGNATURE", message="The Stripe webhook signature is invalid.") from error
    accepted = service.accept_verified_webhook(event)
    if accepted["status"] == "duplicate":
        return accepted
    job = jobs.enqueue(merchant_id=accepted["merchant_id"], job_type=JobType.WEBHOOK,
                       deduplication_key=f"stripe-webhook:{event['id']}", payload={"event": event})
    return {"status": "queued", "event_id": event["id"], "job_id": job.id}
