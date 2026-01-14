"""
Keyboards for profile.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def profile_keyboard() -> InlineKeyboardMarkup:
    """Main profile keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="profile:stats"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:main"),
        ],
        [
            InlineKeyboardButton(text="📋 Мои загрузки", callback_data="my_scheduled"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"),
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
