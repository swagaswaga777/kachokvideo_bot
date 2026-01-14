from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, InlineKeyboardMarkup, InlineKeyboardButton
from src.config import config
import logging
import json
from src.database.main import get_session, BotSettings
from sqlalchemy import select

logger = logging.getLogger(__name__)

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Only check for Messages (commands/text)
        if not isinstance(event, Message):
            return await handler(event, data)

        # Get channels from DB
        channels = []
        async for session in get_session():
            result = await session.execute(select(BotSettings).where(BotSettings.key == "required_channels"))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                try:
                    channels = json.loads(setting.value)
                except:
                    channels = []
        
        if not channels:
            return await handler(event, data)

        user = event.from_user
        bot = data['bot']
        
        not_subscribed = []

        for channel_id in channels:
            try:
                # channel_id can be int or str
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user.id)
                if member.status in ["left", "kicked"]:
                    not_subscribed.append(channel_id)
            except Exception as e:
                # If bot is not admin or channel invalid
                logger.error(f"Sub check error for {channel_id}: {e}")
                # Optional: Remove invalid channel from DB? For now just ignore
                pass
        
        if not_subscribed:
            # Generate buttons
            kb_list = []
            for ch_id in not_subscribed:
                try:
                    chat = await bot.get_chat(ch_id)
                    invite_link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else None
                    if invite_link:
                        kb_list.append([InlineKeyboardButton(text=f"Subscribe {chat.title}", url=invite_link)])
                except:
                    pass
            
            # Add "I Subscribed" button? Or just "Try Again" (user sends msg again)
            # Middleware blocks handler, so user has to retry interaction.
            
            if kb_list:
                await event.answer(
                    "⛔️ **Access Denied!**\n\n"
                    "You must subscribe to our sponsor channels to use the bot.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list)
                )
                return

        return await handler(event, data)
