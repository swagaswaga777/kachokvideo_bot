from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def admin_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    """Admin menu. Owner sees additional management buttons."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"))

    builder.row(InlineKeyboardButton(text="🔧 Техработ", callback_data="admin:maintenance"))
    builder.row(InlineKeyboardButton(text="📺 Каналы (ОП)", callback_data="admin:channels"))
    builder.row(InlineKeyboardButton(text="📁 Выгрузить юзеров", callback_data="admin:export"))
    builder.row(InlineKeyboardButton(text="↩️ Закрыть", callback_data="admin:close"))
    return builder.as_markup()

def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="broadcast:confirm"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin:menu"))
    return builder.as_markup()



