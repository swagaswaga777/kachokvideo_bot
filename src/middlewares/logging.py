from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Privacy-safe logging
        update_id = event.update_id if hasattr(event, "update_id") else "unknown"
        user_id = "unknown"
        if hasattr(event, "message") and event.message:
            user_id = event.message.from_user.id
        elif hasattr(event, "callback_query") and event.callback_query:
            user_id = event.callback_query.from_user.id
            
        logger.info(f"Update: {update_id} | User: {user_id}")
        return await handler(event, data)
