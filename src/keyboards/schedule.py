"""
Keyboards for scheduling downloads.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta


def schedule_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """
    Keyboard for scheduling download time.
    
    Args:
        short_id: Short ID for callback data (stored URL in Redis)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        # Quick presets row 1
        [
            InlineKeyboardButton(text="⏱ 5 мин", callback_data=f"sched:5min:{short_id}"),
            InlineKeyboardButton(text="⏱ 15 мин", callback_data=f"sched:15min:{short_id}"),
            InlineKeyboardButton(text="⏱ 30 мин", callback_data=f"sched:30min:{short_id}"),
        ],
        # Quick presets row 2
        [
            InlineKeyboardButton(text="🕐 1 час", callback_data=f"sched:1hour:{short_id}"),
            InlineKeyboardButton(text="🕑 2 часа", callback_data=f"sched:2hours:{short_id}"),
        ],
        # Special times
        [
            InlineKeyboardButton(text="🌙 Вечером (23:00)", callback_data=f"sched:tonight:{short_id}"),
            InlineKeyboardButton(text="🌅 Утром (08:00)", callback_data=f"sched:morning:{short_id}"),
        ],
        # Custom time
        [
            InlineKeyboardButton(text="📅 Указать время", callback_data=f"sched:custom:{short_id}"),
        ],
        # Cancel
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"sched:cancel:{short_id}"),
        ]
    ])


def scheduled_list_keyboard(tasks: list) -> InlineKeyboardMarkup:
    """
    Keyboard showing user's scheduled downloads.
    
    Args:
        tasks: List of ScheduledTask objects
    """
    buttons = []
    
    for task in tasks[:5]:  # Limit to 5
        time_str = task.scheduled_time.strftime("%H:%M")
        # Truncate URL for display
        url_short = task.url[:30] + "..." if len(task.url) > 30 else task.url
        
        buttons.append([
            InlineKeyboardButton(
                text=f"⏰ {time_str} — {url_short}",
                callback_data=f"sched_view:{task.task_id}"
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=f"sched_del:{task.task_id}"
            )
        ])
    
    if not buttons:
        buttons.append([
            InlineKeyboardButton(text="📭 Нет запланированных загрузок", callback_data="noop")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_schedule_keyboard(short_id: str, preset: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard after scheduling."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"sched_ok:{preset}:{short_id}"),
            InlineKeyboardButton(text="🔙 Изменить", callback_data=f"schedule:{short_id}"),
        ]
    ])


def download_or_schedule_keyboard(short_id: str) -> InlineKeyboardMarkup:
    """
    Keyboard offering download now or schedule for later.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬇️ Скачать сейчас", callback_data=f"dl_now:{short_id}"),
        ],
        [
            InlineKeyboardButton(text="⏰ Отложить", callback_data=f"schedule:{short_id}"),
        ],
        [
            InlineKeyboardButton(text="❌", callback_data=f"delete:{short_id}"),
        ]
    ])
