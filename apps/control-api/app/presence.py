"""Redis-backed cross-instance partner connection leases."""

from redis.asyncio import Redis


class RedisPresence:
    def __init__(self, redis_url: str, ttl_seconds: int = 30) -> None:
        self.redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        self.ttl_seconds = ttl_seconds

    def _key(self, agent_slug: str) -> str:
        return f"asterisk-ai-gateway:agent:{agent_slug}"

    async def register(self, agent_slug: str, connection_id: str) -> bool:
        return bool(
            await self.redis.set(
                self._key(agent_slug), connection_id, ex=self.ttl_seconds, nx=True
            )
        )

    async def heartbeat(self, agent_slug: str, connection_id: str) -> bool:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """
        return bool(
            await self.redis.eval(
                script, 1, self._key(agent_slug), connection_id, self.ttl_seconds
            )
        )

    async def unregister(self, agent_slug: str, connection_id: str) -> None:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
          return redis.call('del', KEYS[1])
        end
        return 0
        """
        await self.redis.eval(script, 1, self._key(agent_slug), connection_id)

    async def ready(self) -> bool:
        return bool(await self.redis.ping())

    async def close(self) -> None:
        await self.redis.aclose()
