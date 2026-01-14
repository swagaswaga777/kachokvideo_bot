"""
Reliability utilities: retry decorator, error handling, rate limiting helpers.
Provides robust error recovery and fallback mechanisms.
"""

import asyncio
import functools
import logging
from typing import Callable, TypeVar, Any, Optional, List, Type
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy(Enum):
    """Retry backoff strategies."""
    EXPONENTIAL = "exponential"  # 2^attempt seconds
    LINEAR = "linear"            # attempt * base seconds
    FIXED = "fixed"              # fixed delay


class DownloadError(Exception):
    """Base exception for download errors with user-friendly message."""
    
    def __init__(self, message: str, user_message: str = None, retryable: bool = True):
        self.message = message
        self.user_message = user_message or "Произошла ошибка при загрузке"
        self.retryable = retryable
        super().__init__(message)


class RateLimitError(DownloadError):
    """Rate limit exceeded error."""
    
    def __init__(self, platform: str, wait_seconds: int = 60):
        super().__init__(
            f"Rate limit exceeded for {platform}",
            f"⏳ Превышен лимит запросов к {platform}. Попробуйте через {wait_seconds} сек.",
            retryable=True
        )
        self.wait_seconds = wait_seconds


class PlatformUnavailableError(DownloadError):
    """Platform temporarily unavailable."""
    
    def __init__(self, platform: str):
        super().__init__(
            f"{platform} is temporarily unavailable",
            f"🔧 {platform} временно недоступен. Попробуйте позже.",
            retryable=True
        )


class ContentNotFoundError(DownloadError):
    """Content not found or deleted."""
    
    def __init__(self, url: str):
        super().__init__(
            f"Content not found: {url}",
            "❌ Контент не найден или был удалён.",
            retryable=False
        )


class GeoblockError(DownloadError):
    """Content is geo-blocked."""
    
    def __init__(self):
        super().__init__(
            "Content is geo-blocked",
            "🌍 Контент недоступен в вашем регионе.",
            retryable=False
        )


class TimeoutError(DownloadError):
    """Operation timed out."""
    
    def __init__(self, operation: str, timeout: int):
        super().__init__(
            f"{operation} timed out after {timeout}s",
            f"⏱ Превышено время ожидания ({timeout} сек). Попробуйте ещё раз.",
            retryable=True
        )


def retry(
    max_attempts: int = 3,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator for automatic retry with configurable backoff.
    
    Args:
        max_attempts: Maximum retry attempts (including first try)
        strategy: Backoff strategy (exponential, linear, fixed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback(attempt, exception, delay) called before retry
    
    Example:
        @retry(max_attempts=3, strategy=RetryStrategy.EXPONENTIAL)
        async def download_video(url):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    # Check if error is retryable
                    if isinstance(e, DownloadError) and not e.retryable:
                        raise
                    
                    # Last attempt - don't retry
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    # Calculate delay based on strategy
                    if strategy == RetryStrategy.EXPONENTIAL:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    elif strategy == RetryStrategy.LINEAR:
                        delay = min(base_delay * attempt, max_delay)
                    else:  # FIXED
                        delay = base_delay
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            if asyncio.iscoroutinefunction(on_retry):
                                await on_retry(attempt, e, delay)
                            else:
                                on_retry(attempt, e, delay)
                        except Exception as cb_error:
                            logger.error(f"Retry callback error: {cb_error}")
                    
                    await asyncio.sleep(delay)
            
            # Should not reach here, but safety fallback
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def with_timeout(timeout_seconds: float, operation_name: str = "Operation"):
    """
    Decorator to add timeout to async function.
    
    Args:
        timeout_seconds: Maximum execution time in seconds
        operation_name: Name for error message
    
    Example:
        @with_timeout(30, "Video download")
        async def download_video(url):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(operation_name, int(timeout_seconds))
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for failing fast on repeated errors.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failing fast, requests immediately fail
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "default"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        
        self._failures = 0
        self._last_failure_time: Optional[float] = None
        self._state = "CLOSED"
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            await self._check_state()
        
        if self._state == "OPEN":
            raise PlatformUnavailableError(self.name)
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
            
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _check_state(self):
        """Check and update circuit state."""
        if self._state == "OPEN" and self._last_failure_time:
            import time
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
                logger.info(f"Circuit {self.name} entering HALF_OPEN state")
    
    async def _on_success(self):
        """Reset on successful call."""
        async with self._lock:
            self._failures = 0
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                logger.info(f"Circuit {self.name} recovered, entering CLOSED state")
    
    async def _on_failure(self):
        """Track failure and potentially open circuit."""
        import time
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            
            if self._failures >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    f"Circuit {self.name} opened after {self._failures} failures. "
                    f"Will recover in {self.recovery_timeout}s"
                )


# User-friendly error messages by error type
ERROR_MESSAGES = {
    "rate_limit": "⏳ Слишком много запросов. Подождите немного.",
    "not_found": "❌ Видео не найдено или было удалено.",
    "private": "🔒 Это приватный контент.",
    "geo_blocked": "🌍 Контент недоступен в вашем регионе.",
    "age_restricted": "🔞 Контент с возрастным ограничением.",
    "timeout": "⏱ Превышено время ожидания. Попробуйте ещё раз.",
    "server_error": "🔧 Сервер временно недоступен. Попробуйте позже.",
    "unsupported": "❌ Эта ссылка не поддерживается.",
    "too_large": "📦 Файл слишком большой для Telegram (макс. 50 МБ).",
    "generic": "❌ Произошла ошибка. Попробуйте ещё раз.",
}


def get_user_error_message(error: Exception) -> str:
    """Get user-friendly error message from exception."""
    if isinstance(error, DownloadError):
        return error.user_message
    
    error_str = str(error).lower()
    
    # Pattern matching for common errors
    if "rate" in error_str or "429" in error_str:
        return ERROR_MESSAGES["rate_limit"]
    elif "not found" in error_str or "404" in error_str or "deleted" in error_str:
        return ERROR_MESSAGES["not_found"]
    elif "private" in error_str or "login" in error_str:
        return ERROR_MESSAGES["private"]
    elif "geo" in error_str or "country" in error_str or "region" in error_str:
        return ERROR_MESSAGES["geo_blocked"]
    elif "age" in error_str:
        return ERROR_MESSAGES["age_restricted"]
    elif "timeout" in error_str:
        return ERROR_MESSAGES["timeout"]
    elif "50" in error_str and ("mb" in error_str or "size" in error_str):
        return ERROR_MESSAGES["too_large"]
    elif "500" in error_str or "502" in error_str or "503" in error_str:
        return ERROR_MESSAGES["server_error"]
    elif "unsupported" in error_str or "not supported" in error_str:
        return ERROR_MESSAGES["unsupported"]
    
    return ERROR_MESSAGES["generic"]
