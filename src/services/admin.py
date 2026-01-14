"""
Secure admin management service.
Implements Owner/Admin role hierarchy with security measures.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.main import get_session, User
from src.config import config

logger = logging.getLogger(__name__)


def get_owner_ids() -> List[int]:
    """
    Get Owner IDs from ADMIN_IDS env variable.
    Owners have full control and CANNOT be removed.
    This is the security anchor - only editable via server config.
    """
    if not config.ADMIN_IDS:
        return []
    try:
        return [int(x.strip()) for x in config.ADMIN_IDS.split(',')]
    except ValueError:
        return []


class AdminService:
    """
    Secure admin management service.
    
    Security model:
    - OWNER: Defined in ADMIN_IDS env var (cannot be changed at runtime)
      - Can add/remove Admins
      - Full access to all admin features
      - Cannot be removed by anyone
    
    - ADMIN: Dynamically added by Owner (stored in DB)
      - Can grant premium, manage ads
      - CANNOT add/remove other admins
      - Can be removed by Owner
    
    All admin actions are logged.
    """
    
    _instance: Optional['AdminService'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._owner_ids = get_owner_ids()
    
    def is_owner(self, user_id: int) -> bool:
        """
        Check if user is Owner (from env config).
        Owners have highest privileges and cannot be removed.
        """
        return user_id in self._owner_ids
    
    async def is_admin(self, user_id: int) -> bool:
        """
        Check if user is Admin (Owner or dynamic admin).
        """
        # Owners are always admins
        if self.is_owner(user_id):
            return True
        
        # Check DB for dynamic admin status
        async for session in get_session():
            result = await session.execute(
                select(User.is_admin).where(User.user_id == user_id)
            )
            is_admin = result.scalar()
            return bool(is_admin)
        
        return False
    
    async def get_role(self, user_id: int) -> str:
        """Get user's admin role: 'owner', 'admin', or 'user'."""
        if self.is_owner(user_id):
            return "owner"
        
        async for session in get_session():
            result = await session.execute(
                select(User.is_admin).where(User.user_id == user_id)
            )
            if result.scalar():
                return "admin"
        
        return "user"
    
    async def add_admin(self, user_id: int, by_user_id: int) -> Dict[str, Any]:
        """
        Add new admin. Only Owners can do this.
        
        Args:
            user_id: User to make admin
            by_user_id: Who is performing this action (must be Owner)
        
        Returns:
            Result dict with success status
        """
        # Security check: Only owners can add admins
        if not self.is_owner(by_user_id):
            logger.warning(f"SECURITY: Non-owner {by_user_id} tried to add admin {user_id}")
            return {"success": False, "error": "Only owners can add admins"}
        
        # Cannot add owner as admin (they already have higher role)
        if self.is_owner(user_id):
            return {"success": False, "error": "User is already an owner"}
        
        async for session in get_session():
            # Check if user exists
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            if user.is_admin:
                return {"success": False, "error": "User is already an admin"}
            
            # Grant admin
            await session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(is_admin=True)
            )
            await session.commit()
            
            logger.info(f"ADMIN: Owner {by_user_id} granted admin to {user_id}")
            
            return {
                "success": True,
                "user_id": user_id,
                "username": user.username,
                "full_name": user.full_name
            }
    
    async def remove_admin(self, user_id: int, by_user_id: int) -> Dict[str, Any]:
        """
        Remove admin. Only Owners can do this.
        Cannot remove Owners.
        """
        # Security check: Only owners can remove admins
        if not self.is_owner(by_user_id):
            logger.warning(f"SECURITY: Non-owner {by_user_id} tried to remove admin {user_id}")
            return {"success": False, "error": "Only owners can remove admins"}
        
        # Cannot remove owners
        if self.is_owner(user_id):
            logger.warning(f"SECURITY: Attempt to remove owner {user_id} by {by_user_id}")
            return {"success": False, "error": "Cannot remove owner"}
        
        async for session in get_session():
            await session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(is_admin=False)
            )
            await session.commit()
            
            logger.info(f"ADMIN: Owner {by_user_id} removed admin from {user_id}")
            
            return {"success": True, "user_id": user_id}
    
    async def get_all_admins(self) -> List[Dict[str, Any]]:
        """Get all admins (owners + dynamic admins)."""
        admins = []
        
        # Add owners
        for owner_id in self._owner_ids:
            async for session in get_session():
                result = await session.execute(
                    select(User).where(User.user_id == owner_id)
                )
                user = result.scalar_one_or_none()
                if user:
                    admins.append({
                        "user_id": owner_id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "role": "owner",
                        "removable": False
                    })
                else:
                    admins.append({
                        "user_id": owner_id,
                        "username": None,
                        "full_name": f"Owner {owner_id}",
                        "role": "owner",
                        "removable": False
                    })
        
        # Add dynamic admins
        async for session in get_session():
            result = await session.execute(
                select(User)
                .where(User.is_admin == True)
                .where(User.user_id.notin_(self._owner_ids))
            )
            for user in result.scalars().all():
                admins.append({
                    "user_id": user.user_id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": "admin",
                    "removable": True
                })
        
        return admins
    
    def log_action(self, admin_id: int, action: str, target_id: Optional[int] = None, details: str = ""):
        """Log admin action for audit trail."""
        target_str = f" on user {target_id}" if target_id else ""
        logger.info(f"ADMIN_AUDIT: [{admin_id}] {action}{target_str} - {details}")


# Global singleton
def get_admin_service() -> AdminService:
    """Get admin service singleton."""
    return AdminService()
