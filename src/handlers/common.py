from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.filters import CommandObject
from src.keyboards.reply import main_keyboard
from src.database.main import get_session, User
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from src.utils.i18n import get_text, TRANSLATIONS
from src.utils.ui import send_menu
from aiogram.fsm.context import FSMContext

router = Router()

# Helper to get all button texts for a key
def get_btn_texts(key):
    return set(TRANSLATIONS[key].values())

@router.message(Command(commands=["start"]))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    telegram_id = message.from_user.id
    args = command.args
    
    lang = "ru"
    deep_link_id = None
    
    # Parse deep link for inline download
    if args and args.startswith("dl_"):
        deep_link_id = args[3:]

    async for session in get_session():
        try:
            # Check if user exists
            result = await session.execute(select(User).where(User.user_id == telegram_id))
            user = result.scalar_one_or_none()

            if not user:
                new_user = User(
                    user_id=telegram_id,
                    username=message.from_user.username,
                    full_name=message.from_user.full_name
                )
                session.add(new_user)
                await session.commit()
            else:
                lang = user.language

        except Exception as e:
            pass

    # Handle deep link (inline download)
    if deep_link_id:
        from src.database.redis import redis_client
        url = await redis_client.get(f"inline:{deep_link_id}")
        if url:
            await message.answer(
                f"🔗 Ссылка для скачивания:\n\n{url.decode()}\n\n"
                f"Отправьте её мне для загрузки!"
            )
            return

    await send_menu(message, state, get_text("start_message", lang), reply_markup=main_keyboard(lang))

@router.message(F.text.in_(get_btn_texts("btn_help")))
@router.message(Command(commands=["help"]))
async def cmd_help(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"

    await send_menu(message, state, get_text("help_message", lang), reply_markup=main_keyboard(lang))

from src.states import DownloadState

@router.message(F.text.in_(get_btn_texts("btn_download")))
async def cmd_download_hint(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"
        
    await state.set_state(DownloadState.waiting_for_link)
    await message.answer(get_text("download_hint", lang))
