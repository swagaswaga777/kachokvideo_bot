"""
Premium service stub.
This module is kept for compatibility but premium features are disabled.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# All users have the same limits now
LIMITS = {
    "free": {
        "downloads_per_day": 100,
        "max_quality": "max",
        "priority": 0,
        "scheduled_downloads": 10,
        "show_ads": False,
    }
}


class PremiumService:
    """Stub premium service - all users are treated equally."""
    
    _instance: Optional['PremiumService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def is_premium(self, user_id: int) -> bool:
        """Always returns False - premium disabled."""
        return False
    
    async def get_user_tier(self, user_id: int) -> str:
        """Always returns free tier."""
        return "free"
    
    async def get_limits(self, user_id: int) -> Dict[str, Any]:
        """Return standard limits for all users."""
        return LIMITS["free"].copy()
    
    async def grant_premium(self, *args, **kwargs) -> bool:
        """Stub - does nothing."""
        return False
    
    async def revoke_premium(self, *args, **kwargs) -> bool:
        """Stub - does nothing."""
        return False
    
    async def get_premium_info(self, user_id: int) -> Dict[str, Any]:
        """Return basic info for any user."""
        from src.database.main import get_session, User
        from sqlalchemy import select
        
        async for session in get_session():
            result = await session.execute(
                select(User.total_downloads).where(User.user_id == user_id)
            )
            total = result.scalar() or 0
        
        return {
            "is_premium": False,
            "tier": "free",
            "subscription_type": "free",
            "premium_until": None,
            "total_downloads": total,
            "limits": LIMITS["free"],
            "days_left": None
        }
    
    async def get_subscriptions(self) -> list:
        """Return empty list - no subscriptions available."""
        return []
    
    async def increment_downloads(self, user_id: int):
        """Increment download counter."""
        from src.database.main import get_session, User
        from sqlalchemy import update
        
        async for session in get_session():
            await session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(total_downloads=User.total_downloads + 1)
            )
            await session.commit()


def get_premium_service() -> PremiumService:
    """Get premium service singleton."""
    return PremiumService()
