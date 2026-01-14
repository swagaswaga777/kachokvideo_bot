"""
Fallback download services for TikTok and Instagram.
Uses public APIs when yt-dlp fails.
"""

import aiohttp
import ssl
import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Timeout for API requests
API_TIMEOUT = 30

# Disable SSL verification for some problematic APIs
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


class TikTokFallback:
    """TikTok fallback using public APIs."""
    
    @staticmethod
    async def download(url: str) -> Optional[Dict[str, Any]]:
        """Try to get TikTok video URL using fallback APIs."""
        
        # Try tikwm.com first
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                connector=connector
            ) as session:
                async with session.post(
                    "https://www.tikwm.com/api/",
                    data={"url": url, "hd": 1},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json",
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 0 and data.get("data"):
                            video_data = data["data"]
                            video_url = video_data.get("hdplay") or video_data.get("play")
                            if video_url:
                                return {
                                    "video_url": video_url,
                                    "title": video_data.get("title", "TikTok Video"),
                                    "author": video_data.get("author", {}).get("nickname", ""),
                                    "cover": video_data.get("cover"),
                                }
        except Exception as e:
            logger.warning(f"tikwm.com failed: {e}")
        
        # Try alternative API
        try:
            video_id = TikTokFallback._extract_video_id(url)
            if not video_id:
                logger.warning(f"Could not extract video ID from URL: {url}")
                return None
                
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                connector=connector
            ) as session:
                async with session.post(
                    "https://api22-normal-c-useast1a.tiktokv.com/aweme/v1/feed/",
                    params={"aweme_id": video_id},
                    headers={
                        "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 12; en_US; SM-G998B; Build/SP1A.210812.016; Cronet/58.0.2991.0)",
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("aweme_list"):
                            aweme = data["aweme_list"][0]
                            video = aweme.get("video", {})
                            play_addr = video.get("play_addr", {})
                            url_list = play_addr.get("url_list", [])
                            if url_list:
                                return {
                                    "video_url": url_list[0],
                                    "title": aweme.get("desc", "TikTok Video"),
                                }
        except Exception as e:
            logger.warning(f"TikTok API v2 failed: {e}")
        
        return None
    
    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:
        """Extract TikTok video ID from URL."""
        patterns = [
            r"tiktok\.com/.*/video/(\d+)",
            r"tiktok\.com/@[^/]+/(\d+)",
            r"vm\.tiktok\.com/(\w+)",
            r"vt\.tiktok\.com/(\w+)",
            r"/(\d{15,25})"  # Fallback: any 15-25 digit number in URL
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


class InstagramFallback:
    """Instagram fallback using public APIs."""
    
    @staticmethod
    async def download(url: str) -> Optional[Dict[str, Any]]:
        """Try to get Instagram video/image URL using fallback APIs."""
        
        shortcode = InstagramFallback._extract_shortcode(url)
        if not shortcode:
            return None
        
        # Try method 1: Instagram embed API
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                connector=connector
            ) as session:
                embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
                async with session.get(
                    embed_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    }
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        video_match = re.search(r'"video_url":"([^"]+)"', html)
                        if video_match:
                            video_url = video_match.group(1).replace("\\u0026", "&")
                            return {
                                "video_url": video_url,
                                "title": "Instagram Video",
                                "type": "video",
                            }
                        
                        img_match = re.search(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', html)
                        if img_match:
                            return {
                                "video_url": img_match.group(1),
                                "title": "Instagram Post",
                                "type": "image",
                            }
        except Exception as e:
            logger.warning(f"Instagram embed failed: {e}")
        
        # Try method 2: Alternative API
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                connector=connector
            ) as session:
                api_url = "https://www.instagram.com/graphql/query/"
                params = {
                    "query_hash": "b3055c01b4b222b8a47dc12b090e4e64",
                    "variables": f'{{"shortcode":"{shortcode}"}}',
                }
                async with session.get(
                    api_url,
                    params=params,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "X-IG-App-ID": "936619743392459",
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        media = data.get("data", {}).get("shortcode_media", {})
                        if media:
                            video_url = media.get("video_url")
                            if video_url:
                                return {
                                    "video_url": video_url,
                                    "title": media.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", "Video")[:50],
                                    "type": "video",
                                }
                            display_url = media.get("display_url")
                            if display_url:
                                return {
                                    "video_url": display_url,
                                    "title": "Instagram Post",
                                    "type": "image",
                                }
        except Exception as e:
            logger.warning(f"Instagram GraphQL failed: {e}")
        
        return None
    
    @staticmethod
    def _extract_shortcode(url: str) -> Optional[str]:
        """Extract Instagram shortcode from URL."""
        patterns = [
            r"instagram\.com/p/([A-Za-z0-9_-]+)",
            r"instagram\.com/reel/([A-Za-z0-9_-]+)",
            r"instagram\.com/reels/([A-Za-z0-9_-]+)",
            r"instagram\.com/tv/([A-Za-z0-9_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


async def download_with_fallback(url: str, download_path: str) -> Optional[Dict[str, Any]]:
    """
    Download video using fallback APIs.
    Returns dict with video_url, title, and optionally local path.
    """
    import aiofiles
    import uuid
    import os
    
    result = None
    
    # Detect platform
    if "tiktok.com" in url.lower() or "vm.tiktok" in url.lower():
        result = await TikTokFallback.download(url)
    elif "instagram.com" in url.lower():
        result = await InstagramFallback.download(url)
    
    if not result or not result.get("video_url"):
        return None
    
    # Download the actual video file
    try:
        file_id = str(uuid.uuid4())
        file_ext = "mp4" if result.get("type") != "image" else "jpg"
        output_path = f"{download_path}/{file_id}.{file_ext}"
        
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120),
            connector=connector
        ) as session:
            async with session.get(
                result["video_url"],
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/" if "tiktok" in url.lower() else "https://www.instagram.com/",
                }
            ) as resp:
                if resp.status == 200:
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            await f.write(chunk)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                        result["path"] = output_path
                        result["ext"] = file_ext
                        return result
    except Exception as e:
        logger.error(f"Fallback download failed: {e}")
    
    return None
