import os
import jwt
import logging
import inspect
from fastapi.concurrency import run_in_threadpool
from functools import wraps
from jwt import PyJWKClient
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from app.lib.structs import APIErrorResponse

load_dotenv()

logger = logging.getLogger("uvicorn")

# --- Configuration ---
CLERK_ISSUER = os.getenv("CLERK_ISSUER")
if not CLERK_ISSUER:
    raise ValueError("CLERK_ISSUER not set in .env file")

JWKS_URL = f"{CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json"
jwks_client = PyJWKClient(JWKS_URL)


def validate_token_logic(token: str):
    """
    Internal helper to decode and verify the JWT.
    """
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLERK_ISSUER,
            options={"verify_aud": False}
        )
        return payload

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        logger.warning(f"JWT Validation Failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Clerk Auth Internal Error: {type(e).__name__}: {e}")
        logger.error(f"Failed to fetch JWKS from: {JWKS_URL}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                success=False,
                message=f"Clerk Authentication error: {str(e)}",
                error_code="CLERK_AUTH_ERROR"
            ).model_dump_json(),
        )


def requires_auth(func):
    """
    Decorator to enforce authentication.
    IMPORTANT: The decorated route MUST accept a 'request' argument.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 1. Find the Request object in args or kwargs
        request = kwargs.get("request") or next(
            (arg for arg in args if isinstance(arg, Request)), None)

        if not request:
            return JSONResponse(
                {"error": "System Error: Route must include 'request: Request' parameter"},
                status_code=500
            )

        # 2. Extract Header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401
            )

        token = auth_header.split(" ")[1]

        # 3. Verify Token
        try:
            payload = validate_token_logic(token)
            # Attach user to request.state so it's accessible in the route via request.state.user
            request.state.user = payload
        except HTTPException as e:
            return JSONResponse({"error": e.detail}, status_code=e.status_code)

        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return await run_in_threadpool(func, *args, **kwargs)
    return wrapper


def require_admin(func):
    """
    Decorator to enforce Admin access.
    Must be placed AFTER @requires_auth (or assuming auth is already checked).
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request = kwargs.get("request") or next(
            (arg for arg in args if isinstance(arg, Request)), None)

        if not request:
            return JSONResponse({"error": "System Error: Request object missing"}, status_code=500)

        # Ensure user is authenticated (check if state.user exists)
        if not hasattr(request.state, "user"):
            return JSONResponse({"error": "Authentication required before Admin check"}, status_code=401)

        user = request.state.user
        admin_list = os.getenv("ADMINS", "").split(",")

        # Check identifier
        user_identifier = user.get("email") or user.get(
            "username") or user.get("sub")

        if user_identifier not in admin_list:
            return JSONResponse(
                {"error": "Admin access required"},
                status_code=403
            )

        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return await run_in_threadpool(func, *args, **kwargs)
    return wrapper
