from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile, BufferedInputFile
from src.services.downloader import DownloaderService
import os
import aiofiles
from src.database.main import get_session, User
from sqlalchemy import select
from src.utils.i18n import get_text
from src.utils.streaming import should_use_streaming

router = Router()
downloader = DownloaderService()

from src.database.redis import redis_client

@router.callback_query(F.data.startswith("convert_audio:"))
async def convert_audio_callback(callback: CallbackQuery):
    short_id = callback.data.split(":", 1)[1]
    
    # Retrieve URL from Redis
    url_bytes = await redis_client.get(f"link:{short_id}")
    if not url_bytes:
        await callback.answer("Link expired or invalid", show_alert=True)
        return
        
    url = url_bytes.decode('utf-8')
    
    user_id = callback.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"

    await callback.answer(get_text("convert_audio_answer", lang))
    # Send temporary status
    status_msg = await callback.message.reply(get_text("convert_audio_status", lang))

    result = await downloader.download_audio(url)
    
    if result and os.path.exists(result['path']):
        audio_file = FSInputFile(result['path'])
        
        from aiogram.utils.text_decorations import html_decoration
        raw_title = result.get('title')
        title = html_decoration.quote(raw_title) if raw_title else "Audio"
        
        caption = get_text("convert_audio_caption", lang).format(title=title)
        await callback.message.reply_audio(audio_file, caption=caption, parse_mode="HTML")
        # await status_msg.delete()  # Disabled: keep messages
        downloader.delete_file(result['path'])
    else:
        await status_msg.edit_text(get_text("error_convert_audio", lang))

@router.callback_query(F.data.startswith("yt_q:"))
async def youtube_quality_callback(callback: CallbackQuery):
    # yt_q:360:short_id
    parts = callback.data.split(":")
    quality = parts[1]
    short_id = parts[2]
    
    # Retrieve URL
    url_bytes = await redis_client.get(f"link:{short_id}")
    if not url_bytes:
        await callback.answer("Link expired", show_alert=True)
        return
    url = url_bytes.decode('utf-8')
    
    user_id = callback.from_user.id
    lang = "ru"
    async for session in get_session():
        result = await session.execute(select(User.language).where(User.user_id == user_id))
        lang = result.scalar() or "ru"
    
    await callback.answer(f"Downloading {quality}p...")
    # Delete prompt message logic if desired, or edit it
    status_msg = await callback.message.edit_text(get_text("processing_link", lang))
    
    # Trigger download
    # Since we are in callback, we call downloader directly
    
    try:
        # Pass time_range? We didn't store it in Redis. 
        # But user objective "YouTube quality prompting" usually implies full video.
        # If user sent timecodes, we likely would have skipped prompt or need to store metadata.
        # Regex extraction happened in media.py handler.
        # For now, simplistic approach: Link in Redis is just the URL.
        # If user added timecodes, they are part of message used in Regex, but we only saved URL group(1).
        # We can accept that timecodes + quality selection might not be supported together yet, 
        # OR we assume YouTube prompt is for standard downloads.
        # Let's proceed with URL only.
        
        result = await downloader.download_media(url, quality=quality)
        
        if result and result.get('path'):
           # Check file size (Telegram limit: 50MB for Bots)
           file_size_mb = os.path.getsize(result['path']) / (1024 * 1024)
           if file_size_mb > 49.5: # Margin of safety
               await status_msg.edit_text(get_text("error_generic", lang).format(error=f"File too large ({file_size_mb:.1f}MB). Telegram limit is 50MB. Try lower quality."))
               downloader.delete_file(result['path'])
               return

           # Send video with streaming for large files
           if should_use_streaming(result['path'], threshold_mb=10.0):
               async with aiofiles.open(result['path'], 'rb') as f:
                   file_data = await f.read()
               video_file = BufferedInputFile(file_data, filename=os.path.basename(result['path']))
           else:
               video_file = FSInputFile(result['path'])
           
           # HTML Escape
           from aiogram.utils.text_decorations import html_decoration
           raw_title = result.get('title', 'Video')
           title = html_decoration.quote(raw_title)
           caption = get_text("download_caption", lang).format(title=title)
           
           # Reuse similar buttons
           from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
           kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_text("btn_convert_audio", lang), callback_data=f"convert_audio:{short_id}")],
                [InlineKeyboardButton(text="🖼 Cover", callback_data=f"get_cover:{short_id}"), 
                 InlineKeyboardButton(text="❌", callback_data=f"delete:{short_id}")]
           ])
           
           await callback.message.answer_video(video_file, caption=caption, parse_mode="HTML", reply_markup=kb)
           # await status_msg.delete()  # Disabled: keep messages
           downloader.delete_file(result['path'])
        else:
           await status_msg.edit_text(get_text("error_download", lang))
           
    except Exception as e:
         await status_msg.edit_text(get_text("error_generic", lang).format(error=str(e)))


@router.callback_query(F.data.startswith("get_cover:"))
async def get_cover_callback(callback: CallbackQuery):
    short_id = callback.data.split(":", 1)[1]
    
    # Retrieve URL from Redis
    url_bytes = await redis_client.get(f"link:{short_id}")
    if not url_bytes:
        await callback.answer("Link expired or invalid", show_alert=True)
        return
        
    url = url_bytes.decode('utf-8')
    await callback.answer("Getting cover...")
    
    thumb_url = await downloader.get_thumbnail_url(url)
    if thumb_url:
        # Send as photo
        await callback.message.reply_photo(thumb_url, caption="🖼 Cover")
    else:
        await callback.message.reply("Could not get cover.")

@router.callback_query(F.data.startswith("delete:"))
async def delete_callback(callback: CallbackQuery):
    # Delete only the bot's video message (not user's message)
    try:
        await callback.message.delete()
        await callback.answer("Удалено")
    except:
        await callback.answer("Не удалось удалить", show_alert=False)
