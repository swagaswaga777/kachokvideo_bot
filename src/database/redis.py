from redis.asyncio import Redis
from src.config import config

redis_client = Redis.from_url(config.REDIS_URL)
