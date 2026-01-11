"""Test configuration module."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_settings_import() -> None:
    """Test that Settings class can be imported and instantiated."""
    # Set required env vars
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
    os.environ["TELEGRAM_CHAT_ID"] = "test_chat_id"

    from src.config import Settings

    # Create settings without env file
    settings = Settings(_env_file=None)

    # Verify defaults
    assert settings.mt5_symbol == "XAUUSD"
    assert settings.risk_percent == 1.5
    assert settings.paper_trading is True
    assert settings.claude_timeout == 300
    assert settings.max_spread_pips == 4.0
    assert settings.confidence_threshold == 50
    assert settings.project_root.exists()
    assert "mymn" in str(settings.project_root)

    print("All config tests passed!")


if __name__ == "__main__":
    test_settings_import()
