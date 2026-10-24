import os

from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import get_current_user_token
from core.logging_config import logger

try:
    import stripe
except ImportError:
    # Fallback mock stripe with minimal interface for testing
    class _MockStripe:
        class Checkout:
            class Session:
                @staticmethod
                def create(*args, **kwargs):
                    raise RuntimeError("Stripe not configured")

        class Webhook:
            @staticmethod
            def construct_event(*args, **kwargs):
                raise RuntimeError("Stripe webhook not configured")

    stripe = _MockStripe
from core.config import settings

router = APIRouter(prefix="/payments", tags=["payments"])

from services.billing.billing_plans import CheckoutRequest


@router.post("/checkout")
async def create_checkout_session(
    payload: CheckoutRequest,
    user: dict = Depends(get_current_user_token),
):
    # Issue #1594: manual Authorization-header extraction + duplicate jwt.decode
    # removed. Identity now comes exclusively from the centralized dependency
    # (AuthMiddleware -> api.deps.get_current_user_token), so this endpoint can
    # no longer drift from app-wide auth semantics (revocation checks, algorithm
    # allow-list, secret rotation, test-bypass gating).
    authenticated_user = user.get("sub") or user.get("user_id")
    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Invalid token. Please re-authenticate.")

    if authenticated_user != payload.user_id:
        raise HTTPException(status_code=403, detail="User mismatch")

    try:
        # FINAL-TEST FIX (2026-09-13): SecretStr is always truthy, so the
        # "not configured" branch never ran. Validate the raw key shape instead.
        stripe_key = (
            settings.stripe_api_key.get_secret_value()
            if getattr(settings, "stripe_api_key", None)
            else ""
        )
        if not stripe_key or not stripe_key.startswith(
            ("sk_live_", "sk_test_", "rk_live_", "rk_test_")
        ):
            is_production = os.environ.get("SUPREMEAI_ENV", "local").lower() == "production" or (
                getattr(settings, "env", "local") == "production"
            )
            if is_production:
                logger.critical(
                    "🚨 STRIPE PAYMENT GATEWAY MISCONFIGURED: usable secret key missing in production"
                )
                raise HTTPException(
                    status_code=503,
                    detail="Payment processing unavailable: Stripe not configured",
                )
            logger.warning("Stripe API key not set — returning 503 Service Unavailable (no mock)")
            raise HTTPException(
                status_code=503,
                detail="Stripe not configured. Payment processing unavailable in non-production environments.",
            )

        stripe.api_key = stripe_key
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": payload.price_id,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=payload.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=payload.cancel_url,
            client_reference_id=payload.user_id,
            metadata={"price_id": payload.price_id},
        )
        try:
            from core.observability.posthog_client import posthog_client

            posthog_client.capture(
                distinct_id=payload.user_id,
                event="checkout_session_created",
                properties={"price_id": payload.price_id},
            )
        except Exception as exc:
            # বল মনতবয: PostHog তলমটর বযরথ হল চকআউট পরসস আটকান উচত নয়;
            # তব নরব সযলপ ন কর ডবগ লগ কর হল
            logger.debug(f"PostHog checkout capture failed: {exc}")
        return {"status": "success", "session_id": session.id, "url": session.url}
    except HTTPException:
        # বাংলা: নিজের রেইজ করা HTTPException (যেমন 401/403/503 not-configured)
        # generic 500-এ গুটিয়ে ফেলা ঠিক নয় — ক্লায়েন্ট সঠিক status পাওয়ার কথা।
        raise
    except Exception as e:
        logger.error(f"Failed to create Stripe checkout session: {e}")
        # বাংলা মন্তব্য: সিকিউরিটি ইনফরমেশন লিক এড়াতে জেনেরিক এরর মেসেজ রিটার্ন করা হচ্ছে।
        raise HTTPException(
            status_code=500, detail="Payment processing error. Please contact support."
        ) from e


# বাংলা মন্তব্য: সাবস্ক্রিপশন প্ল্যানগুলোর লিস্ট প্রদান করার জন্য এন্ডপয়েন্ট
@router.get("/plans")
async def get_plans():
    from services.billing.billing_plans import SUBSCRIPTION_PLANS

    return {"plans": SUBSCRIPTION_PLANS}


# বাংলা মন্তব্য: স্ট্রাইপ ওয়েবহুক ইভেন্ট রিসিভ ও যাচাই করার জন্য এন্ডপয়েন্ট
# ⚠️ WARNING: This endpoint only verifies the webhook signature and returns success.
# It does NOT process payments, credit wallets, or activate subscriptions.
# The real payment processing webhook is at /api/billing/webhook/stripe (billing_api.py).
# If Stripe Dashboard is configured to send to this URL, customers will be charged
# but never receive their product — this is a silent revenue leak.
@router.post("/webhook")
async def stripe_webhook_endpoint(request: Request):
    logger.critical(
        "🔴 STRIPE WEBHOOK HIT DEPRECATED ENDPOINT /payments/webhook — this endpoint does NOT process payments. "
        "The correct endpoint is /api/billing/webhook/stripe. Update the Stripe Dashboard webhook URL immediately. "
        "Customers charged via this endpoint will NOT have their wallets credited or subscriptions activated."
    )
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = None
    if settings.stripe_webhook_secret:
        # settings.stripe_webhook_secret is SecretStr, so get its value
        webhook_secret = settings.stripe_webhook_secret.get_secret_value()

    if not webhook_secret or not sig_header:
        # Fail-safe: misconfiguration shouldn't break production/CI; ignore webhook.
        logger.warning("Stripe webhook ignored (missing secret or signature header).")
        return {
            "status": "ignored",
            "reason": "missing_stripe_webhook_secret_or_signature",
        }

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        return {"status": "success", "event_type": event.get("type")}
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        # বাংলা মন্তব্য: সিকিউরিটি ইনফরমেশন লিক এড়াতে জেনেরিক এরর মেসেজ রিটার্ন করা হচ্ছে।
        raise HTTPException(status_code=400, detail="Webhook payload validation failed") from e
