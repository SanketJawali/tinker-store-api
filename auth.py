from clerk_backend_api.jwks_helpers import AuthenticateRequestOptions
import httpx
from clerk_backend_api import Clerk
from dotenv import load_dotenv
import os

load_dotenv()


# Auth validation with clerk
def is_signed_in(request: httpx.Request):
    sdk = Clerk(bearer_auth=os.getenv('CLERK_SECRET_KEY'))
    request_state = sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=['http://localhost:3000/']
        )
    )
    return request_state.is_signed_in
