import os
from redis import Redis, AuthenticationError


async def get_redis_client():
    """Dependency to get Redis client."""
    # Use environment variable for URL, fallback to localhost only for local dev
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_username = os.getenv("REDIS_USERNAME", "default")
    redis_password = os.getenv("REDIS_PASSWORD", "")

    # redis_client = Redis.from_url(redis_url, decode_responses=True)

    redis_client = Redis(
        host=redis_url,
        port=14027,
        username=redis_username,
        password=redis_password,
    )

    # Quick ping to test connection
    try:
        if redis_client.ping():
            print("Redis Connected successfully!")
    except AuthenticationError:
        print("Authentication failed. Check password.")
    except Exception as e:
        print(f"Error: {e}")

    try:
        yield redis_client
    finally:
        redis_client.close()
