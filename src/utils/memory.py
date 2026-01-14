"""
Memory optimizer utilities for low-end hardware.
Optimized for: 512MB RAM / 2GB Storage

Features:
- Automatic temp file cleanup
- Garbage collection after downloads
- Memory usage monitoring
- Streaming file operations
"""

import os
import gc
import glob
import shutil
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from src.config import config

logger = logging.getLogger(__name__)


class MemoryOptimizer:
    """
    Memory management for low-end hardware.
    
    Key optimizations:
    - Force garbage collection after large operations
    - Clean up temp files automatically
    - Monitor and log memory usage
    """
    
    def __init__(self):
        self.temp_dir = config.TEMP_DIR
        self.auto_cleanup = config.AUTO_CLEANUP
        self._last_cleanup = datetime.now()
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def cleanup_file(self, file_path: str) -> bool:
        """
        Immediately delete a file after use.
        Critical for low storage (2GB).
        """
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up: {file_path}")
                return True
        except Exception as e:
            logger.warning(f"Cleanup failed for {file_path}: {e}")
        return False
    
    def cleanup_temp_dir(self, max_age_minutes: int = 30) -> int:
        """
        Remove all files older than max_age_minutes.
        Run periodically to prevent storage overflow.
        """
        cleaned = 0
        cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
        
        try:
            for file_path in glob.glob(f"{self.temp_dir}/*"):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < cutoff:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                        else:
                            shutil.rmtree(file_path, ignore_errors=True)
                        cleaned += 1
                except Exception as e:
                    logger.debug(f"Could not clean {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Temp cleanup error: {e}")
        
        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} old temp files")
        
        return cleaned
    
    def force_gc(self):
        """
        Force garbage collection.
        Call after large downloads to free memory.
        """
        collected = gc.collect()
        logger.debug(f"GC collected {collected} objects")
        return collected
    
    def get_temp_dir_size_mb(self) -> float:
        """Get current temp directory size in MB."""
        total = 0
        try:
            for file_path in glob.glob(f"{self.temp_dir}/*"):
                if os.path.isfile(file_path):
                    total += os.path.getsize(file_path)
        except Exception:
            pass
        return total / (1024 * 1024)
    
    def is_storage_critical(self, threshold_mb: float = 500) -> bool:
        """Check if temp storage is critically low."""
        try:
            stat = shutil.disk_usage(self.temp_dir)
            free_mb = stat.free / (1024 * 1024)
            return free_mb < threshold_mb
        except Exception:
            return False
    
    async def optimize_after_download(self, file_path: Optional[str] = None):
        """
        Run all optimizations after a download.
        - Delete the file if auto_cleanup is enabled
        - Force garbage collection
        - Clean old temp files periodically
        """
        # Delete specific file
        if file_path and self.auto_cleanup:
            self.cleanup_file(file_path)
        
        # Force GC
        self.force_gc()
        
        # Periodic temp cleanup (every 10 minutes)
        if (datetime.now() - self._last_cleanup).total_seconds() > 600:
            self.cleanup_temp_dir(max_age_minutes=30)
            self._last_cleanup = datetime.now()
        
        # Emergency cleanup if storage is critical
        if self.is_storage_critical(threshold_mb=200):
            logger.warning("Storage critical! Running emergency cleanup...")
            self.cleanup_temp_dir(max_age_minutes=5)


# Global singleton
_optimizer: Optional[MemoryOptimizer] = None

def get_memory_optimizer() -> MemoryOptimizer:
    """Get memory optimizer singleton."""
    global _optimizer
    if _optimizer is None:
        _optimizer = MemoryOptimizer()
    return _optimizer
