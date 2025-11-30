from redis import Redis


async def get_redis_client() -> Redis:
    """Dependency to get Redis client."""
    redis_client: Redis = Redis(
        host='localhost',
        port=6379
    )

    try:
        yield redis_client
    finally:
        redis_client.close()
