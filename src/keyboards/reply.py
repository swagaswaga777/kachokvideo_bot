from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from src.utils.i18n import get_text

def main_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text=get_text("btn_download", lang)), KeyboardButton(text=get_text("btn_language", lang))],
        [KeyboardButton(text=get_text("btn_help", lang))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

def language_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇺🇸 English")],
        [KeyboardButton(text="🇪🇸 Español"), KeyboardButton(text="🇨🇳 Chinese")],
        [KeyboardButton(text=get_text("btn_back", lang))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def quality_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text=get_text("btn_quality_360", lang)), KeyboardButton(text=get_text("btn_quality_480", lang))],
        [KeyboardButton(text=get_text("btn_quality_720", lang)), KeyboardButton(text=get_text("btn_quality_1080", lang))],
        [KeyboardButton(text=get_text("btn_quality_max", lang))],
        [KeyboardButton(text=get_text("btn_back", lang))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

