from aiogram import Router, F
from aiogram.types import Message
from src.keyboards.reply import language_menu_keyboard, main_keyboard
from src.database.main import get_session, User
from sqlalchemy import select, update
from src.utils.i18n import get_text, TRANSLATIONS
from src.utils.ui import send_menu
from aiogram.fsm.context import FSMContext
import logging

logger = logging.getLogger(__name__)

router = Router()

# Helper to get all button texts for a key
def get_btn_texts(key):
    return set(TRANSLATIONS[key].values())

# --- Navigation ---

@router.message(F.text.in_(get_btn_texts("btn_back")))
async def cmd_back(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"

    logger.info(f"User {user_id} clicked BACK. Lang from DB: {lang}. Text: {message.text}")
    await send_menu(message, state, get_text("start_message", lang), reply_markup=main_keyboard(lang))


# --- Language ---

@router.message(F.text.in_(get_btn_texts("btn_language")))
async def cmd_language_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"

    await send_menu(message, state, get_text("language_menu", lang), reply_markup=language_menu_keyboard(lang))

@router.message(F.text.in_({"🇷🇺 Русский", "🇺🇸 English", "🇪🇸 Español", "🇨🇳 Chinese"}))
async def cmd_set_language(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Create mapping
    lang_map = {
        "🇷🇺 Русский": "ru",
        "🇺🇸 English": "en",
        "🇪🇸 Español": "es",
        "🇨🇳 Chinese": "zh"
    }
    
    selected_code = lang_map.get(message.text, "ru")
    logger.info(f"User {user_id} changing lang to {selected_code} (text: {message.text})")
    
    async for session in get_session():
        await session.execute(update(User).where(User.user_id == user_id).values(language=selected_code))
        await session.commit()
    
    # Respond in NEW language and GO TO MAIN MENU (since settings is removed)
    text = get_text("language_set", selected_code).format(lang=message.text)
    # Use Main Keyboard here
    await send_menu(message, state, text, reply_markup=main_keyboard(selected_code))
