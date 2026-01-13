"""Market observers module for event-driven analysis triggers.

Provides:
- BaseObserver: Abstract base class for all observers
- VolatilitySpikeObserver: ATR-based spike detection
- KeyLevelObserver: Support/resistance proximity detection
- MarketObserver: Orchestrator managing all observers
- ObserverEvent: Event dataclass for observer notifications
"""

from src.observers.base_observer import (
    BaseObserver,
    ObserverEvent,
    ObserverEventType,
)
from src.observers.key_level_observer import KeyLevelObserver
from src.observers.market_observer import MarketObserver, get_market_observer
from src.observers.volatility_observer import VolatilitySpikeObserver

__all__ = [
    "BaseObserver",
    "ObserverEvent",
    "ObserverEventType",
    "VolatilitySpikeObserver",
    "KeyLevelObserver",
    "MarketObserver",
    "get_market_observer",
]
