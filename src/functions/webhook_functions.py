import os
from datetime import datetime, timezone, timedelta
import azure.functions as func
import stripe
from src.container import get_container
from src.services.usage_service import UsageService

# Secret and webhook signing key from environment
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

stripe.api_key = STRIPE_SECRET_KEY

async def handle_subscription_update(customer_id, new_tier, usage_svc, cosmos):
    """
    Find the user by Stripe customer ID, update their tier in usage and user profile.
    """
    # Lookup user
    users = await cosmos.query_items(
        container_name=cosmos.users_container,
        query="SELECT * FROM c WHERE c.stripeCustomerId = @customer_id",
        parameters=[{"name": "@customer_id", "value": customer_id}],
    )
    if not users:
        return False
    user = users[0]
    user_id = user["id"]
    await usage_svc.set_tier(user_id, new_tier)
    # Update user profile record for fast front-end access (if tier field also lives here)
    await cosmos.update_user(user_id, {"subscriptionTier": new_tier})
    return True

async def handle_subscription_downgrade_after_grace(customer_id, usage_svc, cosmos):
    # Downgrade after 3-day failed window (already expired or deleted)
    await handle_subscription_update(customer_id, "free", usage_svc, cosmos)

async def stripe_webhook(req: func.HttpRequest) -> func.HttpResponse:
    payload = req.get_body()
    sig_header = req.headers.get('stripe-signature')
    if not STRIPE_WEBHOOK_SECRET:
        return func.HttpResponse("Stripe webhook secret not set", status_code=500)
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return func.HttpResponse("Invalid payload", status_code=400)
    except stripe.error.SignatureVerificationError:
        return func.HttpResponse("Invalid signature", status_code=400)

    # Set up service/DB
    container = get_container()
    cosmos = container.get_database_service()
    usage_svc = UsageService(cosmos)

    # Core event parsing
    event_type = event["type"]
    data = event["data"]["object"]

    # Map Stripe price/metadata to tier (adjust as app evolves)
    TIER_LOOKUP = {
        os.environ.get("STRIPE_PRICE_ID"): "pro",
        os.environ.get("STRIPE_EDU_PRICE_ID", ""): "educator",
    }

    # Handle events
    if event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        price_id = None
        # Look for price ID
        lines = data.get("display_items") or []
        if not lines and data.get("subscription"):
            # Fetch using Stripe API (need expanded session or look up subscription object)
            try:
                sub = stripe.Subscription.retrieve(data["subscription"])
                price_id = sub["items"]["data"][0]["price"]["id"]
            except Exception:
                price_id = None
        else:
            price_id = lines[0]['price']['id'] if lines else None
        new_tier = TIER_LOOKUP.get(price_id, "pro")
        await handle_subscription_update(customer_id, new_tier, usage_svc, cosmos)
    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        # Active or not, check status and price
        customer_id = data.get("customer")
        status = data.get("status")
        price_id = data["items"]["data"][0]["price"]["id"] if data.get("items") else None
        new_tier = TIER_LOOKUP.get(price_id, "pro")
        if status == "active":
            await handle_subscription_update(customer_id, new_tier, usage_svc, cosmos)
        elif status in ("canceled", "unpaid", "incomplete_expired"):
            await handle_subscription_update(customer_id, "free", usage_svc, cosmos)
    elif event_type == "customer.subscription.deleted":
        # Downgrade to free after 3 days
        customer_id = data.get("customer")
        canceled_at = data.get("canceled_at")
        cancel_time = None
        if canceled_at:
            cancel_time = datetime.fromtimestamp(canceled_at, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        if cancel_time and now - cancel_time < timedelta(days=3):
            # Wait for grace, set a timer for 3 days? For stateless backend, just re-check in next webhook or polling
            # For now: don't downgrade yet (next webhook will re-trigger after 3 days)
            pass
        else:
            await handle_subscription_downgrade_after_grace(customer_id, usage_svc, cosmos)
    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        # Check if this is the final failure after 3+ days overdue, downgrade to free
        # Stripe will later send 'customer.subscription.deleted' after dunning
        # For now: do nothing, wait for deletion event
        pass
    else:
        # Irrelevant event, ignore
        pass

    return func.HttpResponse("Webhook received", status_code=200)
