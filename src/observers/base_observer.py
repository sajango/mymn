"""Base observer class for event-driven market monitoring.

Provides abstract base class and data structures for all market observers.
All observers must implement check() method that returns ObserverEvent
when condition triggers, None otherwise.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ObserverEventType(str, Enum):
    """Types of observer events."""

    VOLATILITY_SPIKE = "volatility_spike"
    KEY_LEVEL_PROXIMITY = "key_level_proximity"
    VOLATILITY_COMPRESSION = "volatility_compression"


@dataclass
class ObserverEvent:
    """Event emitted by observer when condition triggered.

    Attributes:
        event_type: Type of event from ObserverEventType enum
        timestamp: Unix timestamp when event was triggered
        data: Observer-specific data dictionary
        confidence: 0-1 confidence score for the event
    """

    event_type: ObserverEventType
    timestamp: float
    data: dict = field(default_factory=dict)
    confidence: float = 1.0

    def __post_init__(self):
        """Validate confidence is within bounds."""
        self.confidence = max(0.0, min(1.0, self.confidence))


class BaseObserver(ABC):
    """Abstract base class for market observers.

    All observers must implement check() method that returns
    ObserverEvent when condition triggers, None otherwise.

    Attributes:
        name: Unique identifier for the observer
        enabled: Whether observer is active
        cooldown_seconds: Minimum time between triggers
    """

    def __init__(self, name: str, cooldown_seconds: int = 900):
        """Initialize base observer.

        Args:
            name: Unique observer name
            cooldown_seconds: Cooldown period between triggers (default 15 min)
        """
        self.name = name
        self.enabled = True
        self.cooldown_seconds = cooldown_seconds
        self._last_triggered = 0.0

    def is_cooldown_active(self) -> bool:
        """Check if cooldown period is active.

        Returns:
            True if still in cooldown, False if ready to trigger
        """
        return time.time() - self._last_triggered < self.cooldown_seconds

    def cooldown_remaining(self) -> float:
        """Get remaining cooldown time in seconds.

        Returns:
            Seconds remaining in cooldown, 0 if ready
        """
        remaining = self.cooldown_seconds - (time.time() - self._last_triggered)
        return max(0.0, remaining)

    def mark_triggered(self):
        """Mark observer as triggered, starting cooldown."""
        self._last_triggered = time.time()

    @abstractmethod
    def check(self, market_data: dict) -> Optional[ObserverEvent]:
        """Check if observer condition is met.

        Args:
            market_data: Dict with current_price, atr, etc.

        Returns:
            ObserverEvent if triggered, None otherwise
        """
        pass

    @abstractmethod
    def reset_state(self):
        """Reset observer internal state."""
        pass

    def get_status(self) -> dict:
        """Get observer status summary.

        Returns:
            Dict with name, enabled, cooldown info
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "cooldown_active": self.is_cooldown_active(),
            "cooldown_remaining": self.cooldown_remaining(),
        }
