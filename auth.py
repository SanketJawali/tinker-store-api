from functools import wraps
from fastapi.responses import JSONResponse
from clerk_backend_api.jwks_helpers import AuthenticateRequestOptions
import httpx
from clerk_backend_api import Clerk
from dotenv import load_dotenv
import os

load_dotenv()


def get_auth_state(request: httpx.Request):
    sdk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
    request_state = sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000/']
        )
    )
    return request_state


# Auth validation with clerk
def is_signed_in(request: httpx.Request):
    return get_auth_state().is_signed_in


def requires_auth(func):
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        # FastAPI provides request as a parameter if you include it in the handler

        # Convert to httpx.Request because your checker expects that
        httpx_request = httpx.Request(
            method=request.method,
            url=str(request.url),
            headers=request.headers.raw
        )

        if not is_signed_in(httpx_request):
            return JSONResponse(
                {"success": False, "error": "AUTH_FAILED"},
                status_code=401
            )

        return await func(request, *args, **kwargs)
    return wrapper


def require_admin(func):
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        # require_auth must run BEFORE this decorator
        user = getattr(request.state, "user", None)

        if user is None:
            return JSONResponse(
                {"success": False, "error": "AUTH_REQUIRED_BEFORE_ADMIN_CHECK"},
                status_code=401
            )

        admin_list = os.getenv("ADMINS", "").split(",")

        # Clerk user fields: id, email_address, username, etc.
        username = user.username or user.email_addresses[0].email_address

        if username not in admin_list:
            return JSONResponse(
                {"success": False, "error": "NOT_ADMIN"},
                status_code=403
            )

        return await func(request, *args, **kwargs)

    return wrapper
