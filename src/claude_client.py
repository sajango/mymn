"""Claude Code CLI wrapper for Elliott Wave analysis."""

import csv
import json
import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.signal_parser import (
    TradingSignal,
    create_no_trade_signal,
    parse_trading_signal,
)

logger = logging.getLogger(__name__)


def _log_csv_file_info(tf: str, path: Path) -> dict:
    """Log detailed CSV file information.

    Args:
        tf: Timeframe label (H4, H1, M30, M15)
        path: Path to CSV file

    Returns:
        Dict with file metadata
    """
    info = {
        "timeframe": tf,
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": 0,
        "row_count": 0,
        "columns": [],
        "date_range": None,
    }

    if not path.exists():
        logger.warning(f"[CSV:{tf}] File not found: {path}")
        return info

    info["size_bytes"] = path.stat().st_size
    size_kb = info["size_bytes"] / 1024

    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            info["columns"] = headers

            rows = list(reader)
            info["row_count"] = len(rows)

            # Extract date range from first column (typically datetime)
            if rows and len(rows[0]) > 0:
                first_date = rows[0][0] if rows else None
                last_date = rows[-1][0] if rows else None
                info["date_range"] = f"{first_date} -> {last_date}"

        logger.info(
            f"[CSV:{tf}] Loaded {path.name}: "
            f"{info['row_count']} rows, {size_kb:.1f}KB, "
            f"columns={len(headers)}, range={info['date_range']}"
        )
    except Exception as e:
        logger.error(f"[CSV:{tf}] Failed to read {path}: {e}")

    return info

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
        claude_path = shutil.which("claude")
        if not claude_path:
            logger.error("Claude CLI not found in PATH")
            return False

        try:
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",  # Explicit UTF-8 for Windows compatibility
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Claude CLI version: {result.stdout.strip()}")
                return True
            logger.error(f"Claude CLI check failed: {result.stderr}")
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
            FileNotFoundError: If Claude CLI is not found in PATH
        """
        # Use shutil.which to find full path (required on Windows)
        claude_path = shutil.which("claude")
        if not claude_path:
            raise FileNotFoundError("Claude CLI not found in PATH")

        cmd = [
            claude_path,
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
        # Log full command (mask sensitive parts if any)
        cmd_display = " ".join(cmd)
        logger.info(f"[CLI] Executing Claude Code CLI...")
        logger.debug(f"[CLI] Full command: {cmd_display}")

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",  # Explicit UTF-8 for Windows compatibility
                timeout=self.timeout,
            )

            elapsed = time.time() - start_time
            response_len = len(result.stdout) if result.stdout else 0

            if result.returncode != 0:
                logger.error(
                    f"[CLI] Error (code={result.returncode}, elapsed={elapsed:.1f}s): "
                    f"{result.stderr[:500]}"
                )
                raise ClaudeClientError(f"CLI failed: {result.stderr[:200]}")

            logger.info(
                f"[CLI] Success: returncode=0, elapsed={elapsed:.1f}s, "
                f"response_length={response_len} chars"
            )

            # Log response preview (first 500 chars for debugging)
            if result.stdout:
                preview = result.stdout[:500].replace("\n", " ")
                logger.debug(f"[CLI] Response preview: {preview}...")

            return result.stdout

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            logger.error(f"[CLI] Timeout after {elapsed:.1f}s (limit={self.timeout}s)")
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
        analysis_start = time.time()
        logger.info("=" * 60)
        logger.info("[ANALYSIS] Starting Elliott Wave analysis...")
        logger.info(f"[ANALYSIS] Timestamp: {datetime.utcnow().isoformat()}Z")

        # Validate inputs
        if not csv_files:
            logger.error("[ANALYSIS] No CSV files provided")
            return create_no_trade_signal("no_data", "No CSV files provided")

        # Log CSV file details
        logger.info(f"[ANALYSIS] Processing {len(csv_files)} CSV files...")
        csv_metadata = {}
        total_rows = 0
        total_size = 0

        for tf in ["H4", "H1", "M30", "M15"]:
            if tf in csv_files:
                info = _log_csv_file_info(tf, csv_files[tf])
                csv_metadata[tf] = info
                total_rows += info["row_count"]
                total_size += info["size_bytes"]

        logger.info(
            f"[ANALYSIS] Total data: {total_rows} rows, "
            f"{total_size / 1024:.1f}KB across {len(csv_files)} files"
        )

        missing = [tf for tf in ["H4", "H1", "M30", "M15"] if tf not in csv_files]
        if missing:
            logger.warning(f"[ANALYSIS] Missing timeframes: {missing}")

        for tf, path in csv_files.items():
            if not path.exists():
                logger.error(f"[ANALYSIS] CSV file not found: {path}")
                return create_no_trade_signal("file_not_found", f"Missing: {path}")

        # Check instructions file
        if not self.instructions_path.exists():
            logger.error(f"[ANALYSIS] Instructions not found: {self.instructions_path}")
            return create_no_trade_signal(
                "config_error", f"Instructions missing: {self.instructions_path}"
            )

        logger.info(f"[ANALYSIS] Instructions: {self.instructions_path}")

        # Run analysis with retry
        response = self._retry_with_backoff(csv_files)
        if response is None:
            logger.error("[ANALYSIS] Claude CLI failed after all retries")
            return create_no_trade_signal(
                "cli_failed", "Claude CLI failed after retries"
            )

        # Parse response with enhanced logging for debugging
        logger.info("[ANALYSIS] Parsing Claude response...")
        logger.debug(f"[ANALYSIS] Response: {len(response)} chars, "
                     f"has_json_block={'```json' in response}, "
                     f"has_braces={'{' in response}")
        logger.debug(f"[ANALYSIS] Preview: {response[:500].replace(chr(10), ' ')}")

        signal = parse_trading_signal(response)

        if signal is None:
            logger.error("[ANALYSIS] Failed to parse signal from response")
            logger.warning(f"[ANALYSIS] Raw response (first 1000 chars): {response[:1000]}")

            # Save failed response to disk for investigation
            self._save_failed_response(response)

            return create_no_trade_signal(
                "parse_failed", "Could not parse JSON from CLI response"
            )

        # Log parsed signal details
        elapsed = time.time() - analysis_start
        sig = signal.signal
        logger.info("[ANALYSIS] Successfully parsed trading signal!")
        logger.info(
            f"[SIGNAL] Action: {sig.action} | Confidence: {sig.confidence}% | "
            f"Symbol: {signal.symbol}"
        )

        if signal.is_tradeable:
            # Log entry and stop loss
            logger.info(
                f"[SIGNAL] Entry: {sig.entry_price} | SL: {sig.stop_loss}"
            )

            # Log take profit levels
            if sig.take_profit:
                tp_str = " | ".join(
                    f"{tp.level}={tp.price}" for tp in sig.take_profit
                )
                logger.info(f"[SIGNAL] Take Profits: {tp_str}")

            # Log risk:reward if available
            if sig.risk_reward:
                logger.info(f"[SIGNAL] Risk:Reward = {sig.risk_reward:.2f}")

            # Log wave analysis if available
            if signal.wave_analysis:
                wave = signal.wave_analysis
                logger.info(
                    f"[SIGNAL] Wave: degree={wave.primary_wave.degree}, "
                    f"position={wave.primary_wave.current_position}"
                )
        else:
            logger.info(f"[SIGNAL] No trade - Reason: {sig.reason}")

        logger.info(f"[ANALYSIS] Completed in {elapsed:.1f}s")
        logger.info("=" * 60)

        # Save analysis to file
        self._save_analysis(response, signal, csv_metadata, elapsed)

        return signal

    def _save_failed_response(self, response: str) -> Optional[Path]:
        """Save failed response to disk for investigation.

        Args:
            response: Raw Claude CLI response that failed to parse

        Returns:
            Path to saved file or None on error
        """
        failed_dir = Path(__file__).parent.parent / "data" / "failed_analyses"
        failed_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filepath = failed_dir / f"failed_{timestamp}.txt"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"=== FAILED RESPONSE ===\n")
                f.write(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")
                f.write(f"Response length: {len(response)} chars\n")
                f.write(f"Has ```json: {'```json' in response}\n")
                f.write(f"Has ```: {'```' in response}\n")
                f.write(f"Has {{: {'{' in response}\n")
                f.write(f"=== RAW RESPONSE ===\n")
                f.write(response)

            logger.info(f"[ANALYSIS] Failed response saved to: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"[ANALYSIS] Failed to save failed response: {e}")
            return None

    def _save_analysis(
        self,
        raw_response: str,
        signal: TradingSignal,
        csv_metadata: dict,
        elapsed_seconds: float,
    ) -> Optional[Path]:
        """Save analysis result to JSON file.

        Args:
            raw_response: Raw Claude CLI response
            signal: Parsed trading signal
            csv_metadata: Metadata about CSV files used
            elapsed_seconds: Analysis duration

        Returns:
            Path to saved file or None on error
        """
        output_dir = Path(__file__).parent.parent / "data" / "analyses"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filepath = output_dir / f"analysis_{timestamp}.json"

        try:
            # Build analysis record
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                "elapsed_seconds": round(elapsed_seconds, 2),
                "csv_files": {
                    tf: {
                        "path": info.get("path"),
                        "rows": info.get("row_count"),
                        "date_range": info.get("date_range"),
                    }
                    for tf, info in csv_metadata.items()
                },
                "raw_response": raw_response,
                "parsed_signal": {
                    "symbol": signal.symbol,
                    "is_tradeable": signal.is_tradeable,
                    "action": signal.signal.action,
                    "confidence": signal.signal.confidence,
                    "entry_price": signal.signal.entry_price,
                    "stop_loss": signal.signal.stop_loss,
                    "reason": signal.signal.reason,
                    "take_profit": [
                        {"level": tp.level, "price": tp.price}
                        for tp in (signal.signal.take_profit or [])
                    ],
                    "risk_reward": signal.signal.risk_reward,
                },
            }

            # Add wave analysis if available
            if signal.wave_analysis:
                wave = signal.wave_analysis
                record["wave_analysis"] = {
                    "degree": wave.primary_wave.degree,
                    "position": wave.primary_wave.current_position,
                    "direction": wave.primary_wave.direction,
                }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, default=str)

            logger.info(f"[ANALYSIS] Saved to: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"[ANALYSIS] Failed to save analysis: {e}")
            return None


# Singleton instance
claude_client = ClaudeClient()
