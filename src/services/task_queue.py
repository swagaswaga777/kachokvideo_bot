"""
Task Queue for parallel request processing.
Implements worker pool pattern with priority queue and per-user limits.
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from enum import IntEnum
import time

from src.config import config

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Task priority levels."""
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(order=True)
class Task:
    """Download task with priority ordering."""
    priority: int
    created_at: float = field(compare=True)
    task_id: str = field(compare=False)
    user_id: int = field(compare=False)
    coroutine: Callable = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    callback: Optional[Callable] = field(compare=False, default=None)


class TaskQueue:
    """
    Parallel task processing with worker pool.
    
    Features:
    - Configurable worker count
    - Priority queue (HIGH > NORMAL > LOW)
    - Per-user concurrency limits
    - Progress tracking with callbacks
    - Graceful shutdown
    """
    
    _instance: Optional['TaskQueue'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._num_workers = getattr(config, 'DOWNLOAD_WORKERS', 10)
        self._max_per_user = 3  # Max concurrent tasks per user
        
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list = []
        self._running = False
        self._user_tasks: Dict[int, int] = {}  # user_id -> active task count
        self._user_locks: Dict[int, asyncio.Lock] = {}
        self._task_results: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
    
    async def start(self):
        """Start worker pool."""
        if self._running:
            return
        
        self._running = True
        self._queue = asyncio.PriorityQueue()
        
        for i in range(self._num_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        
        logger.info(f"Task queue started with {self._num_workers} workers")
    
    async def stop(self):
        """Stop worker pool gracefully."""
        self._running = False
        
        # Send poison pills to all workers
        for _ in self._workers:
            await self._queue.put((0, 0, None))  # Lowest priority sentinel
        
        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
        
        logger.info("Task queue stopped")
    
    async def _worker(self, worker_id: int):
        """Worker coroutine that processes tasks from queue."""
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get task from queue
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                # Check for poison pill
                if item[2] is None:
                    break
                
                task: Task = item[2]
                
                # Check per-user limit
                async with self._lock:
                    if task.user_id not in self._user_locks:
                        self._user_locks[task.user_id] = asyncio.Lock()
                
                async with self._user_locks[task.user_id]:
                    current_count = self._user_tasks.get(task.user_id, 0)
                    
                    if current_count >= self._max_per_user:
                        # Re-queue with delay
                        await asyncio.sleep(0.5)
                        await self._queue.put((task.priority, task.created_at, task))
                        continue
                    
                    self._user_tasks[task.user_id] = current_count + 1
                
                try:
                    # Execute task
                    logger.debug(f"Worker {worker_id} processing task {task.task_id}")
                    result = await task.coroutine(*task.args, **task.kwargs)
                    self._task_results[task.task_id] = result
                    
                    # Call callback if provided
                    if task.callback:
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                await task.callback(task.task_id, result)
                            else:
                                task.callback(task.task_id, result)
                        except Exception as e:
                            logger.error(f"Callback error for task {task.task_id}: {e}")
                            
                except Exception as e:
                    logger.error(f"Task {task.task_id} failed: {e}")
                    self._task_results[task.task_id] = None
                
                finally:
                    # Decrement user task count
                    async with self._lock:
                        self._user_tasks[task.user_id] = max(0, self._user_tasks.get(task.user_id, 1) - 1)
                    
                    self._queue.task_done()
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def submit(
        self,
        task_id: str,
        user_id: int,
        coroutine: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: Priority = Priority.NORMAL,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Submit task to queue.
        
        Args:
            task_id: Unique task identifier
            user_id: Telegram user ID (for per-user limits)
            coroutine: Async function to execute
            args: Positional arguments for coroutine
            kwargs: Keyword arguments for coroutine
            priority: Task priority level
            callback: Optional callback(task_id, result) on completion
        
        Returns:
            task_id for tracking
        """
        if kwargs is None:
            kwargs = {}
        
        task = Task(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            user_id=user_id,
            coroutine=coroutine,
            args=args,
            kwargs=kwargs,
            callback=callback
        )
        
        await self._queue.put((task.priority, task.created_at, task))
        logger.debug(f"Task {task_id} submitted by user {user_id} with priority {priority.name}")
        
        return task_id
    
    def get_result(self, task_id: str) -> Optional[Any]:
        """Get result of completed task."""
        return self._task_results.get(task_id)
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    def get_user_task_count(self, user_id: int) -> int:
        """Get active task count for user."""
        return self._user_tasks.get(user_id, 0)


# Global instance getter
def get_task_queue() -> TaskQueue:
    """Get the singleton task queue instance."""
    return TaskQueue()
