from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, String, DateTime, func, text, Boolean, Integer, Float
from src.config import config
from datetime import datetime
from typing import Optional

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    joined_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    
    # Settings
    language: Mapped[str] = mapped_column(String, default="ru")
    quality: Mapped[str] = mapped_column(String, default="mobile")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Admin role (dynamic, can be granted by Owner)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Premium fields
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_until: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    subscription_type: Mapped[str] = mapped_column(String, default="free")  # free, week, month, year, lifetime
    
    # Stats
    total_downloads: Mapped[int] = mapped_column(Integer, default=0)


class Subscription(Base):
    """Subscription plans configuration."""
    __tablename__ = "subscriptions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)  # week, month, year, lifetime
    display_name: Mapped[str] = mapped_column(String)  # "Неделя", "Месяц"
    duration_days: Mapped[int] = mapped_column(Integer)  # 7, 30, 365, 0 (0 = lifetime)
    price_stars: Mapped[int] = mapped_column(Integer, default=0)  # Telegram Stars price
    price_rub: Mapped[float] = mapped_column(Float, default=0.0)  # RUB price
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Sort order


class Ad(Base):
    """Advertisement configuration."""
    __tablename__ = "ads"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)  # Internal name
    text: Mapped[str] = mapped_column(String)  # Ad message text
    media_type: Mapped[str] = mapped_column(String, nullable=True)  # photo, video, None
    media_file_id: Mapped[str] = mapped_column(String, nullable=True)  # Telegram file_id
    button_text: Mapped[str] = mapped_column(String, nullable=True)  # Button label
    button_url: Mapped[str] = mapped_column(String, nullable=True)  # Button URL
    frequency: Mapped[int] = mapped_column(Integer, default=5)  # Show every N downloads
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Payment(Base):
    """Payment history."""
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    subscription_name: Mapped[str] = mapped_column(String)
    amount_stars: Mapped[int] = mapped_column(Integer, default=0)
    amount_rub: Mapped[float] = mapped_column(Float, default=0.0)
    payment_method: Mapped[str] = mapped_column(String)  # stars, wallet
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, completed, failed
    telegram_payment_id: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)


class BotSettings(Base):
    __tablename__ = "bot_settings"
    
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=True) # JSON serialized string

engine = create_async_engine(config.DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Simple migration hack for dev - add new columns
        migrations = [
            "ALTER TABLE users ADD COLUMN language VARCHAR DEFAULT 'ru'",
            "ALTER TABLE users ADD COLUMN quality VARCHAR DEFAULT 'mobile'",
            "ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN is_premium BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN premium_until DATETIME",
            "ALTER TABLE users ADD COLUMN subscription_type VARCHAR DEFAULT 'free'",
            "ALTER TABLE users ADD COLUMN total_downloads INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
