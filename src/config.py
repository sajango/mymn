"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core Settings
    telegram_bot_token: str = Field(description="Telegram bot token")
    telegram_chat_id: str = Field(description="Telegram chat ID for notifications")
    mt5_path: str = Field(
        default="C:/Program Files/MetaTrader 5/terminal64.exe",
        description="Path to MT5 terminal",
    )
    mt5_symbol: str = Field(default="XAUUSD", description="Trading symbol")
    risk_percent: float = Field(
        default=1.5, ge=0.1, le=5.0, description="Risk percentage per trade"
    )
    max_position_size: float = Field(
        default=0.1, ge=0.01, le=1.0, description="Maximum position size in lots"
    )

    # Position Sizing Mode
    use_fixed_lots: bool = Field(
        default=False, description="Use fixed lot size instead of risk-based calculation"
    )
    fixed_lot_size: float = Field(
        default=0.03, ge=0.01, le=1.0, description="Fixed lot size when use_fixed_lots=true"
    )
    paper_trading: bool = Field(default=True, description="Enable paper trading mode")
    claude_timeout: int = Field(
        default=300, ge=60, le=600, description="Claude CLI timeout in seconds"
    )

    # Slippage Settings
    max_slippage: int = Field(
        default=20, ge=0, le=100, description="Maximum slippage in points"
    )
    expected_slippage_pips: float = Field(
        default=1.0, ge=0, le=10, description="Expected slippage in pips"
    )

    # Session Confidence Adjustments
    session_confidence_overlap: int = Field(
        default=10, description="Confidence boost during session overlap"
    )
    session_confidence_london: int = Field(
        default=5, description="Confidence boost during London session"
    )
    session_confidence_ny: int = Field(
        default=5, description="Confidence boost during NY session"
    )
    session_confidence_asian: int = Field(
        default=-15, description="Confidence adjustment during Asian session"
    )
    session_confidence_offhours: int = Field(
        default=-20, description="Confidence adjustment during off-hours"
    )

    # Spread Settings
    max_spread_pips: float = Field(
        default=4.0, ge=0.5, le=20, description="Maximum spread to enter trade"
    )

    # Trailing Stop Settings
    trail_atr_multiplier: float = Field(
        default=1.5, ge=0.5, le=5, description="ATR multiplier for trailing stop"
    )
    breakeven_buffer_pips: int = Field(
        default=5, ge=0, le=50, description="Pips above entry for breakeven"
    )

    # News Filter Settings
    news_blackout_before_mins: int = Field(
        default=30, ge=0, le=120, description="Minutes before news to avoid trading"
    )
    news_blackout_after_mins: int = Field(
        default=15, ge=0, le=60, description="Minutes after news to avoid trading"
    )

    # Confidence Thresholds
    confidence_threshold: int = Field(
        default=60, ge=0, le=100, description="Minimum confidence to trade"
    )
    confidence_full_position: int = Field(
        default=75, ge=0, le=100, description="Confidence for full position"
    )
    confidence_half_position: int = Field(
        default=60, ge=0, le=100, description="Confidence for half position"
    )

    # Database Settings
    database_path: str = Field(
        default="data/trades.db", description="SQLite database path"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )
    log_path: str = Field(default="logs/trading.log", description="Log file path")

    # Signal Settings
    signal_timeout: int = Field(
        default=300, ge=60, le=600, description="Signal expiration timeout in seconds"
    )

    # Auto-Trading Settings
    auto_trade_enabled: bool = Field(
        default=False, description="Enable automatic trade execution"
    )
    auto_trade_confidence: int = Field(
        default=75, ge=50, le=100, description="Minimum confidence for auto-execution"
    )
    auto_trade_max_daily: int = Field(
        default=5, ge=1, le=20, description="Maximum auto-trades per day"
    )

    # Risk Guard Settings
    max_concurrent_positions: int = Field(
        default=2, ge=1, le=10, description="Maximum concurrent open positions"
    )
    max_total_lots: float = Field(
        default=0.2, ge=0.01, le=5.0, description="Maximum total lot exposure"
    )
    max_account_risk_percent: float = Field(
        default=3.0, ge=0.5, le=10.0, description="Maximum account risk percentage"
    )
    opposite_position_policy: Literal["reject", "close_first", "hedge"] = Field(
        default="close_first",
        description="Policy for handling opposite direction signals",
    )
    duplicate_cooldown_minutes: int = Field(
        default=15, ge=1, le=120, description="Minutes to block duplicate signals"
    )

    # Key Level Proximity Settings
    key_level_proximity_enabled: bool = Field(
        default=True, description="Enable key level proximity validation"
    )
    key_level_proximity_atr_multiplier: float = Field(
        default=1.5, ge=0.5, le=5.0, description="ATR multiplier for safe distance"
    )
    key_level_proximity_min_pips: float = Field(
        default=10.0, ge=1.0, le=100.0, description="Minimum safe distance in pips"
    )

    # Signal Consistency Filter Settings
    direction_change_cooldown_minutes: int = Field(
        default=60, ge=15, le=240,
        description="Minutes before allowing direction change"
    )
    direction_change_min_confidence: int = Field(
        default=75, ge=50, le=100,
        description="Minimum confidence required for direction reversal"
    )
    rapid_flip_threshold_minutes: int = Field(
        default=30, ge=10, le=120,
        description="Minutes threshold for rapid flip-flop detection"
    )

    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent

    @property
    def data_dir(self) -> Path:
        """Get the data directory."""
        return self.project_root / "data"

    @property
    def csv_dir(self) -> Path:
        """Get the CSV export directory."""
        return self.data_dir / "csv"

    @property
    def logs_dir(self) -> Path:
        """Get the logs directory."""
        return self.project_root / "logs"

    @property
    def db_path(self) -> Path:
        """Get the database path."""
        return self.project_root / self.database_path

    @property
    def log_file(self) -> Path:
        """Get the log file path."""
        return self.project_root / self.log_path


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
