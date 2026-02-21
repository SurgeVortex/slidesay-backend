import json
import azure.functions as func
from src.services.stripe_service import StripeService

_stripe_service = None

def get_stripe_service():
    global _stripe_service
    if _stripe_service is None:
        _stripe_service = StripeService()
    return _stripe_service

async def create_checkout_session(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        email = body.get('email')
        success_url = body.get('success_url')
        cancel_url = body.get('cancel_url')
        if not (email and success_url and cancel_url):
            return func.HttpResponse(json.dumps({'error': 'Missing required fields'}), status_code=400)
        url = await get_stripe_service().create_checkout_session(email, success_url, cancel_url)
        return func.HttpResponse(json.dumps({'checkout_url': url}), status_code=200, headers={'Content-Type': 'application/json'})
    except Exception as ex:
        return func.HttpResponse(json.dumps({'error': str(ex)}), status_code=500)

async def create_customer_portal(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        customer_id = body.get('customer_id')
        return_url = body.get('return_url')
        if not (customer_id and return_url):
            return func.HttpResponse(json.dumps({'error': 'Missing required fields'}), status_code=400)
        url = await get_stripe_service().create_customer_portal(customer_id, return_url)
        return func.HttpResponse(json.dumps({'portal_url': url}), status_code=200, headers={'Content-Type': 'application/json'})
    except Exception as ex:
        return func.HttpResponse(json.dumps({'error': str(ex)}), status_code=500)
