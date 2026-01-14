import re
import os
import aiofiles
from aiogram import Router, F
from aiogram.types import Message, FSInputFile, BufferedInputFile
from src.services.downloader import DownloaderService
from aiogram.enums import ChatAction
from src.database.main import get_session, User
from sqlalchemy import select
from src.utils.i18n import get_text
from src.utils.streaming import should_use_streaming
from src.utils.security import validate_url, validate_file_size
from src.utils.progress import update_progress_message

router = Router()
downloader = DownloaderService()

URL_REGEX = r'(https?://[^\s]+)(?:\s+(\d{1,4})-(\d{1,4}))?'

from aiogram.fsm.context import FSMContext
from src.states import DownloadState

@router.message(DownloadState.waiting_for_link, F.text.regexp(URL_REGEX))
async def handle_media_url(message: Message, state: FSMContext):
    url_match = re.search(URL_REGEX, message.text)
    if not url_match:
        return 
    
    url = url_match.group(1)
    start_time = url_match.group(2)
    end_time = url_match.group(3)
    
    time_range = None
    if start_time and end_time:
        try:
            time_range = (int(start_time), int(end_time))
        except ValueError:
            pass
    
    # Security: Validate URL before processing
    validation = validate_url(url, strict_whitelist=True)
    if not validation.is_valid:
        await message.answer(validation.user_message)
        await state.clear()
        return
    
    user_id = message.from_user.id
    lang = "ru"
    quality = "max"
    
    async for session in get_session():
        # Get Language and Quality
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            lang = user.language
            quality = user.quality or "max"
    
    # YouTube Detection
    is_youtube = "youtube.com" in url or "youtu.be" in url
    
    status_msg = await message.answer("🔍 Анализ ссылки...")
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    try:
        if is_youtube:
             # Just prompt for quality
             import uuid
             from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
             from src.database.redis import redis_client

             short_id = str(uuid.uuid4())[:8]
             await redis_client.setex(f"link:{short_id}", 86400, url)
             # Msg ID for deletion
             await redis_client.setex(f"msg:{short_id}", 86400, message.message_id)

             kb = InlineKeyboardMarkup(inline_keyboard=[
                 [
                     InlineKeyboardButton(text="360p", callback_data=f"yt_q:360:{short_id}"),
                     InlineKeyboardButton(text="480p", callback_data=f"yt_q:480:{short_id}")
                 ],
                 [
                     InlineKeyboardButton(text="720p", callback_data=f"yt_q:720:{short_id}"),
                     InlineKeyboardButton(text="1080p", callback_data=f"yt_q:1080:{short_id}")
                 ],
                 [
                    InlineKeyboardButton(text="❌", callback_data=f"delete:{short_id}")
                 ]
             ])
             # Audio? Maybe later.
             
             await status_msg.edit_text(get_text("youtube_quality_prompt", lang), reply_markup=kb)
             return

        if time_range:
            status_msg = await status_msg.edit_text(f"Cutting video {time_range[0]}-{time_range[1]}s...")

        # For others -> Max quality
        result = await downloader.download_media(url, time_range=time_range, quality="max")
        
        if not result:
            await status_msg.edit_text(get_text("error_download", lang))
            return
            
        content_type = result.get('type', 'video')

        # Common Caption
        from aiogram.utils.text_decorations import html_decoration
        
        caption_template = get_text("download_caption", lang)
        raw_title = result.get('title', 'Media')
        # Escape title for HTML
        title = html_decoration.quote(raw_title)
        
        caption = caption_template.format(title=title)
        
        # Prepare Buttons (Common)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        import uuid
        from src.database.redis import redis_client
        
        short_id = str(uuid.uuid4())[:8]
        await redis_client.setex(f"link:{short_id}", 86400, url)
        # Store User Message ID too
        await redis_client.setex(f"msg:{short_id}", 86400, message.message_id)
        
        # Base Buttons
        buttons = []
        # Only add Audio/Cover buttons for Video? 
        # For images, "Convert to Audio" makes no sense. "Get Cover" effectively is the image itself.
        # So for Image/Album, maybe just Delete button?
        
        if content_type == 'video':
             buttons.append([InlineKeyboardButton(text=get_text("btn_convert_audio", lang), callback_data=f"convert_audio:{short_id}")])
             buttons.append([
                 InlineKeyboardButton(text="🖼 Cover", callback_data=f"get_cover:{short_id}"), 
                 InlineKeyboardButton(text="❌", callback_data=f"delete:{short_id}")
             ])
        else:
             # Photo/Album
             buttons.append([InlineKeyboardButton(text="❌", callback_data=f"delete:{short_id}")])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        result = await downloader.download_media(url, time_range, quality)
        
        if not result:
            await status_msg.edit_text(get_text("error_download", lang))
            return
            
        if content_type == 'video':
            file_path = result['path']
            if not os.path.exists(file_path):
                 await status_msg.edit_text(get_text("error_download", lang))
                 return
            
            # Check file size (Telegram limit: 50MB for Bots)
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 49.5: # Margin of safety
               await status_msg.edit_text(get_text("error_generic", lang).format(error=f"File too large ({file_size_mb:.1f}MB). Telegram limit is 50MB."))
               return

            # Use streaming for larger files to reduce memory usage
            if should_use_streaming(file_path, threshold_mb=10.0):
                # Stream file in chunks - memory efficient for large files
                async with aiofiles.open(file_path, 'rb') as f:
                    file_data = await f.read()
                video_file = BufferedInputFile(file_data, filename=os.path.basename(file_path))
                await message.answer_video(video_file, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                # Small files - use FSInputFile (simpler)
                video_file = FSInputFile(file_path)
                await message.answer_video(video_file, caption=caption, parse_mode="HTML", reply_markup=kb)

        elif content_type in ['image', 'album']:
            paths = result.get('paths', [])
            if not paths:
                 await status_msg.edit_text(get_text("error_download", lang))
                 return

            if len(paths) == 1:
                # Single Image
                photo_file = FSInputFile(paths[0])
                await message.answer_photo(photo_file, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                # Album
                from aiogram.types import InputMediaPhoto
                # Chunk into groups of 10
                chunk_size = 10
                for i in range(0, len(paths), chunk_size):
                    chunk = paths[i:i + chunk_size]
                    media_group = []
                    for idx, p in enumerate(chunk):
                        # Caption only on first item of first chunk?
                        cap = caption if i == 0 and idx == 0 else None
                        media_group.append(InputMediaPhoto(media=FSInputFile(p), caption=cap, parse_mode="HTML"))
                    
                    await message.answer_media_group(media_group)
                
                # Send buttons as separate message because MediaGroup can't have buttons
                await message.answer("Control:", reply_markup=kb)

        # await status_msg.delete()  # Disabled: keep messages
        
    except Exception as e:
        await status_msg.edit_text(get_text("error_generic", lang).format(error=str(e)))
    finally:
        # Cleanup files immediately after upload (critical for 2GB storage)
        if 'download_result' in dir() and download_result:
            if isinstance(download_result, dict):
                if download_result.get('path'):
                    downloader.delete_file(download_result['path'])
                if download_result.get('paths'):
                    for p in download_result['paths']:
                        downloader.delete_file(p)
        
        # Memory optimization: GC + temp cleanup
        from src.utils.memory import get_memory_optimizer
        await get_memory_optimizer().optimize_after_download()
        
        await state.clear()

@router.message(DownloadState.waiting_for_link)
async def handle_invalid_link(message: Message):
    user_id = message.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"
        
    await message.answer(get_text("err_not_link", lang))
