"""Test Claude client module."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set required env vars before importing config-dependent modules
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.claude_client import (
    ClaudeClient,
    ClaudeClientError,
    ClaudeParseError,
    ClaudeTimeoutError,
)
from src.signal_parser import SignalAction


class TestClaudeClientInitialization:
    """Test ClaudeClient initialization."""

    def test_default_initialization(self) -> None:
        """Test client initializes with defaults."""
        client = ClaudeClient()
        assert client.max_retries == 1
        assert client._instructions_path is None
        assert client._timeout is None

    def test_custom_initialization(self, tmp_path: Path) -> None:
        """Test client initializes with custom values."""
        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")

        client = ClaudeClient(
            instructions_path=instructions,
            timeout=120,
            max_retries=3,
        )
        assert client.instructions_path == instructions
        assert client.timeout == 120
        assert client.max_retries == 3


class TestVerifyCliInstalled:
    """Test CLI installation verification."""

    @patch("src.claude_client.subprocess.run")
    def test_cli_installed(self, mock_run: MagicMock) -> None:
        """Test returns True when CLI is installed."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="claude version 1.0.0",
        )

        client = ClaudeClient()
        assert client.verify_cli_installed() is True
        mock_run.assert_called_once()

    @patch("src.claude_client.subprocess.run")
    def test_cli_not_installed(self, mock_run: MagicMock) -> None:
        """Test returns False when CLI not found."""
        mock_run.side_effect = FileNotFoundError()

        client = ClaudeClient()
        assert client.verify_cli_installed() is False

    @patch("src.claude_client.subprocess.run")
    def test_cli_check_fails(self, mock_run: MagicMock) -> None:
        """Test returns False when CLI returns error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="error",
        )

        client = ClaudeClient()
        assert client.verify_cli_installed() is False


class TestBuildPrompt:
    """Test prompt building."""

    def test_builds_prompt_with_files(self, tmp_path: Path) -> None:
        """Test builds prompt listing CSV files."""
        csv_files = {
            "H4": tmp_path / "xauusd_h4.csv",
            "H1": tmp_path / "xauusd_h1.csv",
        }

        client = ClaudeClient()
        prompt = client._build_prompt(csv_files)

        assert "XAUUSD" in prompt
        assert "H4" in prompt
        assert "H1" in prompt
        assert "JSON" in prompt


class TestBuildCommand:
    """Test CLI command building."""

    def test_builds_command_with_files(self, tmp_path: Path) -> None:
        """Test builds proper CLI command."""
        # Create test files
        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        client = ClaudeClient(instructions_path=instructions)
        csv_files = {"H4": h4_csv}
        prompt = "test prompt"

        cmd = client._build_command(prompt, csv_files)

        assert "claude" in cmd
        assert "--print" in cmd
        assert "-p" in cmd
        assert prompt in cmd
        assert "--system-prompt" in cmd
        assert "--add-file" in cmd

    def test_skips_missing_timeframes(self, tmp_path: Path) -> None:
        """Test skips non-existent CSV files."""
        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        client = ClaudeClient(instructions_path=instructions)
        # Only H4 exists, H1/M30/M15 don't
        csv_files = {
            "H4": h4_csv,
            "H1": tmp_path / "nonexistent.csv",
        }

        cmd = client._build_command("test", csv_files)

        # Should only have one --add-file (for H4)
        add_file_count = cmd.count("--add-file")
        assert add_file_count == 1


class TestRunCli:
    """Test CLI execution."""

    @patch("src.claude_client.subprocess.run")
    def test_successful_run(self, mock_run: MagicMock) -> None:
        """Test successful CLI execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"signal": {"action": "BUY"}}',
        )

        client = ClaudeClient()
        result = client._run_cli(["claude", "--print"])

        assert "BUY" in result

    @patch("src.claude_client.subprocess.run")
    def test_timeout_raises_error(self, mock_run: MagicMock) -> None:
        """Test timeout raises ClaudeTimeoutError."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)

        client = ClaudeClient(timeout=300)
        with pytest.raises(ClaudeTimeoutError):
            client._run_cli(["claude", "--print"])

    @patch("src.claude_client.subprocess.run")
    def test_nonzero_exit_raises_error(self, mock_run: MagicMock) -> None:
        """Test non-zero exit code raises ClaudeClientError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="CLI error",
        )

        client = ClaudeClient()
        with pytest.raises(ClaudeClientError):
            client._run_cli(["claude", "--print"])


class TestRetryWithBackoff:
    """Test retry logic with exponential backoff."""

    @patch("src.claude_client.time.sleep")
    @patch("src.claude_client.subprocess.run")
    def test_retries_on_failure(
        self, mock_run: MagicMock, mock_sleep: MagicMock, tmp_path: Path
    ) -> None:
        """Test retries with backoff on failure."""
        # Fail first, succeed second
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="error"),
            MagicMock(returncode=0, stdout='{"test": true}'),
        ]

        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")

        client = ClaudeClient(instructions_path=instructions, max_retries=1)
        csv_files = {"H4": tmp_path / "h4.csv"}
        (tmp_path / "h4.csv").write_text("data")

        result = client._retry_with_backoff(csv_files)

        assert result is not None
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once()

    @patch("src.claude_client.subprocess.run")
    def test_returns_none_after_all_retries(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Test returns None when all retries exhausted."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")

        client = ClaudeClient(instructions_path=instructions, max_retries=0)
        csv_files = {"H4": tmp_path / "h4.csv"}
        (tmp_path / "h4.csv").write_text("data")

        result = client._retry_with_backoff(csv_files)
        assert result is None


class TestAnalyze:
    """Test analyze method."""

    def test_returns_no_trade_for_empty_files(self) -> None:
        """Test returns NO_TRADE when no CSV files provided."""
        client = ClaudeClient()
        signal = client.analyze({})

        assert signal.signal.action == SignalAction.NO_TRADE
        assert "no_data" in signal.signal.reason

    def test_returns_no_trade_for_missing_files(self, tmp_path: Path) -> None:
        """Test returns NO_TRADE when files don't exist."""
        client = ClaudeClient()
        csv_files = {"H4": tmp_path / "nonexistent.csv"}
        signal = client.analyze(csv_files)

        assert signal.signal.action == SignalAction.NO_TRADE
        assert "file_not_found" in signal.signal.reason

    def test_returns_no_trade_for_missing_instructions(self, tmp_path: Path) -> None:
        """Test returns NO_TRADE when instructions missing."""
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        client = ClaudeClient(instructions_path=tmp_path / "nonexistent.md")
        signal = client.analyze({"H4": h4_csv})

        assert signal.signal.action == SignalAction.NO_TRADE
        assert "config_error" in signal.signal.reason

    @patch("src.claude_client.subprocess.run")
    def test_successful_analysis(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Test successful analysis returns valid signal."""
        valid_response = '''```json
        {
            "timestamp": "2024-08-21T14:30:00Z",
            "symbol": "XAUUSD",
            "signal": {
                "action": "BUY",
                "entry_price": 3340.00,
                "stop_loss": 3310.00,
                "confidence": 78
            }
        }
        ```'''
        mock_run.return_value = MagicMock(returncode=0, stdout=valid_response)

        # Create test files
        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        client = ClaudeClient(instructions_path=instructions)
        signal = client.analyze({"H4": h4_csv})

        assert signal.signal.action == SignalAction.BUY
        assert signal.signal.confidence == 78

    @patch("src.claude_client.subprocess.run")
    def test_returns_no_trade_on_parse_failure(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Test returns NO_TRADE when response can't be parsed."""
        mock_run.return_value = MagicMock(returncode=0, stdout="not valid json")

        instructions = tmp_path / "instructions.md"
        instructions.write_text("test")
        h4_csv = tmp_path / "xauusd_h4.csv"
        h4_csv.write_text("data")

        client = ClaudeClient(instructions_path=instructions)
        signal = client.analyze({"H4": h4_csv})

        assert signal.signal.action == SignalAction.NO_TRADE
        assert "parse_failed" in signal.signal.reason


class TestPathValidation:
    """Test path validation for security."""

    def test_validates_csv_extension(self, tmp_path: Path) -> None:
        """Test accepts valid CSV files."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("test")

        client = ClaudeClient()
        result = client._validate_path(csv_file)
        assert result == csv_file.resolve()

    def test_validates_md_extension(self, tmp_path: Path) -> None:
        """Test accepts valid markdown files."""
        md_file = tmp_path / "instructions.md"
        md_file.write_text("test")

        client = ClaudeClient()
        result = client._validate_path(md_file)
        assert result == md_file.resolve()

    def test_rejects_suspicious_extensions(self, tmp_path: Path) -> None:
        """Test rejects non-allowed extensions."""
        exe_file = tmp_path / "malicious.exe"
        exe_file.write_text("test")

        client = ClaudeClient()
        with pytest.raises(ValueError, match="Invalid file type"):
            client._validate_path(exe_file)

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        """Test rejects path traversal attempts."""
        client = ClaudeClient()
        malicious_path = tmp_path / ".." / "etc" / "passwd.csv"

        with pytest.raises(ValueError, match="Invalid path"):
            client._validate_path(malicious_path)

    def test_rejects_command_injection(self, tmp_path: Path) -> None:
        """Test rejects command injection attempts."""
        client = ClaudeClient()
        malicious_path = tmp_path / "data;rm -rf /.csv"

        with pytest.raises(ValueError, match="Invalid path"):
            client._validate_path(malicious_path)


class TestSingletonInstance:
    """Test singleton instance."""

    def test_singleton_exists(self) -> None:
        """Test claude_client singleton is created."""
        from src.claude_client import claude_client

        assert claude_client is not None
        assert isinstance(claude_client, ClaudeClient)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
