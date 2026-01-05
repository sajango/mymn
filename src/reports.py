"""Weekly performance report generator.

Generates:
- JSON reports saved to logs/reports/
- Optimization suggestions based on metrics
- Period comparison for trend analysis
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.analytics import get_analytics_engine
from src.config import get_settings

logger = logging.getLogger(__name__)


class WeeklyReportGenerator:
    """Generate and save weekly performance reports."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize report generator.

        Args:
            output_dir: Directory for report files (default: logs/reports)
        """
        settings = get_settings()
        self.output_dir = output_dir or settings.logs_dir / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_weekly_report(self) -> dict:
        """Generate weekly report for the previous week.

        Returns:
            Complete weekly report dict
        """
        today = datetime.utcnow()
        # Calculate last week's date range (Monday-Sunday)
        week_start = today - timedelta(days=today.weekday() + 7)
        week_end = week_start + timedelta(days=6)

        start_date = week_start.strftime("%Y-%m-%d")
        end_date = week_end.strftime("%Y-%m-%d")

        logger.info(f"Generating weekly report: {start_date} to {end_date}")

        # Get analytics
        engine = get_analytics_engine()
        report = engine.generate_full_report(start_date, end_date)

        # Add period info
        report["period"] = {
            "type": "weekly",
            "start": start_date,
            "end": end_date,
            "week_number": week_start.isocalendar()[1],
        }

        # Add optimization suggestions
        report["suggestions"] = engine.get_optimization_suggestions()

        # Save report
        filename = f"weekly_report_{week_start.strftime('%Y%m%d')}.json"
        filepath = self.output_dir / filename
        self._save_report(report, filepath)

        logger.info(f"Weekly report saved: {filepath}")
        return report

    def generate_monthly_report(self) -> dict:
        """Generate monthly report for the previous month.

        Returns:
            Complete monthly report dict
        """
        today = datetime.utcnow()
        # First day of current month
        first_of_month = today.replace(day=1)
        # Last day of previous month
        month_end = first_of_month - timedelta(days=1)
        # First day of previous month
        month_start = month_end.replace(day=1)

        start_date = month_start.strftime("%Y-%m-%d")
        end_date = month_end.strftime("%Y-%m-%d")

        logger.info(f"Generating monthly report: {start_date} to {end_date}")

        engine = get_analytics_engine()
        report = engine.generate_full_report(start_date, end_date)

        report["period"] = {
            "type": "monthly",
            "start": start_date,
            "end": end_date,
            "month": month_start.strftime("%B %Y"),
        }

        report["suggestions"] = engine.get_optimization_suggestions()

        filename = f"monthly_report_{month_start.strftime('%Y%m')}.json"
        filepath = self.output_dir / filename
        self._save_report(report, filepath)

        logger.info(f"Monthly report saved: {filepath}")
        return report

    def generate_custom_report(
        self, start_date: str, end_date: str, report_name: str = "custom"
    ) -> dict:
        """Generate custom date range report.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            report_name: Name prefix for saved file

        Returns:
            Complete report dict
        """
        logger.info(f"Generating custom report: {start_date} to {end_date}")

        engine = get_analytics_engine()
        report = engine.generate_full_report(start_date, end_date)

        report["period"] = {
            "type": "custom",
            "start": start_date,
            "end": end_date,
        }

        report["suggestions"] = engine.get_optimization_suggestions()

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_name}_report_{timestamp}.json"
        filepath = self.output_dir / filename
        self._save_report(report, filepath)

        logger.info(f"Custom report saved: {filepath}")
        return report

    def _save_report(self, report: dict, filepath: Path):
        """Save report to JSON file.

        Args:
            report: Report dict to save
            filepath: Destination path
        """
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)

    def get_recent_reports(self, limit: int = 10) -> list[dict]:
        """Get list of recent reports.

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of report metadata dicts
        """
        reports = []
        for filepath in sorted(
            self.output_dir.glob("*.json"), reverse=True
        )[:limit]:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                reports.append(
                    {
                        "filename": filepath.name,
                        "generated_at": data.get("generated_at"),
                        "period": data.get("period", {}),
                        "total_trades": data.get("overall_metrics", {}).get(
                            "total_trades", 0
                        ),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                logger.warning(f"Could not read report: {filepath}")
                continue

        return reports

    def compare_periods(
        self, period1_start: str, period1_end: str, period2_start: str, period2_end: str
    ) -> dict:
        """Compare two time periods.

        Args:
            period1_start: First period start (YYYY-MM-DD)
            period1_end: First period end (YYYY-MM-DD)
            period2_start: Second period start (YYYY-MM-DD)
            period2_end: Second period end (YYYY-MM-DD)

        Returns:
            Comparison dict with both periods and deltas
        """
        engine = get_analytics_engine()

        metrics1 = engine.calculate_overall_metrics(period1_start, period1_end)
        metrics2 = engine.calculate_overall_metrics(period2_start, period2_end)

        return {
            "period_1": {
                "start": period1_start,
                "end": period1_end,
                "metrics": {
                    "win_rate": metrics1.win_rate,
                    "profit_factor": metrics1.profit_factor,
                    "total_trades": metrics1.total_trades,
                    "sharpe_ratio": metrics1.sharpe_ratio,
                },
            },
            "period_2": {
                "start": period2_start,
                "end": period2_end,
                "metrics": {
                    "win_rate": metrics2.win_rate,
                    "profit_factor": metrics2.profit_factor,
                    "total_trades": metrics2.total_trades,
                    "sharpe_ratio": metrics2.sharpe_ratio,
                },
            },
            "delta": {
                "win_rate": round(metrics2.win_rate - metrics1.win_rate, 1),
                "profit_factor": round(
                    metrics2.profit_factor - metrics1.profit_factor, 2
                ),
                "total_trades": metrics2.total_trades - metrics1.total_trades,
                "sharpe_ratio": round(
                    metrics2.sharpe_ratio - metrics1.sharpe_ratio, 2
                ),
            },
        }


# Lazy singleton
_weekly_reporter: Optional[WeeklyReportGenerator] = None


def get_weekly_reporter() -> WeeklyReportGenerator:
    """Get or create weekly reporter singleton."""
    global _weekly_reporter
    if _weekly_reporter is None:
        _weekly_reporter = WeeklyReportGenerator()
    return _weekly_reporter
