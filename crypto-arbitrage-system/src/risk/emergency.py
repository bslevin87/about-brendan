"""
Emergency controls and kill switch.

Provides manual emergency controls:
- Kill switch for immediate trading halt
- Emergency shutdown
- Manual state override
- Status monitoring
"""
from datetime import datetime
from typing import Dict, Optional

from src.core.logger import get_logger

logger = get_logger(__name__, component="emergency")


class EmergencyController:
    """
    Emergency controls and kill switch.

    Provides:
    - Manual kill switch
    - Emergency shutdown
    - State override
    - Manual resume
    """

    def __init__(self):
        """Initialize emergency controller."""
        self.kill_switch_activated = False
        self.kill_switch_reason: Optional[str] = None
        self.kill_switch_timestamp: Optional[datetime] = None

        logger.info("Emergency controller initialized")

    def activate_kill_switch(self, reason: str) -> None:
        """
        Activate kill switch - immediately halt all trading.

        Args:
            reason: Reason for activation
        """
        self.kill_switch_activated = True
        self.kill_switch_reason = reason
        self.kill_switch_timestamp = datetime.utcnow()

        logger.critical(
            "🚨 KILL SWITCH ACTIVATED",
            reason=reason,
            timestamp=self.kill_switch_timestamp.isoformat(),
        )

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch - allow trading to resume."""
        if not self.kill_switch_activated:
            logger.warning("kill_switch_not_active", message="Kill switch was not activated")
            return

        previous_reason = self.kill_switch_reason
        self.kill_switch_activated = False
        self.kill_switch_reason = None

        logger.info(
            "✅ Kill switch deactivated",
            previous_reason=previous_reason,
        )

    def is_kill_switch_active(self) -> bool:
        """
        Check if kill switch is currently active.

        Returns:
            True if kill switch is active, False otherwise
        """
        return self.kill_switch_activated

    def get_kill_switch_status(self) -> Dict[str, any]:
        """
        Get current kill switch status.

        Returns:
            Dictionary with kill switch state
        """
        return {
            "active": self.kill_switch_activated,
            "reason": self.kill_switch_reason,
            "activated_at": (
                self.kill_switch_timestamp.isoformat()
                if self.kill_switch_timestamp
                else None
            ),
        }

    def reset(self) -> None:
        """Reset emergency controller (deactivate kill switch)."""
        if self.kill_switch_activated:
            self.deactivate_kill_switch()
