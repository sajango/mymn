"""Claude Code CLI wrapper for Elliott Wave analysis."""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.signal_parser import (
    TradingSignal,
    create_no_trade_signal,
    parse_trading_signal,
)

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_INSTRUCTIONS_PATH = Path(__file__).parent.parent / "instructions_v2.md"


class ClaudeClientError(Exception):
    """Base exception for Claude client errors."""

    pass


class ClaudeTimeoutError(ClaudeClientError):
    """Raised when Claude CLI times out."""

    pass


class ClaudeParseError(ClaudeClientError):
    """Raised when response parsing fails."""

    pass


class ClaudeClient:
    """Client for Claude Code CLI operations."""

    def __init__(
        self,
        instructions_path: Optional[Path] = None,
        timeout: Optional[int] = None,
        max_retries: int = 1,
    ):
        """Initialize Claude client.

        Args:
            instructions_path: Path to instructions markdown file
            timeout: CLI timeout in seconds (default from config)
            max_retries: Max retry attempts on failure
        """
        self._config = None
        self._instructions_path = instructions_path
        self._timeout = timeout
        self.max_retries = max_retries

    def _validate_path(self, path: Path) -> Path:
        """Validate and sanitize file path for security.

        Args:
            path: File path to validate

        Returns:
            Resolved absolute path

        Raises:
            ValueError: If path is suspicious or outside allowed directories
        """
        # Resolve to absolute path
        abs_path = path.resolve()

        # Check for path traversal attempts
        path_str = str(path)
        if ".." in path_str or path_str.startswith("/") or ";" in path_str:
            raise ValueError(f"Invalid path: {path}")

        # Only allow files with safe extensions
        allowed_extensions = {".csv", ".md", ".txt"}
        if abs_path.suffix.lower() not in allowed_extensions:
            raise ValueError(f"Invalid file type: {abs_path.suffix}")

        return abs_path

    @property
    def config(self):
        """Lazy load config."""
        if self._config is None:
            self._config = get_settings()
        return self._config

    @property
    def instructions_path(self) -> Path:
        """Get instructions file path."""
        if self._instructions_path:
            return self._instructions_path
        return DEFAULT_INSTRUCTIONS_PATH

    @property
    def timeout(self) -> int:
        """Get CLI timeout in seconds."""
        if self._timeout:
            return self._timeout
        return self.config.claude_timeout

    def verify_cli_installed(self) -> bool:
        """Check if Claude CLI is installed and accessible.

        Returns:
            True if CLI is available
        """
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Claude CLI version: {result.stdout.strip()}")
                return True
            logger.error(f"Claude CLI check failed: {result.stderr}")
            return False
        except FileNotFoundError:
            logger.error("Claude CLI not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI version check timed out")
            return False
        except Exception as e:
            logger.error(f"Claude CLI check error: {e}")
            return False

    def _build_prompt(self, csv_files: dict[str, Path]) -> str:
        """Build analysis prompt with CSV data references.

        Args:
            csv_files: Dict mapping timeframe to CSV file path

        Returns:
            Prompt string for analysis
        """
        prompt_parts = [
            "Analyze the attached XAUUSD price data and generate a trading signal.",
            "",
            "Data files provided:",
        ]

        for tf, path in sorted(csv_files.items()):
            prompt_parts.append(f"- {tf}: {path.name}")

        prompt_parts.extend([
            "",
            "Follow the instructions in the system prompt exactly.",
            "Output ONLY the JSON signal - no explanations or markdown outside the JSON.",
            "Wrap the JSON in ```json code blocks.",
        ])

        return "\n".join(prompt_parts)

    def _build_command(self, prompt: str, csv_files: dict[str, Path]) -> list[str]:
        """Build Claude CLI command.

        Args:
            prompt: Analysis prompt
            csv_files: Dict mapping timeframe to CSV file path

        Returns:
            Command list for subprocess

        Raises:
            ValueError: If any file path is invalid or suspicious
        """
        cmd = [
            "claude",
            "--print",  # Non-interactive, output only
            "--dangerously-skip-permissions",  # Skip permission prompts (needed for automation)
            "-p", prompt,
        ]

        # Add instructions as system prompt (validate path first)
        if self.instructions_path.exists():
            validated_instructions = self._validate_path(self.instructions_path)
            cmd.extend(["--system-prompt", str(validated_instructions)])

        # Add CSV files as context (validate each path)
        for tf in ["H4", "H1", "M30", "M15"]:
            if tf in csv_files and csv_files[tf].exists():
                validated_csv = self._validate_path(csv_files[tf])
                cmd.extend(["--add-file", str(validated_csv)])

        return cmd

    def _run_cli(self, cmd: list[str]) -> str:
        """Execute CLI command with timeout.

        Args:
            cmd: Command to execute

        Returns:
            CLI stdout output

        Raises:
            ClaudeTimeoutError: If command times out
            ClaudeClientError: If command fails
        """
        logger.debug(f"Running: {' '.join(cmd[:5])}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                logger.error(f"CLI error (code {result.returncode}): {result.stderr}")
                raise ClaudeClientError(f"CLI failed: {result.stderr[:200]}")

            return result.stdout

        except subprocess.TimeoutExpired:
            logger.error(f"CLI timed out after {self.timeout}s")
            raise ClaudeTimeoutError(f"CLI timed out after {self.timeout}s")

    def _retry_with_backoff(
        self, csv_files: dict[str, Path], attempt: int = 0
    ) -> Optional[str]:
        """Execute CLI with exponential backoff retry.

        Args:
            csv_files: CSV files for analysis
            attempt: Current attempt number

        Returns:
            CLI output or None if all retries fail
        """
        prompt = self._build_prompt(csv_files)
        cmd = self._build_command(prompt, csv_files)

        try:
            return self._run_cli(cmd)
        except (ClaudeTimeoutError, ClaudeClientError) as e:
            if attempt < self.max_retries:
                delay = 2 ** attempt * 5  # 5s, 10s, 20s...
                logger.warning(f"Retry {attempt + 1}/{self.max_retries} after {delay}s: {e}")
                time.sleep(delay)
                return self._retry_with_backoff(csv_files, attempt + 1)
            logger.error(f"All retries exhausted: {e}")
            return None

    def analyze(self, csv_files: dict[str, Path]) -> TradingSignal:
        """Run Elliott Wave analysis on CSV data.

        Args:
            csv_files: Dict mapping timeframe (H4, H1, M30, M15) to CSV path

        Returns:
            TradingSignal with analysis results or NO_TRADE on failure
        """
        # Validate inputs
        if not csv_files:
            logger.error("No CSV files provided")
            return create_no_trade_signal("no_data", "No CSV files provided")

        missing = [tf for tf in ["H4", "H1", "M30", "M15"] if tf not in csv_files]
        if missing:
            logger.warning(f"Missing timeframes: {missing}")

        for tf, path in csv_files.items():
            if not path.exists():
                logger.error(f"CSV file not found: {path}")
                return create_no_trade_signal("file_not_found", f"Missing: {path}")

        # Check instructions file
        if not self.instructions_path.exists():
            logger.error(f"Instructions not found: {self.instructions_path}")
            return create_no_trade_signal(
                "config_error", f"Instructions missing: {self.instructions_path}"
            )

        # Run analysis with retry
        response = self._retry_with_backoff(csv_files)
        if response is None:
            return create_no_trade_signal(
                "cli_failed", "Claude CLI failed after retries"
            )

        # Parse response
        signal = parse_trading_signal(response)
        if signal is None:
            logger.error("Failed to parse signal from response")
            # Note: Not logging response content to protect strategy details
            return create_no_trade_signal(
                "parse_failed", "Could not parse JSON from CLI response"
            )

        return signal


# Singleton instance
claude_client = ClaudeClient()
