from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from typing import Optional, Union
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

async def send_menu(
    message: Message, 
    state: FSMContext, 
    text: str, 
    reply_markup: Optional[Union[ReplyKeyboardMarkup, InlineKeyboardMarkup]] = None
):
    """
    Sends a new menu message and deletes the previous one to keep chat clean.
    Also deletes the user's trigger message.
    """
    # 1. Delete User's Message (if exists and possible)
    # try:
    #     await message.delete()
    # except Exception:
    #     pass

    # 2. Get previous bot message ID from state
    data = await state.get_data()
    last_msg_id = data.get("last_bot_msg_id")

    # 3. Delete previous bot message
    if last_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass # Message might be too old or already deleted

    # 4. Send new message
    new_msg = await message.answer(text, reply_markup=reply_markup)

    # 5. Save new message ID
    await state.update_data(last_bot_msg_id=new_msg.message_id)
