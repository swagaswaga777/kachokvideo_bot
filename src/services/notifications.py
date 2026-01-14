"""
Notification service for download completion alerts.
Sends notifications when large file downloads are ready.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.database.redis import redis_client

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications."""
    DOWNLOAD_COMPLETE = "download_complete"
    DOWNLOAD_FAILED = "download_failed"
    SCHEDULED_READY = "scheduled_ready"
    SCHEDULED_FAILED = "scheduled_failed"


@dataclass
class Notification:
    """Notification data structure."""
    user_id: int
    chat_id: int
    type: NotificationType
    message: str
    data: Optional[Dict[str, Any]] = None


class NotificationService:
    """
    Service for sending notifications to users.
    
    Features:
    - Download completion notifications
    - Scheduled download ready alerts
    - Retry failed notifications
    - Queue for async delivery
    """
    
    _instance: Optional['NotificationService'] = None
    _bot: Optional[Bot] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def set_bot(self, bot: Bot):
        """Set the bot instance for sending messages."""
        self._bot = bot
    
    async def start(self):
        """Start notification delivery worker."""
        if self._running:
            return
        
        self._running = True
        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._delivery_worker())
        logger.info("Notification service started")
    
    async def stop(self):
        """Stop notification service."""
        self._running = False
        
        # Process remaining notifications
        while not self._queue.empty():
            try:
                notification = self._queue.get_nowait()
                await self._send_notification(notification)
            except asyncio.QueueEmpty:
                break
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Notification service stopped")
    
    async def notify_download_complete(
        self,
        user_id: int,
        chat_id: int,
        title: str,
        file_path: Optional[str] = None,
        download_link: Optional[str] = None
    ):
        """
        Notify user that download is complete.
        
        Args:
            user_id: Telegram user ID
            chat_id: Chat to send notification
            title: Media title
            file_path: Path to downloaded file
            download_link: Original download URL
        """
        notification = Notification(
            user_id=user_id,
            chat_id=chat_id,
            type=NotificationType.DOWNLOAD_COMPLETE,
            message=f"✅ Загрузка завершена!\n\n📹 {title}",
            data={
                "title": title,
                "file_path": file_path,
                "download_link": download_link
            }
        )
        
        await self._queue.put(notification)
    
    async def notify_download_failed(
        self,
        user_id: int,
        chat_id: int,
        error: str,
        url: Optional[str] = None
    ):
        """Notify user that download failed."""
        notification = Notification(
            user_id=user_id,
            chat_id=chat_id,
            type=NotificationType.DOWNLOAD_FAILED,
            message=f"❌ Ошибка загрузки\n\n{error}",
            data={"url": url, "error": error}
        )
        
        await self._queue.put(notification)
    
    async def notify_scheduled_ready(
        self,
        user_id: int,
        chat_id: int,
        message: str,
        result: Optional[Dict[str, Any]] = None
    ):
        """
        Notify user that scheduled download is ready.
        Called by scheduler service.
        """
        notification = Notification(
            user_id=user_id,
            chat_id=chat_id,
            type=NotificationType.SCHEDULED_READY,
            message=message,
            data=result
        )
        
        await self._queue.put(notification)
    
    async def _delivery_worker(self):
        """Background worker that delivers notifications."""
        while self._running:
            try:
                notification = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                await self._send_notification(notification)
                self._queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Notification delivery error: {e}")
    
    async def _send_notification(self, notification: Notification):
        """Send a single notification."""
        if not self._bot:
            logger.error("Bot not set for notification service")
            return
        
        try:
            # Build keyboard based on notification type
            keyboard = None
            
            if notification.type == NotificationType.DOWNLOAD_COMPLETE:
                if notification.data and notification.data.get("download_link"):
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="🔗 Открыть источник",
                            url=notification.data["download_link"]
                        )]
                    ])
            
            await self._bot.send_message(
                chat_id=notification.chat_id,
                text=notification.message,
                reply_markup=keyboard,
                disable_notification=False
            )
            
            logger.info(f"Sent {notification.type.value} notification to {notification.user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send notification to {notification.user_id}: {e}")
            
            # Store failed notification for retry
            await self._store_failed(notification)
    
    async def _store_failed(self, notification: Notification):
        """Store failed notification for later retry."""
        key = f"failed_notify:{notification.user_id}:{datetime.now().timestamp()}"
        try:
            import json
            data = {
                "user_id": notification.user_id,
                "chat_id": notification.chat_id,
                "type": notification.type.value,
                "message": notification.message,
            }
            await redis_client.setex(key, 3600, json.dumps(data))  # 1 hour TTL
        except Exception as e:
            logger.error(f"Failed to store notification: {e}")


# Global singleton getter
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
