from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    DATABASE_URL: str = "sqlite+aiosqlite:///bot.db"
    REDIS_URL: str = "redis://redis:6379/0"
    REQUIRED_CHANNEL_ID: int = 0
    ADMIN_IDS: str = "" # Comma separated list of IDs
    WALLET_PAY_API_KEY: str = ""  # Wallet Pay Store API Key
    
    # Local Bot API Server settings (for 2GB file uploads)
    USE_LOCAL_BOT_API: bool = False           # Enable Local Bot API
    LOCAL_BOT_API_URL: str = "http://telegram-bot-api:8081"  # Local API URL
    TELEGRAM_API_ID: Optional[str] = None     # From https://my.telegram.org
    TELEGRAM_API_HASH: Optional[str] = None   # From https://my.telegram.org
    
    # Performance settings (optimized for low-end hardware)
    DOWNLOAD_WORKERS: int = 1         # Single worker for 512MB RAM
    DOWNLOAD_SEMAPHORE: int = 1       # Only 1 concurrent download
    HTTP_TIMEOUT: int = 30            # aiohttp timeout (seconds)
    PROXY_LIST: str = ""              # Comma-separated proxy list
    CDN_FALLBACK: bool = True         # Enable CDN fallback on failure
    
    # Low memory mode (512MB RAM / 2GB storage)
    LOW_MEMORY_MODE: bool = True      # Enable aggressive memory optimization
    MAX_VIDEO_SIZE_MB: float = 45.0   # Skip videos larger than this (increased to 2000 with Local API)
    CHUNK_SIZE: int = 65536           # 64KB chunks for streaming (reduced from default)
    AUTO_CLEANUP: bool = True         # Delete files immediately after upload
    TEMP_DIR: str = "/tmp/bot_dl"     # Temp directory (use RAM disk if available)
    
    # Reliability settings
    MAX_RETRIES: int = 3              # Max retry attempts
    DOWNLOAD_TIMEOUT: int = 180       # Download timeout (seconds)
    RATE_LIMIT: int = 2               # Messages per second
    DOWNLOAD_LIMIT: int = 5           # Downloads per minute
    BURST_LIMIT: int = 10             # Anti-spam burst limit
    
    # Security settings
    MAX_FILE_SIZE_MB: float = 50.0    # Telegram bot limit (2000 with Local API)
    STRICT_WHITELIST: bool = True     # Only allow whitelisted domains
    ENABLE_SSRF_PROTECTION: bool = True  # Block private IPs
    
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
    
    @property
    def effective_max_file_size_mb(self) -> float:
        """Return 2000MB if using Local Bot API, else default."""
        return 2000.0 if self.USE_LOCAL_BOT_API else self.MAX_FILE_SIZE_MB

config = Settings()

