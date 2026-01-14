"""
Progress bar utility for download status updates.
Creates visual progress indicators for Telegram messages.
"""

import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)


# Progress bar characters
PROGRESS_FILLED = "▓"
PROGRESS_EMPTY = "░"
PROGRESS_WIDTH = 10


@dataclass
class ProgressState:
    """Tracks progress state."""
    message: Message
    total: int
    current: int = 0
    last_update: float = 0
    status_text: str = "Загрузка..."
    

class ProgressBar:
    """
    Creates and updates progress bar in Telegram message.
    
    Example:
        ▓▓▓▓▓░░░░░ 50% • 2.5 MB/s
    """
    
    def __init__(
        self,
        message: Message,
        total: int = 100,
        update_interval: float = 2.0  # Min seconds between updates
    ):
        self.message = message
        self.total = total
        self.current = 0
        self.update_interval = update_interval
        self.last_update = 0
        self.start_time = datetime.now()
        self._cancelled = False
    
    def cancel(self):
        """Cancel progress updates."""
        self._cancelled = True
    
    @property
    def percentage(self) -> int:
        """Get current percentage."""
        if self.total <= 0:
            return 0
        return min(100, int(self.current / self.total * 100))
    
    def render(self, status: str = "") -> str:
        """Render progress bar string."""
        pct = self.percentage
        filled = int(pct / 100 * PROGRESS_WIDTH)
        empty = PROGRESS_WIDTH - filled
        
        bar = PROGRESS_FILLED * filled + PROGRESS_EMPTY * empty
        
        # Calculate speed
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 0 and self.current > 0:
            speed = self.current / elapsed
            if speed >= 1024 * 1024:
                speed_str = f"{speed / (1024*1024):.1f} MB/s"
            elif speed >= 1024:
                speed_str = f"{speed / 1024:.1f} KB/s"
            else:
                speed_str = f"{speed:.0f} B/s"
        else:
            speed_str = ""
        
        # Build progress line
        parts = [f"{bar} {pct}%"]
        if speed_str:
            parts.append(speed_str)
        
        progress_line = " • ".join(parts)
        
        if status:
            return f"{status}\n\n{progress_line}"
        return progress_line
    
    async def update(self, current: int, status: str = "⏳ Загрузка..."):
        """
        Update progress bar in message.
        Throttled to avoid rate limits.
        """
        if self._cancelled:
            return
        
        self.current = current
        now = datetime.now().timestamp()
        
        # Throttle updates
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        
        try:
            text = self.render(status)
            await self.message.edit_text(text)
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")
    
    async def finish(self, final_text: str):
        """Complete progress with final message."""
        self._cancelled = True
        try:
            await self.message.edit_text(final_text)
        except Exception as e:
            logger.debug(f"Progress finish failed: {e}")


class DownloadProgress:
    """
    yt-dlp progress hook compatible class.
    Wraps ProgressBar for use with yt-dlp.
    """
    
    def __init__(self, progress_bar: ProgressBar):
        self.progress_bar = progress_bar
        self._last_status = ""
    
    def __call__(self, d: dict):
        """yt-dlp progress hook callback."""
        status = d.get('status', '')
        
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            
            if total > 0:
                self.progress_bar.total = total
                self.progress_bar.current = downloaded
                
                # Schedule async update (we're in sync context)
                # This is a workaround since yt-dlp hooks are sync
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            self.progress_bar.update(downloaded, "⏳ Загрузка...")
                        )
                except Exception:
                    pass
                    
        elif status == 'finished':
            self._last_status = 'finished'
        
        elif status == 'error':
            self._last_status = 'error'


def create_progress_text(stage: str, detail: str = "") -> str:
    """
    Create simple stage-based progress text.
    
    Stages: probing, downloading, processing, uploading
    """
    stages = {
        "probing": ("🔍", "Анализ ссылки..."),
        "downloading": ("⬇️", "Загрузка..."),
        "processing": ("⚙️", "Обработка..."),
        "uploading": ("⬆️", "Отправка..."),
        "done": ("✅", "Готово!"),
        "error": ("❌", "Ошибка"),
    }
    
    emoji, text = stages.get(stage, ("⏳", "Обработка..."))
    
    if detail:
        return f"{emoji} {text}\n{detail}"
    return f"{emoji} {text}"


async def update_progress_message(
    message: Message,
    stage: str,
    detail: str = "",
    progress_pct: Optional[int] = None
):
    """
    Update message with progress stage.
    Includes optional percentage bar.
    """
    text = create_progress_text(stage, detail)
    
    if progress_pct is not None:
        filled = int(progress_pct / 100 * PROGRESS_WIDTH)
        empty = PROGRESS_WIDTH - filled
        bar = PROGRESS_FILLED * filled + PROGRESS_EMPTY * empty
        text += f"\n\n{bar} {progress_pct}%"
    
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.debug(f"Progress message update failed: {e}")
