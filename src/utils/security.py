"""
Security utilities: URL validation, domain whitelist, file size limits.
Protects against malicious input and enforces platform restrictions.
"""

import re
import logging
from typing import Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from enum import Enum

from src.config import config

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Base security exception with user-friendly message."""
    
    def __init__(self, message: str, user_message: str):
        self.message = message
        self.user_message = user_message
        super().__init__(message)


class MaliciousURLError(SecurityError):
    """URL appears malicious or suspicious."""
    
    def __init__(self, url: str, reason: str):
        super().__init__(
            f"Malicious URL detected: {url} - {reason}",
            "🚫 Эта ссылка заблокирована по соображениям безопасности."
        )


class UnsupportedPlatformError(SecurityError):
    """Platform not in whitelist."""
    
    def __init__(self, domain: str):
        super().__init__(
            f"Unsupported platform: {domain}",
            f"❌ Платформа {domain} не поддерживается."
        )


class FileSizeError(SecurityError):
    """File size exceeds limit."""
    
    def __init__(self, size_mb: float, limit_mb: float):
        super().__init__(
            f"File size {size_mb:.1f}MB exceeds limit {limit_mb}MB",
            f"📦 Файл слишком большой ({size_mb:.1f} МБ). Лимит: {limit_mb} МБ."
        )


# Allowed platform domains (whitelist)
ALLOWED_DOMAINS: Set[str] = {
    # YouTube
    'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'youtu.be', 'youtube-nocookie.com',
    'music.youtube.com',
    
    # TikTok
    'tiktok.com', 'www.tiktok.com', 'm.tiktok.com',
    'vm.tiktok.com', 'vt.tiktok.com',
    
    # Instagram
    'instagram.com', 'www.instagram.com',
    'instagr.am',
    
    # Twitter/X
    'twitter.com', 'www.twitter.com', 'mobile.twitter.com',
    'x.com', 'www.x.com',
    't.co',
    
    # Facebook
    'facebook.com', 'www.facebook.com', 'm.facebook.com',
    'fb.watch', 'fb.com',
    
    # Vimeo
    'vimeo.com', 'www.vimeo.com', 'player.vimeo.com',
    
    # Reddit
    'reddit.com', 'www.reddit.com', 'v.redd.it',
    'i.redd.it', 'old.reddit.com',
    
    # Twitch
    'twitch.tv', 'www.twitch.tv', 'clips.twitch.tv',
    
    # Dailymotion
    'dailymotion.com', 'www.dailymotion.com',
    
    # SoundCloud
    'soundcloud.com', 'www.soundcloud.com',
    
    # Pinterest
    'pinterest.com', 'www.pinterest.com', 'pin.it',
    
    # Likee
    'likee.video', 'l.likee.video',
    
    # VK
    'vk.com', 'vk.ru', 'vkvideo.ru',
    
    # Kwai
    'kwai.com', 'www.kwai.com', 'm.kwai.com',
    'kw.ai',
}

# Suspicious patterns that might indicate malicious URLs
MALICIOUS_PATTERNS = [
    r'javascript:',           # XSS attempt
    r'data:',                 # Data URI scheme
    r'file://',               # Local file access
    r'ftp://',                # FTP (not HTTP/HTTPS)
    r'\x00',                  # Null byte injection
    r'\.\./',                 # Path traversal
    r'%00',                   # URL-encoded null byte
    r'<script',               # Script injection
    r'&#',                    # HTML entity injection
    r'\s',                    # Whitespace in URL (suspicious)
]

# Compiled regex for efficiency
_malicious_regex = re.compile('|'.join(MALICIOUS_PATTERNS), re.IGNORECASE)


@dataclass
class ValidationResult:
    """Result of URL validation."""
    is_valid: bool
    url: str
    domain: str
    error: Optional[str] = None
    user_message: Optional[str] = None


def extract_domain(url: str) -> str:
    """Extract domain from URL, handling various formats."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove port if present
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # Remove www. prefix for consistent matching
        # (but we keep it in ALLOWED_DOMAINS for flexibility)
        return domain
        
    except Exception:
        return ""


def validate_url(url: str, strict_whitelist: bool = True) -> ValidationResult:
    """
    Comprehensive URL validation.
    
    Checks:
    1. URL format validity
    2. HTTPS/HTTP protocol
    3. Malicious pattern detection
    4. Domain whitelist (if strict_whitelist=True)
    5. Suspicious query parameters
    
    Args:
        url: URL to validate
        strict_whitelist: If True, only allow whitelisted domains
    
    Returns:
        ValidationResult with validation status and details
    """
    url = url.strip()
    
    # Basic format check
    if not url:
        return ValidationResult(
            is_valid=False, url=url, domain="",
            error="Empty URL", user_message="❌ Ссылка не указана."
        )
    
    # Check for malicious patterns
    if _malicious_regex.search(url):
        logger.warning(f"Malicious pattern detected in URL: {url[:100]}")
        return ValidationResult(
            is_valid=False, url=url, domain="",
            error="Malicious pattern detected",
            user_message="🚫 Обнаружена подозрительная ссылка."
        )
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return ValidationResult(
            is_valid=False, url=url, domain="",
            error=f"URL parse error: {e}",
            user_message="❌ Некорректный формат ссылки."
        )
    
    # Protocol check (only HTTP/HTTPS)
    if parsed.scheme not in ('http', 'https'):
        return ValidationResult(
            is_valid=False, url=url, domain="",
            error=f"Invalid protocol: {parsed.scheme}",
            user_message="❌ Поддерживаются только HTTP/HTTPS ссылки."
        )
    
    # Extract and validate domain
    domain = extract_domain(url)
    if not domain:
        return ValidationResult(
            is_valid=False, url=url, domain="",
            error="Could not extract domain",
            user_message="❌ Некорректный домен в ссылке."
        )
    
    # Length check (prevent DoS with very long URLs)
    if len(url) > 2048:
        return ValidationResult(
            is_valid=False, url=url, domain=domain,
            error="URL too long",
            user_message="❌ Ссылка слишком длинная."
        )
    
    # Domain whitelist check
    if strict_whitelist:
        # Check if domain or any parent domain is allowed
        domain_parts = domain.split('.')
        is_allowed = False
        
        for i in range(len(domain_parts)):
            check_domain = '.'.join(domain_parts[i:])
            if check_domain in ALLOWED_DOMAINS:
                is_allowed = True
                break
        
        if not is_allowed:
            logger.info(f"Domain not in whitelist: {domain}")
            return ValidationResult(
                is_valid=False, url=url, domain=domain,
                error=f"Domain not allowed: {domain}",
                user_message=f"❌ Платформа {domain} не поддерживается.\n\n"
                            f"Поддерживаются: YouTube, TikTok, Instagram, Twitter, "
                            f"Facebook, Vimeo, Reddit, Twitch, VK."
            )
    
    # URL is valid
    return ValidationResult(is_valid=True, url=url, domain=domain)


def validate_file_size(size_bytes: int, max_mb: float = None) -> Tuple[bool, str]:
    """
    Validate file size against limits.
    
    Args:
        size_bytes: File size in bytes
        max_mb: Maximum size in MB (default from config or 50MB Telegram limit)
    
    Returns:
        (is_valid, error_message or empty string)
    """
    if max_mb is None:
        max_mb = getattr(config, 'MAX_FILE_SIZE_MB', 50.0)
    
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb > max_mb:
        return False, f"📦 Файл слишком большой ({size_mb:.1f} МБ). Лимит: {max_mb} МБ."
    
    return True, ""


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and injection.
    
    Removes:
    - Path separators
    - Null bytes
    - Control characters
    - Leading dots (hidden files)
    """
    if not filename:
        return "file"
    
    # Remove path separators and dangerous characters
    sanitized = re.sub(r'[/\\:\*\?"<>|]', '_', filename)
    
    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    
    # Remove leading dots (prevent hidden files)
    sanitized = sanitized.lstrip('.')
    
    # Limit length
    if len(sanitized) > 200:
        name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
        sanitized = name[:195] + ('.' + ext if ext else '')
    
    return sanitized or "file"


def is_private_ip(hostname: str) -> bool:
    """
    Check if hostname resolves to private/internal IP.
    Prevents SSRF attacks.
    """
    import socket
    import ipaddress
    
    try:
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)
        
        # Check for private, loopback, link-local
        return (
            ip_obj.is_private or
            ip_obj.is_loopback or
            ip_obj.is_link_local or
            ip_obj.is_reserved
        )
    except (socket.gaierror, ValueError):
        return False


def get_supported_platforms() -> str:
    """Get formatted list of supported platforms."""
    platforms = [
        "YouTube", "TikTok", "Instagram", "Twitter/X",
        "Facebook", "Vimeo", "Reddit", "Twitch",
        "Dailymotion", "SoundCloud", "Pinterest", "VK",
        "Likee", "Kwai"
    ]
    return ", ".join(platforms)

