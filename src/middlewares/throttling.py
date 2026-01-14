from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Enhanced throttling middleware with:
    - Per-user message rate limiting
    - Burst protection
    - Download-specific rate limits
    - Informative cooldown messages
    """
    
    def __init__(
        self,
        redis: Redis,
        rate_limit: int = 2,           # Messages per window
        rate_window: int = 1,           # Window in seconds
        download_limit: int = 5,        # Downloads per window
        download_window: int = 60,      # Download window in seconds
        burst_limit: int = 10,          # Max burst messages
        burst_window: int = 10          # Burst window in seconds
    ):
        self.redis = redis
        self.rate_limit = rate_limit
        self.rate_window = rate_window
        self.download_limit = download_limit
        self.download_window = download_window
        self.burst_limit = burst_limit
        self.burst_window = burst_window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        
        # Check burst limit (anti-spam)
        burst_key = f"burst:{user_id}"
        burst_count = await self.redis.incr(burst_key)
        if burst_count == 1:
            await self.redis.expire(burst_key, self.burst_window)
        
        if burst_count > self.burst_limit:
            if burst_count == self.burst_limit + 1:
                await event.answer(
                    "🚫 Обнаружен спам! Подождите 10 секунд.",
                    disable_notification=True
                )
            logger.warning(f"Burst limit exceeded for user {user_id}")
            return

        # Check regular rate limit
        rate_key = f"rate:{user_id}"
        count = await self.redis.incr(rate_key)
        if count == 1:
            await self.redis.expire(rate_key, self.rate_window)
        
        if count > self.rate_limit:
            if count == self.rate_limit + 1:
                await event.answer(
                    "⏳ Слишком быстро! Подождите секунду.",
                    disable_notification=True
                )
            return

        return await handler(event, data)
    
    async def check_download_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Check if user can perform download.
        
        Returns:
            (allowed: bool, remaining_seconds: int)
        """
        key = f"downloads:{user_id}"
        count = await self.redis.incr(key)
        
        if count == 1:
            await self.redis.expire(key, self.download_window)
        
        if count > self.download_limit:
            ttl = await self.redis.ttl(key)
            return False, max(0, ttl)
        
        return True, 0
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get current rate limit stats for user."""
        downloads_key = f"downloads:{user_id}"
        rate_key = f"rate:{user_id}"
        
        downloads = await self.redis.get(downloads_key)
        downloads_ttl = await self.redis.ttl(downloads_key)
        rate = await self.redis.get(rate_key)
        
        return {
            "downloads_used": int(downloads) if downloads else 0,
            "downloads_limit": self.download_limit,
            "downloads_reset_in": max(0, downloads_ttl),
            "rate_used": int(rate) if rate else 0,
            "rate_limit": self.rate_limit
        }

