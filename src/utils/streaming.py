"""
Streaming utilities for efficient file upload to Telegram.
Implements chunked file reading without loading entire file into memory.
"""

import os
import asyncio
import logging
from typing import AsyncGenerator, Optional

import aiofiles

logger = logging.getLogger(__name__)

# Chunk size for streaming (64KB - optimal for most networks)
DEFAULT_CHUNK_SIZE = 64 * 1024


async def stream_file(file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> AsyncGenerator[bytes, None]:
    """
    Async generator that yields file contents in chunks.
    
    Args:
        file_path: Path to file to stream
        chunk_size: Size of each chunk in bytes
    
    Yields:
        bytes: File chunk
    """
    async with aiofiles.open(file_path, 'rb') as f:
        while True:
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            yield chunk


class StreamingInputFile:
    """
    Custom InputFile-like class for streaming large files to Telegram.
    
    Instead of loading entire file into memory, reads chunks on demand.
    Compatible with aiogram's file sending methods.
    """
    
    def __init__(self, file_path: str, filename: Optional[str] = None, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """
        Initialize streaming file.
        
        Args:
            file_path: Absolute path to file
            filename: Optional custom filename for Telegram
            chunk_size: Chunk size for reading
        """
        self.path = file_path
        self.filename = filename or os.path.basename(file_path)
        self.chunk_size = chunk_size
        self._size: Optional[int] = None
    
    @property
    def size(self) -> int:
        """Get file size lazily."""
        if self._size is None:
            self._size = os.path.getsize(self.path)
        return self._size
    
    async def read(self, bot) -> bytes:
        """
        Read entire file. Falls back for small files or when streaming isn't supported.
        
        Note: This loads entire file into memory. For large files,
        use the generator-based approach with custom upload logic.
        """
        async with aiofiles.open(self.path, 'rb') as f:
            return await f.read()
    
    def __aiter__(self):
        """Make this class an async iterator for chunked reading."""
        return self._chunk_iterator()
    
    async def _chunk_iterator(self) -> AsyncGenerator[bytes, None]:
        """Internal async iterator for chunks."""
        async with aiofiles.open(self.path, 'rb') as f:
            while True:
                chunk = await f.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk


async def get_file_info(file_path: str) -> dict:
    """
    Get file metadata without loading content.
    
    Returns:
        dict with 'size', 'exists', 'extension'
    """
    exists = os.path.exists(file_path)
    if not exists:
        return {'exists': False, 'size': 0, 'extension': ''}
    
    size = os.path.getsize(file_path)
    extension = os.path.splitext(file_path)[1].lstrip('.')
    
    return {
        'exists': True,
        'size': size,
        'size_mb': size / (1024 * 1024),
        'extension': extension
    }


def should_use_streaming(file_path: str, threshold_mb: float = 10.0) -> bool:
    """
    Determine if file should use streaming upload.
    
    Args:
        file_path: Path to file
        threshold_mb: Size threshold in MB (default 10MB)
    
    Returns:
        True if streaming should be used
    """
    try:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return size_mb > threshold_mb
    except OSError:
        return False
