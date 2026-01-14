"""
Profile handlers.
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from src.database.main import get_session, User
from sqlalchemy import select
from src.keyboards.premium import profile_keyboard
from src.utils.i18n import get_text

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Show user profile."""
    await show_profile(message.from_user.id, message)


@router.callback_query(F.data == "profile:main")
async def cb_profile(callback: CallbackQuery):
    """Show profile via callback."""
    await show_profile(callback.from_user.id, callback.message, edit=True)
    await callback.answer()


async def show_profile(user_id: int, message: Message, edit: bool = False):
    """Display user profile."""
    # Get user data
    async for session in get_session():
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
    
    if not user:
        text = "❌ Профиль не найден"
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return
    
    text = (
        f"👤 **Ваш профиль**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 Имя: {user.full_name or 'Не указано'}\n"
        f"📥 Всего загрузок: {user.total_downloads or 0}\n"
    )
    
    keyboard = profile_keyboard()
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "profile:stats")
async def show_stats(callback: CallbackQuery):
    """Show user statistics."""
    user_id = callback.from_user.id
    
    async for session in get_session():
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
    
    if not user:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    
    joined = user.joined_at.strftime("%d.%m.%Y") if user.joined_at else "—"
    
    text = (
        f"📊 **Ваша статистика**\n\n"
        f"📥 Всего загрузок: {user.total_downloads or 0}\n"
        f"📅 Дата регистрации: {joined}\n"
        f"🌐 Язык: {user.language.upper()}\n"
        f"📹 Качество: {user.quality}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=profile_keyboard(),
        parse_mode="Markdown"
    )
