"""Redis fixed-window limits for public credential exchange."""

import time

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.metrics import rate_limit_rejections
from app.settings import Settings


def enforce_token_rate_limit(
    request: Request, settings: Settings, api_key_prefix: str, organization_id: str
) -> None:
    if not settings.redis_url or settings.token_rate_limit_per_minute <= 0:
        return
    client_ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    identities = (
        f"key:{api_key_prefix}",
        f"org:{organization_id}",
        f"ip:{client_ip}",
    )
    redis = Redis.from_url(settings.redis_url, socket_timeout=1, decode_responses=True)
    try:
        pipeline = redis.pipeline(transaction=True)
        for identity in identities:
            key = f"gateway:rate:token:{identity}:{window}"
            pipeline.incr(key)
            pipeline.expire(key, 90)
        counts = pipeline.execute()[::2]
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Rate limit store unavailable") from error
    finally:
        redis.close()
    if any(int(count) > settings.token_rate_limit_per_minute for count in counts):
        rate_limit_rejections.labels("realtime_token").inc()
        raise HTTPException(status_code=429, detail="Realtime token rate limit exceeded")
