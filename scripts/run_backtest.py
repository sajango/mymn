#!/usr/bin/env python3
"""CLI script to run backtesting on historical data.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --symbol XAUUSD --confidence 60
    python scripts/run_backtest.py --help

Examples:
    # Run with defaults
    python scripts/run_backtest.py

    # Custom confidence threshold
    python scripts/run_backtest.py --confidence 70

    # Export to file
    python scripts/run_backtest.py --output reports/backtest_result.md

    # Date range filter
    python scripts/run_backtest.py --start 2025-01-01 --end 2025-12-31
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    RuleBasedSignalGenerator,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run backtesting on historical trading data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_backtest.py
  python scripts/run_backtest.py --confidence 70 --risk 2.0
  python scripts/run_backtest.py --start 2025-01-01 --end 2025-06-30
        """,
    )

    # Data settings
    parser.add_argument(
        "--data-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "backtest",
        help="Path to backtest data directory (default: data/backtest)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="XAUUSD",
        help="Trading symbol (default: XAUUSD)",
    )

    # Trading settings
    parser.add_argument(
        "--confidence",
        type=int,
        default=60,
        help="Minimum confidence threshold (default: 60)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10000.0,
        help="Initial balance in USD (default: 10000)",
    )
    parser.add_argument(
        "--risk",
        type=float,
        default=1.5,
        help="Risk percent per trade (default: 1.5)",
    )

    # Simulation settings
    parser.add_argument(
        "--slippage",
        type=float,
        default=1.0,
        help="Slippage in pips (default: 1.0)",
    )
    parser.add_argument(
        "--spread",
        type=float,
        default=2.5,
        help="Spread in pips (default: 2.5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (default: None)",
    )

    # Date range
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD (default: all data)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date YYYY-MM-DD (default: all data)",
    )

    # Output settings
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for report (default: print to stdout)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # Validate data path
    if not args.data_path.exists():
        logger.error("Data path does not exist: %s", args.data_path)
        logger.info("Please export historical data first using:")
        logger.info("  from src.backtest_engine import export_historical_data")
        logger.info("  export_historical_data()")
        return 1

    # Check for CSV files
    csv_files = list(args.data_path.glob(f"{args.symbol}_*.csv"))
    if not csv_files:
        logger.error("No CSV files found for %s in %s", args.symbol, args.data_path)
        return 1

    logger.info("Found %d data files for %s", len(csv_files), args.symbol)

    # Create config
    try:
        config = BacktestConfig(
            data_path=args.data_path,
            symbol=args.symbol,
            min_confidence=args.confidence,
            initial_balance=args.balance,
            risk_percent=args.risk,
            slippage_pips=args.slippage,
            spread_pips=args.spread,
            random_seed=args.seed,
        )
    except ValueError as e:
        logger.error("Invalid configuration: %s", e)
        return 1

    # Create engine
    generator = RuleBasedSignalGenerator(config=config)
    engine = BacktestEngine(config=config, signal_generator=generator)

    # Load data
    logger.info("Loading data...")
    try:
        engine.load_data()
    except Exception as e:
        logger.error("Failed to load data: %s", e)
        return 1

    # Parse dates
    start_date = parse_date(args.start) if args.start else None
    end_date = parse_date(args.end) if args.end else None

    # Run backtest
    logger.info("Running backtest...")
    logger.info("  Symbol: %s", args.symbol)
    logger.info("  Min Confidence: %d%%", args.confidence)
    logger.info("  Risk per Trade: %.1f%%", args.risk)

    try:
        result = engine.run(start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.error("Backtest failed: %s", e)
        return 1

    # Generate report
    report = result.generate_report()

    # Output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        logger.info("Report saved to: %s", args.output)
    else:
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)

    # Summary
    logger.info("Backtest complete!")
    logger.info("  Total Trades: %d", result.total_trades)
    logger.info("  Win Rate: %.1f%%", result.win_rate)
    logger.info("  Profit Factor: %.2f", result.profit_factor)
    logger.info("  Max Drawdown: %.1f%%", result.max_drawdown)
    logger.info("  Total P/L: $%.2f", result.total_profit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
