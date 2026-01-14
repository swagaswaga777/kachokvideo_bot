"""
Async HTTP Client with connection pooling, proxy rotation, and retry logic.
Implements performance optimizations for non-blocking network operations.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector

from src.config import config

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Manages proxy rotation for requests."""
    
    def __init__(self, proxies: List[str]):
        self._proxies = proxies
        self._index = 0
        self._lock = asyncio.Lock()
        self._failed_proxies: set = set()
    
    async def get_next(self) -> Optional[str]:
        """Get next available proxy using round-robin."""
        if not self._proxies:
            return None
        
        async with self._lock:
            available = [p for p in self._proxies if p not in self._failed_proxies]
            if not available:
                # Reset failed proxies if all failed
                self._failed_proxies.clear()
                available = self._proxies
            
            proxy = available[self._index % len(available)]
            self._index += 1
            return proxy
    
    async def mark_failed(self, proxy: str):
        """Mark proxy as temporarily failed."""
        async with self._lock:
            self._failed_proxies.add(proxy)
            logger.warning(f"Proxy marked as failed: {proxy}")
    
    async def reset(self):
        """Reset all failed proxies."""
        async with self._lock:
            self._failed_proxies.clear()


class HTTPClient:
    """
    Singleton async HTTP client with:
    - Connection pooling (TCPConnector)
    - Configurable timeouts
    - Retry logic with exponential backoff
    - Proxy rotation support
    """
    
    _instance: Optional['HTTPClient'] = None
    _session: Optional[ClientSession] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Parse proxy list from config
        proxy_list = []
        if hasattr(config, 'PROXY_LIST') and config.PROXY_LIST:
            proxy_list = [p.strip() for p in config.PROXY_LIST.split(',') if p.strip()]
        
        self._proxy_rotator = ProxyRotator(proxy_list)
        self._timeout = getattr(config, 'HTTP_TIMEOUT', 30)
        self._max_retries = 3
    
    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            connector = TCPConnector(
                limit=100,  # Max connections
                limit_per_host=10,  # Max per host
                ttl_dns_cache=300,  # DNS cache TTL
                enable_cleanup_closed=True,
            )
            timeout = ClientTimeout(total=self._timeout)
            self._session = ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0)'}
            )
        return self._session
    
    async def close(self):
        """Close the HTTP session gracefully."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("HTTP client session closed")
    
    async def get(
        self,
        url: str,
        use_proxy: bool = False,
        retries: int = 3,
        **kwargs
    ) -> Optional[aiohttp.ClientResponse]:
        """
        Perform GET request with retry logic and optional proxy.
        
        Args:
            url: Target URL
            use_proxy: Whether to use proxy rotation
            retries: Number of retry attempts
            **kwargs: Additional aiohttp request arguments
        
        Returns:
            ClientResponse or None on failure
        """
        session = await self._get_session()
        
        for attempt in range(retries):
            proxy = None
            if use_proxy:
                proxy = await self._proxy_rotator.get_next()
            
            try:
                async with session.get(url, proxy=proxy, **kwargs) as response:
                    if response.status == 200:
                        return response
                    elif response.status >= 500:
                        # Server error, retry
                        logger.warning(f"Server error {response.status} for {url}, attempt {attempt + 1}")
                    else:
                        # Client error, don't retry
                        logger.error(f"Client error {response.status} for {url}")
                        return None
                        
            except aiohttp.ClientError as e:
                logger.warning(f"Request failed: {e}, attempt {attempt + 1}/{retries}")
                if proxy:
                    await self._proxy_rotator.mark_failed(proxy)
            
            # Exponential backoff
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def download_chunked(
        self,
        url: str,
        chunk_size: int = 64 * 1024,
        use_proxy: bool = False
    ):
        """
        Download file in chunks (generator).
        
        Yields:
            bytes: File chunks
        """
        session = await self._get_session()
        proxy = await self._proxy_rotator.get_next() if use_proxy else None
        
        try:
            async with session.get(url, proxy=proxy) as response:
                if response.status != 200:
                    logger.error(f"Download failed with status {response.status}")
                    return
                
                async for chunk in response.content.iter_chunked(chunk_size):
                    yield chunk
                    
        except aiohttp.ClientError as e:
            logger.error(f"Chunked download error: {e}")
            if proxy:
                await self._proxy_rotator.mark_failed(proxy)
    
    async def head(self, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get headers for URL (for content-length, type detection)."""
        session = await self._get_session()
        
        try:
            async with session.head(url, **kwargs) as response:
                return {
                    'status': response.status,
                    'content_length': response.headers.get('Content-Length'),
                    'content_type': response.headers.get('Content-Type'),
                }
        except aiohttp.ClientError as e:
            logger.error(f"HEAD request failed: {e}")
            return None


# Global instance getter
def get_http_client() -> HTTPClient:
    """Get the singleton HTTP client instance."""
    return HTTPClient()


@asynccontextmanager
async def http_client_context():
    """Context manager for HTTP client lifecycle."""
    client = get_http_client()
    try:
        yield client
    finally:
        await client.close()
