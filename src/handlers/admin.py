import csv
import io
import json
import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from src.config import config
from src.database.main import get_session, User, BotSettings
from sqlalchemy import func, select, update
from src.keyboards.admin import admin_menu_keyboard, broadcast_confirm_keyboard
from src.states import AdminState

logger = logging.getLogger(__name__)
router = Router()

def get_admin_ids():
    if not config.ADMIN_IDS: return []
    try:
        return [int(x.strip()) for x in config.ADMIN_IDS.split(',')]
    except ValueError:
        return []

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Open admin panel."""
    from src.services.admin import get_admin_service
    admin_service = get_admin_service()
    
    if await admin_service.is_admin(message.from_user.id):
        await message.answer("👑 Admin Panel", reply_markup=admin_menu_keyboard())

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    """Return to admin menu."""
    await state.clear()
    await callback.message.edit_text("👑 Admin Panel", reply_markup=admin_menu_keyboard())

@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: CallbackQuery):
    await callback.message.delete()

# --- Stats & Export ---

@router.callback_query(F.data == "admin:stats")
async def cb_stats(callback: CallbackQuery):
    async for session in get_session():
        total = await session.scalar(select(func.count(User.id)))
        active = await session.scalar(select(func.count(User.id)).where(User.is_blocked == False))
        blocked = await session.scalar(select(func.count(User.id)).where(User.is_blocked == True))
    
    await callback.message.edit_text(
        f"📊 **Statistics**\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active: {active}\n"
        f"❌ Blocked: {blocked}",
        reply_markup=admin_menu_keyboard()
    )

@router.callback_query(F.data == "admin:export")
async def cb_export(callback: CallbackQuery):
    await callback.answer("⏳ Generating file...")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Telegram ID', 'Username', 'Full Name', 'Joined At', 'Blocked'])

    async for session in get_session():
        result = await session.execute(select(User))
        users = result.scalars().all()
        for user in users:
            writer.writerow([user.id, user.user_id, user.username, user.full_name, user.joined_at, user.is_blocked])
    
    output.seek(0)
    document = BufferedInputFile(output.getvalue().encode(), filename="users.csv")
    
    await callback.message.answer_document(document, caption="📁 User Database")
    await callback.answer()

# --- Maintenance Mode ---

@router.callback_query(F.data == "admin:maintenance")
async def cb_maintenance(callback: CallbackQuery):
    async for session in get_session():
        stmt = select(BotSettings).where(BotSettings.key == "maintenance_mode")
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        
        current_status = False
        if setting and setting.value == "true":
            current_status = True
        
        # Toggle
        new_status = not current_status
        new_value = "true" if new_status else "false"
        
        if setting:
            setting.value = new_value
        else:
            session.add(BotSettings(key="maintenance_mode", value=new_value))
        await session.commit()
        
        status_text = "✅ ON" if new_status else "❌ OFF"
        await callback.answer(f"Maintenance Mode: {status_text}")
        await callback.message.edit_text(f"🔧 Maintenance Mode is now: {status_text}", reply_markup=admin_menu_keyboard())

# --- Channels Management ---

@router.callback_query(F.data == "admin:channels")
async def cb_channels_list(callback: CallbackQuery):
    channels = []
    async for session in get_session():
        result = await session.execute(select(BotSettings).where(BotSettings.key == "required_channels"))
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            try:
                channels = json.loads(setting.value)
            except:
                channels = []
    
    text = "📺 **Required Channels**\n\nThe user must subscribe to these channels to use the bot.\n\n"
    kb = []
    for ch_id in channels:
        try:
            chat = await callback.bot.get_chat(ch_id)
            title = chat.title
            text += f"• {title} (ID: `{ch_id}`)\n"
            kb.append([InlineKeyboardButton(text=f"❌ Remove {title}", callback_data=f"admin:rm_ch:{ch_id}")])
        except Exception:
            text += f"• ID: `{ch_id}` (Bot not admin or invalid)\n"
            kb.append([InlineKeyboardButton(text=f"❌ Remove {ch_id}", callback_data=f"admin:rm_ch:{ch_id}")])

    kb.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="admin:add_channel")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin:menu")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "admin:add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ **Add Channel**\n\n"
        "Forward a message from the channel OR send the Channel ID (e.g. -100123456789).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Cancel", callback_data="admin:channels")]])
    )
    await state.set_state(AdminState.add_channel)

@router.message(AdminState.add_channel)
async def process_add_channel(message: Message, state: FSMContext):
    channel_id = None
    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
    else:
        try:
            channel_id = int(message.text)
        except ValueError:
            await message.answer("Invalid ID. Try again.")
            return

    # Add to DB
    async for session in get_session():
        stmt = select(BotSettings).where(BotSettings.key == "required_channels")
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        
        channels = []
        if setting and setting.value:
            try:
                channels = json.loads(setting.value)
            except: pass
        
        if channel_id not in channels:
            channels.append(channel_id)
            if setting:
                setting.value = json.dumps(channels)
            else:
                session.add(BotSettings(key="required_channels", value=json.dumps(channels)))
            await session.commit()
            await message.answer(f"✅ Channel `{channel_id}` added!")
        else:
            await message.answer("⚠️ Channel already added.")
            
    await state.clear()
    # Return to menu?
    await message.answer("Return to menu -> /admin")

@router.callback_query(F.data.startswith("admin:rm_ch:"))
async def cb_remove_channel(callback: CallbackQuery):
    channel_id_to_remove = int(callback.data.split(":", 2)[2])
    
    async for session in get_session():
        stmt = select(BotSettings).where(BotSettings.key == "required_channels")
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        
        if setting and setting.value:
            channels = json.loads(setting.value)
            if channel_id_to_remove in channels:
                channels.remove(channel_id_to_remove)
                setting.value = json.dumps(channels)
                await session.commit()
                await callback.answer("✅ Removed")
            else:
                await callback.answer("⚠️ Not found")
        else:
            await callback.answer("⚠️ Error")
    
    await cb_channels_list(callback) # Refresh

# --- Broadcast Logic ---

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📢 **Broadcast**\n\nSend the message (text, photo, video) you want to broadcast.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Cancel", callback_data="admin:menu")]])
    )
    await state.set_state(AdminState.broadcast_text) # Using same state name logic

@router.message(AdminState.broadcast_text)
async def process_broadcast_message(message: Message, state: FSMContext):
    # Store message info
    await state.update_data(message_id=message.message_id, chat_id=message.chat.id)
    
    await message.copy_to(chat_id=message.chat.id)
    await message.answer(
        "👆 Preview.\nSend now?",
        reply_markup=broadcast_confirm_keyboard()
    )
    await state.set_state(AdminState.broadcast_confirm)

@router.callback_query(F.data == "broadcast:confirm", AdminState.broadcast_confirm)
async def process_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data['message_id']
    chat_id = data['chat_id']
    
    await callback.message.edit_text("🚀 Broadcasting started...")
    
    sent = 0
    blocked = 0
    errors = 0
    
    async for session in get_session():
        # Get all users
        result = await session.execute(select(User.user_id))
        user_ids = result.scalars().all()
        
        for user_id in user_ids:
            try:
                await callback.bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=msg_id)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
                # Mark as blocked logic (Need separate update query to be efficient, but line-by-line for now)
                # But inside this loop "session" is active. Can we execute update? 
                # Better to use a separate session or execute update directly.
                # Just execute update here:
                await session.execute(update(User).where(User.user_id == user_id).values(is_blocked=True))
                await session.commit()
            except Exception as e:
                errors += 1
                logger.error(f"Broadcast error for {user_id}: {e}")
            
            await asyncio.sleep(0.05) # Rate limit safety
    
    await callback.message.answer(
        f"✅ **Broadcast Completed**\n\n"
        f"📨 Sent: {sent}\n"
        f"🚫 Blocked: {blocked} (marked in DB)\n"
        f"⚠️ Errors: {errors}"
    )
    await state.clear()
