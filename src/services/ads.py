"""
Ad service stub.
This module is kept for compatibility but ad features are disabled.
"""

import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class AdService:
    """Stub ad service - ads are disabled."""
    
    _instance: Optional['AdService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def should_show_ad(self, user_id: int) -> bool:
        """Always returns False - ads disabled."""
        return False
    
    async def get_active_ads(self) -> List:
        """Return empty list."""
        return []
    
    async def get_random_ad(self):
        """Return None - no ads."""
        return None
    
    async def record_view(self, ad_id: int):
        """Stub - does nothing."""
        pass
    
    async def record_click(self, ad_id: int):
        """Stub - does nothing."""
        pass
    
    async def create_ad(self, *args, **kwargs):
        """Stub - does nothing."""
        return None
    
    async def update_ad(self, *args, **kwargs) -> bool:
        """Stub - does nothing."""
        return False
    
    async def toggle_ad(self, ad_id: int) -> bool:
        """Stub - does nothing."""
        return False
    
    async def delete_ad(self, ad_id: int) -> bool:
        """Stub - does nothing."""
        return False
    
    async def get_all_ads(self) -> List:
        """Return empty list."""
        return []
    
    async def get_ad_by_id(self, ad_id: int):
        """Return None."""
        return None


def get_ad_service() -> AdService:
    """Get ad service singleton."""
    return AdService()
