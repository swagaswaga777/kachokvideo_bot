from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def settings_keyboard(quality: str = "mobile") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Language (Placeholder for now, just visual)
    builder.row(InlineKeyboardButton(text="🇷🇺 Язык: Русский", callback_data="settings:lang"))
    
    # Quality Toggle
    q_text = "📱 Мобильное (1080p, H.264)" if quality == "mobile" else "🎬 Максимальное (4K)"
    builder.row(InlineKeyboardButton(text=f"🎥 Качество: {q_text}", callback_data="settings:quality"))
    
    builder.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="settings:close"))
    return builder.as_markup()
