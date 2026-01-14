"""
Enhanced inline mode handler with thumbnail preview.
Allows downloading from any chat via @yourbot link
"""

import hashlib
import logging
import asyncio
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    InlineQuery, InlineQueryResultArticle, InlineQueryResultVideo,
    InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
)
import yt_dlp

from src.database.redis import redis_client
from src.utils.security import validate_url

logger = logging.getLogger(__name__)
router = Router()


async def get_video_preview(url: str) -> Optional[dict]:
    """
    Extract video thumbnail and info for preview.
    Uses yt-dlp to get metadata without downloading.
    """
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
        'skip_download': True,
    }
    
    loop = asyncio.get_event_loop()
    
    try:
        def extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        # Timeout to prevent blocking
        info = await asyncio.wait_for(
            loop.run_in_executor(None, extract),
            timeout=5.0
        )
        
        if not info:
            return None
        
        # Get best thumbnail
        thumbnails = info.get('thumbnails', [])
        thumbnail_url = None
        if thumbnails:
            # Prefer higher resolution
            for t in reversed(thumbnails):
                if t.get('url'):
                    thumbnail_url = t['url']
                    break
        
        # Fallback to thumbnail field
        if not thumbnail_url:
            thumbnail_url = info.get('thumbnail')
        
        return {
            'title': info.get('title', 'Video')[:100],
            'description': info.get('description', '')[:200] if info.get('description') else '',
            'duration': info.get('duration'),
            'thumbnail': thumbnail_url,
            'uploader': info.get('uploader', ''),
            'view_count': info.get('view_count'),
            'platform': info.get('extractor', 'Unknown'),
        }
        
    except asyncio.TimeoutError:
        logger.debug(f"Preview timeout for {url[:50]}")
        return None
    except Exception as e:
        logger.debug(f"Preview error: {e}")
        return None


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in human-readable format."""
    if not seconds:
        return ""
    
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_views(count: Optional[int]) -> str:
    """Format view count in human-readable format."""
    if not count:
        return ""
    
    if count >= 1_000_000:
        return f"{count/1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count/1_000:.1f}K"
    return str(count)


@router.inline_query()
async def inline_download_handler(query: InlineQuery):
    """
    Enhanced inline query handler.
    @yourbot https://youtube.com/watch?v=xxx
    
    Shows thumbnail preview and video info before sending.
    """
    text = query.query.strip()
    user_id = query.from_user.id
    
    # Empty query - show help
    if not text:
        return await query.answer(
            results=[],
            switch_pm_text="🎬 Вставьте ссылку на видео",
            switch_pm_parameter="start",
            cache_time=10
        )
    
    # Validate URL
    if not text.startswith("http"):
        return await query.answer(
            results=[],
            switch_pm_text="❌ Некорректная ссылка",
            switch_pm_parameter="start",
            cache_time=5
        )
    
    # Security validation
    validation = validate_url(text, strict_whitelist=True)
    if not validation.is_valid:
        item = InlineQueryResultArticle(
            id="invalid",
            title="❌ Платформа не поддерживается",
            description=validation.domain or "Неизвестный домен",
            input_message_content=InputTextMessageContent(
                message_text="❌ Эта платформа не поддерживается"
            )
        )
        return await query.answer(results=[item], cache_time=60)
    
    # Generate stable ID for caching
    result_id = hashlib.md5(text.encode()).hexdigest()[:16]
    
    # Store URL in Redis for callback handling
    short_id = result_id[:8]
    await redis_client.setex(f"inline:{short_id}", 3600, text)
    
    # Try to get video preview
    preview = await get_video_preview(text)
    
    results = []
    
    if preview:
        # Rich preview with thumbnail
        duration_str = format_duration(preview.get('duration'))
        views_str = format_views(preview.get('view_count'))
        
        # Build description
        desc_parts = []
        if preview.get('uploader'):
            desc_parts.append(f"👤 {preview['uploader']}")
        if duration_str:
            desc_parts.append(f"⏱ {duration_str}")
        if views_str:
            desc_parts.append(f"👁 {views_str}")
        
        description = " • ".join(desc_parts) if desc_parts else preview.get('platform', '')
        
        # Message that will be sent
        message_text = (
            f"🎬 **{preview['title']}**\n\n"
            f"🔗 {text}\n\n"
            f"_Отправлено через @{query.bot.username}_"
        )
        
        # Button to download in bot
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⬇️ Скачать",
                url=f"https://t.me/{query.bot.username}?start=dl_{short_id}"
            )]
        ])
        
        item = InlineQueryResultArticle(
            id=result_id,
            title=f"🎬 {preview['title']}",
            description=description,
            thumbnail_url=preview.get('thumbnail') or "https://cdn-icons-png.flaticon.com/512/4096/4096263.png",
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                parse_mode="Markdown"
            ),
            reply_markup=keyboard
        )
        results.append(item)
        
    else:
        # Fallback without preview
        message_text = f"🎬 Видео для скачивания:\n\n{text}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⬇️ Скачать в боте",
                url=f"https://t.me/{query.bot.username}?start=dl_{short_id}"
            )]
        ])
        
        item = InlineQueryResultArticle(
            id=result_id,
            title="🎬 Скачать видео",
            description=f"{validation.domain} • Нажмите для отправки",
            thumbnail_url="https://cdn-icons-png.flaticon.com/512/4096/4096263.png",
            input_message_content=InputTextMessageContent(
                message_text=message_text
            ),
            reply_markup=keyboard
        )
        results.append(item)
    
    # Add "Download now" option (sends link for bot to process)
    results.append(InlineQueryResultArticle(
        id=f"{result_id}_direct",
        title="📥 Отправить ссылку",
        description="Бот обработает её в личных сообщениях",
        thumbnail_url="https://cdn-icons-png.flaticon.com/512/724/724933.png",
        input_message_content=InputTextMessageContent(message_text=text)
    ))
    
    await query.answer(results=results, cache_time=300)
