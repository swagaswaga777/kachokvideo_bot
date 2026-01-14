"""
Handlers for scheduled downloads.
"""

import uuid
import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.states import ScheduleState
from src.services.scheduler import get_scheduler, get_preset_time, format_scheduled_time
from src.keyboards.schedule import (
    schedule_keyboard, scheduled_list_keyboard,
    confirm_schedule_keyboard, download_or_schedule_keyboard
)
from src.database.redis import redis_client
from src.utils.i18n import get_text

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("schedule:"))
async def show_schedule_options(callback: CallbackQuery):
    """Show scheduling time options."""
    short_id = callback.data.split(":", 1)[1]
    
    # Verify URL exists
    url = await redis_client.get(f"link:{short_id}")
    if not url:
        await callback.answer("❌ Ссылка истекла", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⏰ **Отложенная загрузка**\n\n"
        "Выберите, когда скачать видео:",
        reply_markup=schedule_keyboard(short_id),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("sched:"))
async def handle_schedule_preset(callback: CallbackQuery, state: FSMContext):
    """Handle schedule preset selection."""
    parts = callback.data.split(":")
    preset = parts[1]
    short_id = parts[2]
    
    # Cancel button
    if preset == "cancel":
        await callback.message.delete()
        await callback.answer("Отменено")
        return
    
    # Custom time - ask for input
    if preset == "custom":
        await state.update_data(schedule_short_id=short_id)
        await state.set_state(ScheduleState.waiting_for_time)
        
        await callback.message.edit_text(
            "📅 **Укажите время**\n\n"
            "Отправьте время в формате:\n"
            "• `14:30` — сегодня в 14:30\n"
            "• `завтра 10:00` — завтра в 10:00\n"
            "• `5` — через 5 минут\n\n"
            "Или нажмите /cancel для отмены",
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    # Get scheduled time from preset
    scheduled_time = get_preset_time(preset)
    
    # Get URL
    url_bytes = await redis_client.get(f"link:{short_id}")
    if not url_bytes:
        await callback.answer("❌ Ссылка истекла", show_alert=True)
        return
    url = url_bytes.decode()
    
    # Schedule the download
    scheduler = get_scheduler()
    task_id = str(uuid.uuid4())[:8]
    
    await scheduler.schedule_download(
        task_id=task_id,
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        url=url,
        scheduled_time=scheduled_time,
        quality="max"
    )
    
    time_str = format_scheduled_time(scheduled_time)
    
    await callback.message.edit_text(
        f"✅ **Загрузка запланирована!**\n\n"
        f"⏰ Время: {time_str}\n"
        f"🔗 {url[:50]}{'...' if len(url) > 50 else ''}\n\n"
        f"Вы получите уведомление, когда видео будет готово.",
        parse_mode="Markdown"
    )
    await callback.answer(f"Запланировано на {time_str}")


@router.message(ScheduleState.waiting_for_time)
async def process_custom_time(message: Message, state: FSMContext):
    """Process custom time input."""
    text = message.text.strip().lower()
    
    # Cancel
    if text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
        return
    
    now = datetime.now()
    scheduled_time = None
    
    try:
        # Parse different formats
        if text.isdigit():
            # Just minutes: "5" -> 5 minutes from now
            minutes = int(text)
            if 1 <= minutes <= 1440:  # Max 24 hours
                scheduled_time = now + timedelta(minutes=minutes)
        
        elif "завтра" in text:
            # "завтра 10:00"
            time_part = text.replace("завтра", "").strip()
            if ":" in time_part:
                hour, minute = map(int, time_part.split(":"))
                scheduled_time = (now + timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
        
        elif ":" in text:
            # "14:30" -> today at 14:30
            hour, minute = map(int, text.split(":"))
            scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If time already passed today, schedule for tomorrow
            if scheduled_time <= now:
                scheduled_time += timedelta(days=1)
                
    except (ValueError, IndexError):
        pass
    
    if not scheduled_time:
        await message.answer(
            "❌ Не удалось распознать время.\n\n"
            "Попробуйте: `14:30` или `5` (минут) или `завтра 10:00`",
            parse_mode="Markdown"
        )
        return
    
    # Get stored short_id
    data = await state.get_data()
    short_id = data.get("schedule_short_id")
    
    if not short_id:
        await state.clear()
        await message.answer("❌ Сессия истекла. Отправьте ссылку заново.")
        return
    
    # Get URL
    url_bytes = await redis_client.get(f"link:{short_id}")
    if not url_bytes:
        await state.clear()
        await message.answer("❌ Ссылка истекла")
        return
    url = url_bytes.decode()
    
    # Schedule
    scheduler = get_scheduler()
    task_id = str(uuid.uuid4())[:8]
    
    await scheduler.schedule_download(
        task_id=task_id,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        url=url,
        scheduled_time=scheduled_time,
        quality="max"
    )
    
    time_str = format_scheduled_time(scheduled_time)
    
    await message.answer(
        f"✅ **Загрузка запланирована!**\n\n"
        f"⏰ Время: {time_str}\n\n"
        f"Вы получите уведомление, когда видео будет готово.",
        parse_mode="Markdown"
    )
    
    await state.clear()


@router.callback_query(F.data.startswith("sched_del:"))
async def cancel_scheduled_download(callback: CallbackQuery):
    """Cancel a scheduled download."""
    task_id = callback.data.split(":", 1)[1]
    
    scheduler = get_scheduler()
    success = await scheduler.cancel_scheduled(task_id, callback.from_user.id)
    
    if success:
        await callback.answer("✅ Отменено")
        # Refresh list
        tasks = await scheduler.get_user_scheduled(callback.from_user.id)
        await callback.message.edit_reply_markup(
            reply_markup=scheduled_list_keyboard(tasks)
        )
    else:
        await callback.answer("❌ Не удалось отменить", show_alert=True)


@router.callback_query(F.data == "my_scheduled")
async def show_my_scheduled(callback: CallbackQuery):
    """Show user's scheduled downloads."""
    scheduler = get_scheduler()
    tasks = await scheduler.get_user_scheduled(callback.from_user.id)
    
    if tasks:
        text = "📋 **Запланированные загрузки:**\n\n"
        for task in tasks[:5]:
            time_str = format_scheduled_time(task.scheduled_time)
            text += f"• {time_str}\n"
    else:
        text = "📭 У вас нет запланированных загрузок"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=scheduled_list_keyboard(tasks)
    )
