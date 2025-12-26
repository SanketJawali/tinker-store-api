import os
from redis import Redis

async def get_redis_client():
    """Dependency to get Redis client."""
    # Use environment variable for URL, fallback to localhost only for local dev
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    redis_client = Redis.from_url(redis_url, decode_responses=True)

    try:
        yield redis_client
    finally:
        redis_client.close()

