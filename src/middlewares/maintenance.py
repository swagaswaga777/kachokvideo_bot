from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from src.config import config
import logging
from src.database.main import get_session, BotSettings
from sqlalchemy import select

logger = logging.getLogger(__name__)

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        # Check if admin
        admins = [int(aid.strip()) for aid in config.ADMIN_IDS.split(",") if aid.strip()]
        if user_id in admins:
            return await handler(event, data)

        # Check maintenance mode
        async for session in get_session():
            result = await session.execute(select(BotSettings).where(BotSettings.key == "maintenance_mode"))
            setting = result.scalar_one_or_none()
            if setting and setting.value == "true":
                await event.answer("⚠️ **Maintenance Mode**\n\nThe bot is currently undergoing maintenance. Please try again later.")
                return

        return await handler(event, data)
