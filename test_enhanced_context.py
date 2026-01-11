"""Test enhanced context system."""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.database import Database
from src.signal_parser import TradingSignal

# Create test database
db_path = Path("test_context.db")
if db_path.exists():
    db_path.unlink()

db = Database(db_path)

# Create test signal
signal_data = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "symbol": "XAUUSD",
    "signal": {
        "action": "BUY",
        "confidence": 75,
        "entry_price": 2645.50,
        "stop_loss": 2640.00,
        "take_profit": [
            {"level": "TP1", "price": 2650.00, "close_percent": 50},
            {"level": "TP2", "price": 2655.00, "close_percent": 30},
            {"level": "TP3", "price": 2660.00, "close_percent": 20}
        ],
        "risk_reward": 2.5,
        "reason": "Wave 3 bullish impulse"
    },
    "wave_analysis": {
        "h4_trend": "bullish",
        "h1_trend": "bullish",
        "current_wave": "3",
        "wave_position": "Wave 3 of (3)"
    }
}

# Parse signal
signal_json = json.dumps(signal_data)
signal = TradingSignal.model_validate_json(signal_json)

# Save signal
signal_id = db.save_signal(signal)
print(f"Saved signal ID: {signal_id}")

# Save market memory
db.save_market_memory(
    memory_type="wave_count",
    key="current_wave",
    value="Wave 3 of (3)",
    confidence=75,
    expires_hours=24
)

db.save_market_memory(
    memory_type="pattern",
    key="bullish_impulse",
    value="Strong bullish impulse wave identified",
    confidence=80,
    expires_hours=12
)

# Get enhanced context
context = db.get_enhanced_signal_context(limit=5)

print("\n=== Enhanced Signal Context ===")
print(json.dumps(context, indent=2))

# Clean up
db_path.unlink()
print("\nTest completed successfully!")