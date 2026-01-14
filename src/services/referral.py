"""
Referral service stub.
This module is kept for compatibility but referral features are disabled.
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ReferralService:
    """Stub referral service - referrals are disabled."""
    
    _instance: Optional['ReferralService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_referral_link(self, user_id: int, bot_username: str) -> str:
        """Return simple bot link."""
        return f"https://t.me/{bot_username}"
    
    async def process_referral(self, *args, **kwargs) -> Dict[str, Any]:
        """Stub - referrals disabled."""
        return {"success": False, "error": "Referrals disabled"}
    
    async def get_user_referrals(self, user_id: int) -> Dict[str, Any]:
        """Return empty stats."""
        return {"total_referrals": 0, "bonus_days_earned": 0}
    
    async def get_top_referrers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return empty list."""
        return []
    
    async def get_top_active_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return empty list."""
        return []
    
    async def get_referral_stats(self) -> Dict[str, Any]:
        """Return empty stats."""
        return {"total_referrals": 0, "users_with_referrals": 0, "bonus_days_distributed": 0}


def get_referral_service() -> ReferralService:
    """Get referral service singleton."""
    return ReferralService()
