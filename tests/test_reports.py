"""Tests for weekly report generator.

Tests:
- Weekly report generation
- Monthly report generation
- Report saving and loading
- Period comparison
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestWeeklyReportGenerator:
    """Test weekly report generation."""

    def test_generate_weekly_report_creates_file(self, tmp_path, temp_db, buy_signal):
        """Weekly report saves JSON file."""
        from src.reports import WeeklyReportGenerator

        # Add some test data
        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

            with patch("src.analytics.get_database", return_value=temp_db):
                report = reporter.generate_weekly_report()

        # Check file was created
        report_files = list(tmp_path.glob("weekly_report_*.json"))
        assert len(report_files) == 1

        # Check report structure
        assert "period" in report
        assert report["period"]["type"] == "weekly"
        assert "overall_metrics" in report
        assert "suggestions" in report

    def test_generate_monthly_report(self, tmp_path, temp_db, buy_signal):
        """Monthly report generation."""
        from src.reports import WeeklyReportGenerator

        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

            with patch("src.analytics.get_database", return_value=temp_db):
                report = reporter.generate_monthly_report()

        report_files = list(tmp_path.glob("monthly_report_*.json"))
        assert len(report_files) == 1
        assert report["period"]["type"] == "monthly"

    def test_generate_custom_report(self, tmp_path, temp_db, buy_signal):
        """Custom date range report."""
        from src.reports import WeeklyReportGenerator

        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

            with patch("src.analytics.get_database", return_value=temp_db):
                report = reporter.generate_custom_report(
                    start_date="2024-01-01",
                    end_date="2024-06-30",
                    report_name="q1_q2",
                )

        report_files = list(tmp_path.glob("q1_q2_report_*.json"))
        assert len(report_files) == 1
        assert report["period"]["type"] == "custom"
        assert report["period"]["start"] == "2024-01-01"
        assert report["period"]["end"] == "2024-06-30"


class TestReportStorage:
    """Test report storage and retrieval."""

    def test_get_recent_reports_lists_files(self, tmp_path):
        """get_recent_reports lists saved reports."""
        from src.reports import WeeklyReportGenerator

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

        # Create some test reports
        for i in range(5):
            report_data = {
                "generated_at": datetime.utcnow().isoformat(),
                "period": {"type": "weekly", "start": f"2024-0{i+1}-01"},
                "overall_metrics": {"total_trades": i * 10},
            }
            filepath = tmp_path / f"weekly_report_2024010{i}.json"
            with open(filepath, "w") as f:
                json.dump(report_data, f)

        reports = reporter.get_recent_reports(limit=3)

        assert len(reports) == 3
        assert all("filename" in r for r in reports)
        assert all("period" in r for r in reports)

    def test_get_recent_reports_handles_corrupted_file(self, tmp_path):
        """get_recent_reports skips corrupted files."""
        from src.reports import WeeklyReportGenerator

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

        # Create valid report
        valid_report = {
            "generated_at": datetime.utcnow().isoformat(),
            "period": {"type": "weekly"},
            "overall_metrics": {"total_trades": 10},
        }
        with open(tmp_path / "valid_report.json", "w") as f:
            json.dump(valid_report, f)

        # Create corrupted file
        with open(tmp_path / "corrupted.json", "w") as f:
            f.write("not valid json{")

        reports = reporter.get_recent_reports()

        # Should only return valid report
        assert len(reports) == 1
        assert "valid_report.json" in reports[0]["filename"]


class TestPeriodComparison:
    """Test period comparison functionality."""

    def test_compare_periods_returns_delta(self, tmp_path, temp_db, buy_signal):
        """Period comparison calculates deltas."""
        from src.reports import WeeklyReportGenerator

        signal_id = temp_db.save_signal(buy_signal)
        trade_id = temp_db.save_trade(
            signal_id=signal_id,
            ticket=1000,
            volume=0.1,
            signal=buy_signal,
        )
        temp_db.close_trade(trade_id, 3400.0, 100.0)

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=tmp_path)

            with patch("src.analytics.get_database", return_value=temp_db):
                comparison = reporter.compare_periods(
                    period1_start="2024-01-01",
                    period1_end="2024-01-31",
                    period2_start="2024-02-01",
                    period2_end="2024-02-28",
                )

        assert "period_1" in comparison
        assert "period_2" in comparison
        assert "delta" in comparison
        assert "win_rate" in comparison["delta"]
        assert "profit_factor" in comparison["delta"]


class TestOutputDirectory:
    """Test output directory handling."""

    def test_creates_output_directory_if_missing(self, tmp_path):
        """Output directory created if doesn't exist."""
        from src.reports import WeeklyReportGenerator

        output_dir = tmp_path / "nonexistent" / "reports"
        assert not output_dir.exists()

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator(output_dir=output_dir)

        assert output_dir.exists()

    def test_uses_default_output_directory(self, tmp_path):
        """Uses logs/reports by default."""
        from src.reports import WeeklyReportGenerator

        with patch("src.reports.get_settings") as mock_settings:
            mock_settings.return_value.logs_dir = tmp_path
            reporter = WeeklyReportGenerator()

        expected_dir = tmp_path / "reports"
        assert reporter.output_dir == expected_dir


class TestSingleton:
    """Test weekly reporter singleton."""

    def test_get_weekly_reporter_returns_same_instance(self):
        """get_weekly_reporter returns singleton."""
        import src.reports

        src.reports._weekly_reporter = None

        from src.reports import get_weekly_reporter

        reporter1 = get_weekly_reporter()
        reporter2 = get_weekly_reporter()

        assert reporter1 is reporter2
