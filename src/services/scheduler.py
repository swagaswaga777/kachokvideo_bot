"""
Scheduler service for delayed/scheduled downloads.
Supports scheduling downloads for a specific time with persistent storage.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

from src.database.redis import redis_client

logger = logging.getLogger(__name__)


class ScheduleStatus(Enum):
    """Status of scheduled task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """Represents a scheduled download task."""
    task_id: str
    user_id: int
    chat_id: int
    url: str
    scheduled_time: datetime
    quality: str = "max"
    status: ScheduleStatus = ScheduleStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for Redis storage."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "url": self.url,
            "scheduled_time": self.scheduled_time.isoformat(),
            "quality": self.quality,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "error_message": self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledTask':
        """Deserialize from dictionary."""
        return cls(
            task_id=data["task_id"],
            user_id=data["user_id"],
            chat_id=data["chat_id"],
            url=data["url"],
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            quality=data.get("quality", "max"),
            status=ScheduleStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]),
            error_message=data.get("error_message")
        )


class SchedulerService:
    """
    Service for managing scheduled downloads.
    
    Features:
    - Schedule downloads for specific time
    - Persistent storage in Redis
    - Background task executor
    - User notification on completion
    """
    
    _instance: Optional['SchedulerService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._redis = redis_client
        self._running = False
        self._check_interval = 30  # Check every 30 seconds
        self._task: Optional[asyncio.Task] = None
        self._download_callback: Optional[Callable] = None
        self._notify_callback: Optional[Callable] = None
    
    def set_callbacks(
        self,
        download_callback: Callable,
        notify_callback: Callable
    ):
        """
        Set callbacks for download execution and user notification.
        
        Args:
            download_callback: async func(task: ScheduledTask) -> result
            notify_callback: async func(user_id, chat_id, message, result)
        """
        self._download_callback = download_callback
        self._notify_callback = notify_callback
    
    async def start(self):
        """Start the scheduler background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler service started")
    
    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler service stopped")
    
    async def schedule_download(
        self,
        task_id: str,
        user_id: int,
        chat_id: int,
        url: str,
        scheduled_time: datetime,
        quality: str = "max"
    ) -> ScheduledTask:
        """
        Schedule a download for a specific time.
        
        Args:
            task_id: Unique task identifier
            user_id: Telegram user ID
            chat_id: Chat ID for sending result
            url: Media URL to download
            scheduled_time: When to execute download
            quality: Download quality
        
        Returns:
            ScheduledTask object
        """
        task = ScheduledTask(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            url=url,
            scheduled_time=scheduled_time,
            quality=quality
        )
        
        # Store in Redis with TTL (24 hours after scheduled time)
        key = f"scheduled:{task_id}"
        ttl = int((scheduled_time - datetime.now()).total_seconds()) + 86400
        await self._redis.setex(key, max(ttl, 3600), json.dumps(task.to_dict()))
        
        # Add to user's scheduled tasks set
        user_key = f"user_scheduled:{user_id}"
        await self._redis.sadd(user_key, task_id)
        
        logger.info(f"Scheduled download {task_id} for user {user_id} at {scheduled_time}")
        return task
    
    async def cancel_scheduled(self, task_id: str, user_id: int) -> bool:
        """Cancel a scheduled download."""
        key = f"scheduled:{task_id}"
        data = await self._redis.get(key)
        
        if not data:
            return False
        
        task = ScheduledTask.from_dict(json.loads(data))
        
        # Verify ownership
        if task.user_id != user_id:
            return False
        
        # Update status
        task.status = ScheduleStatus.CANCELLED
        await self._redis.setex(key, 3600, json.dumps(task.to_dict()))
        
        # Remove from user's set
        user_key = f"user_scheduled:{user_id}"
        await self._redis.srem(user_key, task_id)
        
        logger.info(f"Cancelled scheduled download {task_id}")
        return True
    
    async def get_user_scheduled(self, user_id: int) -> list[ScheduledTask]:
        """Get all scheduled tasks for user."""
        user_key = f"user_scheduled:{user_id}"
        task_ids = await self._redis.smembers(user_key)
        
        tasks = []
        for tid in task_ids:
            tid_str = tid.decode() if isinstance(tid, bytes) else tid
            key = f"scheduled:{tid_str}"
            data = await self._redis.get(key)
            if data:
                task = ScheduledTask.from_dict(json.loads(data))
                if task.status == ScheduleStatus.PENDING:
                    tasks.append(task)
        
        # Sort by scheduled time
        tasks.sort(key=lambda t: t.scheduled_time)
        return tasks
    
    async def _scheduler_loop(self):
        """Background loop that checks and executes scheduled tasks."""
        while self._running:
            try:
                await self._check_and_execute()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    async def _check_and_execute(self):
        """Check for due tasks and execute them."""
        # Scan for all scheduled tasks
        cursor = 0
        now = datetime.now()
        
        while True:
            cursor, keys = await self._redis.scan(cursor, match="scheduled:*", count=100)
            
            for key in keys:
                try:
                    data = await self._redis.get(key)
                    if not data:
                        continue
                    
                    task = ScheduledTask.from_dict(json.loads(data))
                    
                    # Skip if not pending
                    if task.status != ScheduleStatus.PENDING:
                        continue
                    
                    # Check if due
                    if task.scheduled_time <= now:
                        await self._execute_task(task)
                        
                except Exception as e:
                    logger.error(f"Error processing scheduled task {key}: {e}")
            
            if cursor == 0:
                break
    
    async def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled download task."""
        logger.info(f"Executing scheduled task {task.task_id}")
        
        # Update status to running
        task.status = ScheduleStatus.RUNNING
        key = f"scheduled:{task.task_id}"
        await self._redis.setex(key, 3600, json.dumps(task.to_dict()))
        
        result = None
        try:
            if self._download_callback:
                result = await self._download_callback(task)
                task.status = ScheduleStatus.COMPLETED
            else:
                task.status = ScheduleStatus.FAILED
                task.error_message = "No download callback configured"
                
        except Exception as e:
            logger.error(f"Scheduled download failed: {e}")
            task.status = ScheduleStatus.FAILED
            task.error_message = str(e)
        
        # Update status
        await self._redis.setex(key, 3600, json.dumps(task.to_dict()))
        
        # Remove from user's pending set
        user_key = f"user_scheduled:{task.user_id}"
        await self._redis.srem(user_key, task.task_id)
        
        # Notify user
        if self._notify_callback:
            if task.status == ScheduleStatus.COMPLETED:
                message = "✅ Отложенная загрузка завершена!"
            else:
                message = f"❌ Ошибка отложенной загрузки: {task.error_message}"
            
            try:
                await self._notify_callback(task.user_id, task.chat_id, message, result)
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")


# Time presets for quick scheduling
SCHEDULE_PRESETS = {
    "5min": timedelta(minutes=5),
    "15min": timedelta(minutes=15),
    "30min": timedelta(minutes=30),
    "1hour": timedelta(hours=1),
    "2hours": timedelta(hours=2),
    "tonight": None,  # Special: 23:00 today or tomorrow
    "morning": None,  # Special: 08:00 tomorrow
}


def get_preset_time(preset: str) -> datetime:
    """Get datetime for a schedule preset."""
    now = datetime.now()
    
    if preset in SCHEDULE_PRESETS and SCHEDULE_PRESETS[preset]:
        return now + SCHEDULE_PRESETS[preset]
    
    if preset == "tonight":
        tonight = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if tonight <= now:
            tonight += timedelta(days=1)
        return tonight
    
    if preset == "morning":
        morning = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if morning <= now:
            morning += timedelta(days=1)
        return morning
    
    # Default: 5 minutes from now
    return now + timedelta(minutes=5)


def format_scheduled_time(dt: datetime) -> str:
    """Format datetime for display to user."""
    now = datetime.now()
    
    if dt.date() == now.date():
        return f"сегодня в {dt.strftime('%H:%M')}"
    elif dt.date() == (now + timedelta(days=1)).date():
        return f"завтра в {dt.strftime('%H:%M')}"
    else:
        return dt.strftime("%d.%m в %H:%M")


# Global singleton getter
def get_scheduler() -> SchedulerService:
    """Get scheduler service singleton."""
    return SchedulerService()
