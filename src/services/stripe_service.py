import os
import stripe

# Setup Stripe with secret key from environment
def get_stripe_client():
    api_key = os.environ.get('STRIPE_SECRET_KEY')
    if not api_key:
        raise RuntimeError('STRIPE_SECRET_KEY not set in environment')
    stripe.api_key = api_key
    return stripe

class StripeService:
    def __init__(self):
        self.stripe = get_stripe_client()
        self.product_id = os.environ.get('STRIPE_PRODUCT_ID')
        self.subscription_price_id = os.environ.get('STRIPE_PRICE_ID')
        self.customer_portal_url = os.environ.get('STRIPE_CUSTOMER_PORTAL_URL')

    async def create_checkout_session(self, user_email, success_url, cancel_url):
        checkout_session = self.stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=['card'],
            line_items=[{
                'price': self.subscription_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return checkout_session.url

    async def create_customer_portal(self, customer_id, return_url):
        session = self.stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url
