import json
from azure.functions import HttpRequest, HttpResponse
from src.services.user_service import UserService
from src.utils.auth import require_auth

user_service = UserService()

def get_user_id_from_claims(req: HttpRequest):
    # Assumes claims from validated JWT are set on req.headers['X-User-Id'] or similar
    user_id = req.headers.get("X-User-Id")
    if not user_id:
        raise Exception("Missing user id in request claims")
    return user_id

@require_auth
def get_me(req: HttpRequest) -> HttpResponse:
    user_id = get_user_id_from_claims(req)
    user = asyncio.run(user_service.get_user(user_id))
    if not user:
        # Auto-create profile if missing (first login)
        # Assume we can fetch additional info from claims/req
        user_info = { # Extend here if you want to include more fields
            "email": req.headers.get("X-User-Email"),
            "displayName": req.headers.get("X-User-Name"),
        }
        user = asyncio.run(user_service.ensure_profile(user_id, user_info))
    return HttpResponse(json.dumps(user), mimetype="application/json")

@require_auth
def put_me(req: HttpRequest) -> HttpResponse:
    user_id = get_user_id_from_claims(req)
    updates = json.loads(req.get_body())
    updated = asyncio.run(user_service.update_user(user_id, updates))
    return HttpResponse(json.dumps(updated or {}), mimetype="application/json")

@require_auth
def delete_me(req: HttpRequest) -> HttpResponse:
    user_id = get_user_id_from_claims(req)
    result = asyncio.run(user_service.delete_user(user_id))
    return HttpResponse(json.dumps({"deleted": result}), mimetype="application/json")

# Azure Functions entrypoints
def main(req: HttpRequest):
    if req.method == "GET":
        return get_me(req)
    elif req.method == "PUT":
        return put_me(req)
    elif req.method == "DELETE":
        return delete_me(req)
    return HttpResponse("Method not allowed", status_code=405)
