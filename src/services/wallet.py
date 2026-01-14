"""
Wallet service stub.
This module is kept for compatibility but wallet payments are disabled.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WalletService:
    """Stub wallet service - payments disabled."""
    
    _instance: Optional['WalletService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.api_key = None  # No API key = disabled
    
    async def create_order(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Stub - returns None."""
        return None
    
    async def get_order_preview(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Stub - returns None."""
        return None


def get_wallet_service() -> WalletService:
    """Get wallet service singleton."""
    return WalletService()
