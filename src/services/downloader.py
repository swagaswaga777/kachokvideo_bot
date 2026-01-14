import os
import asyncio
import logging
import uuid
import subprocess
from typing import Dict, Any, Optional
from concurrent.futures import ProcessPoolExecutor
import yt_dlp

from src.config import config
from src.utils.reliability import (
    retry, RetryStrategy, with_timeout,
    DownloadError, ContentNotFoundError, RateLimitError, get_user_error_message
)
from src.utils.memory import get_memory_optimizer

logger = logging.getLogger(__name__)

# Process pool for CPU-bound FFmpeg operations
_process_pool: Optional[ProcessPoolExecutor] = None

def get_process_pool() -> ProcessPoolExecutor:
    """Get or create process pool for CPU-bound operations."""
    global _process_pool
    if _process_pool is None:
        max_workers = 1 if config.LOW_MEMORY_MODE else 4
        _process_pool = ProcessPoolExecutor(max_workers=max_workers)
    return _process_pool


class DownloaderService:
    def __init__(self, download_path: str = None):
        self.download_path = download_path or config.TEMP_DIR
        os.makedirs(self.download_path, exist_ok=True)
        self.semaphore = asyncio.Semaphore(config.DOWNLOAD_SEMAPHORE)
        self.memory_optimizer = get_memory_optimizer()
        
    def _get_common_opts(self) -> dict:
        """Common yt-dlp options for all downloads."""
        return {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,  # Don't ignore errors - we want to handle them
            'no_color': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') and os.path.getsize('cookies.txt') > 0 else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            'socket_timeout': 30,
            'retries': 3,
        }

    @retry(max_attempts=2, strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0)
    @with_timeout(180.0, "Download")
    async def download_media(self, url: str, time_range: Optional[tuple] = None, quality: str = "max") -> Optional[Dict[str, Any]]:
        """Download media from URL."""
        async with self.semaphore:
            file_id = str(uuid.uuid4())
            
            # Detect platform
            is_tiktok = any(d in url.lower() for d in ['tiktok.com', 'vm.tiktok'])
            is_youtube = any(d in url.lower() for d in ['youtube.com', 'youtu.be'])
            is_instagram = 'instagram.com' in url.lower()
            
            # For TikTok and Instagram, try fallback APIs first (more reliable)
            if is_tiktok or is_instagram:
                from src.services.fallback import download_with_fallback
                
                logger.info(f"Using fallback API for {'TikTok' if is_tiktok else 'Instagram'}")
                fallback_result = await download_with_fallback(url, self.download_path)
                
                if fallback_result and fallback_result.get("path"):
                    # Return video directly without conversion (fallback APIs provide ready MP4)
                    if fallback_result.get("ext") == "mp4":
                        return {
                            'type': 'video',
                            'path': fallback_result["path"],
                            'title': fallback_result.get("title", "Video"),
                            'ext': 'mp4',
                        }
                    else:
                        # Image - return as is
                        return {
                            'type': 'image',
                            'paths': [fallback_result["path"]],
                            'title': fallback_result.get("title", "Image"),
                        }
                
                logger.warning(f"Fallback failed, trying yt-dlp...")
            
            # Standard yt-dlp download (for YouTube and as fallback)
            try:
                raw_path = await self._download_raw(url, file_id, quality)
                if not raw_path:
                    return None
                
                final_path = await self._convert_to_telegram_mp4(raw_path, file_id)
                
                if final_path != raw_path and os.path.exists(raw_path):
                    self.delete_file(raw_path)
                
                if not final_path or not os.path.exists(final_path):
                    return None
                
                title = await self._get_title(url)
                
                return {
                    'type': 'video',
                    'path': final_path,
                    'title': title or 'Video',
                    'ext': 'mp4',
                }
                
            except Exception as e:
                logger.error(f"Download error for {url}: {e}")
                return None

    async def _download_raw(self, url: str, file_id: str, quality: str) -> Optional[str]:
        """Download video in best format (prefer MP4 without merge)."""
        loop = asyncio.get_event_loop()
        
        # Format selection - prefer single file formats that don't need FFmpeg merge
        # Order: best single MP4 > best single video > merged (if FFmpeg available)
        if quality == "max" or not quality.isdigit():
            format_str = 'best[ext=mp4]/best/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio'
        else:
            h = quality
            format_str = f'best[height<={h}][ext=mp4]/best[height<={h}]/bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]'
        
        opts = self._get_common_opts()
        opts.update({
            'format': format_str,
            'outtmpl': f'{self.download_path}/{file_id}.%(ext)s',
            'merge_output_format': 'mp4',
            'prefer_free_formats': False,  # Prefer MP4 over webm
        })
        
        def do_download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        
        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, do_download),
                timeout=120.0
            )
            
            if not info:
                return None
            
            # Find downloaded file
            import glob
            files = glob.glob(f'{self.download_path}/{file_id}.*')
            if files:
                return files[0]
            return None
            
        except Exception as e:
            logger.error(f"Raw download error: {e}")
            return None

    async def _convert_to_telegram_mp4(self, input_path: str, file_id: str) -> Optional[str]:
        """Convert video to Telegram-compatible H.264 MP4."""
        output_path = f"{self.download_path}/{file_id}_final.mp4"
        
        # Check if already proper MP4 with H.264
        if input_path.endswith('.mp4'):
            # Probe to check codec
            probe_result = await self._probe_video(input_path)
            if probe_result and probe_result.get('codec') == 'h264':
                # Already good, just copy
                return input_path
        
        # Convert with FFmpeg - H.264 for maximum compatibility
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-c:v', 'libx264',          # H.264 codec
            '-preset', 'fast',           # Balance speed/quality
            '-crf', '23',                # Quality (lower = better, 18-28 is good)
            '-pix_fmt', 'yuv420p',       # Pixel format for compatibility
            '-profile:v', 'high',        # H.264 profile
            '-level', '4.1',             # Level for HD
            '-movflags', '+faststart',   # Web/Telegram optimization
            '-c:a', 'aac',               # AAC audio
            '-b:a', '192k',              # Audio bitrate
            '-ar', '44100',              # Audio sample rate
            '-ac', '2',                  # Stereo audio
            '-max_muxing_queue_size', '1024',
            output_path
        ]
        
        loop = asyncio.get_event_loop()
        
        try:
            process = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    timeout=300
                )
            )
            
            if process.returncode == 0 and os.path.exists(output_path):
                # Verify output is not empty
                if os.path.getsize(output_path) > 1000:
                    logger.info(f"Converted to H.264 MP4: {output_path}")
                    return output_path
                else:
                    logger.error("Converted file too small")
                    os.remove(output_path)
                    return None
            else:
                logger.error(f"FFmpeg error: {process.stderr.decode()[:500]}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out")
            return None
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            return None

    async def _probe_video(self, path: str) -> Optional[dict]:
        """Probe video to get codec info."""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'csv=p=0',
                path
            ]
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=10)
            )
            if result.returncode == 0:
                codec = result.stdout.decode().strip()
                return {'codec': codec}
        except:
            pass
        return None

    async def _get_title(self, url: str) -> str:
        """Get video title without downloading."""
        try:
            opts = self._get_common_opts()
            opts['skip_download'] = True
            
            loop = asyncio.get_event_loop()
            
            def extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        if 'entries' in info:
                            return info['entries'][0].get('title', 'Video')
                        return info.get('title', 'Video')
                return 'Video'
            
            return await asyncio.wait_for(
                loop.run_in_executor(None, extract),
                timeout=15.0
            )
        except:
            return 'Video'

    async def download_audio(self, url: str) -> Optional[Dict[str, Any]]:
        """Download audio from URL."""
        async with self.semaphore:
            file_id = str(uuid.uuid4())
            
            opts = self._get_common_opts()
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': f'{self.download_path}/{file_id}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            
            loop = asyncio.get_event_loop()
            
            try:
                def do_download():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=True)
                
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, do_download),
                    timeout=120.0
                )
                
                if not info:
                    return None
                
                mp3_path = f"{self.download_path}/{file_id}.mp3"
                if os.path.exists(mp3_path):
                    return {
                        'path': mp3_path,
                        'title': info.get('title', 'Audio'),
                        'ext': 'mp3',
                    }
                return None
                
            except Exception as e:
                logger.error(f"Audio download error: {e}")
                return None

    async def get_thumbnail_url(self, url: str) -> Optional[str]:
        """Get thumbnail URL for video."""
        try:
            opts = self._get_common_opts()
            opts['skip_download'] = True
            
            loop = asyncio.get_event_loop()
            
            async with self.semaphore:
                def extract():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if info:
                            if 'entries' in info:
                                info = info['entries'][0]
                            return info.get('thumbnail')
                    return None
                
                return await asyncio.wait_for(
                    loop.run_in_executor(None, extract),
                    timeout=15.0
                )
        except Exception as e:
            logger.error(f"Thumbnail error: {e}")
            return None

    def delete_file(self, file_path: str):
        """Delete file from disk."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted {file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
