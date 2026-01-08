"""Claude Code CLI wrapper for Elliott Wave analysis."""

import csv
import json
import logging
import shutil
import subprocess
import tempfile
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
        self._db = None

    def set_database(self, db) -> None:
        """Set database reference for signal context retrieval.

        Args:
            db: Database instance
        """
        self._db = db

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

    def _build_prompt(
        self, csv_files: dict[str, Path], signal_context: Optional[dict] = None
    ) -> str:
        """Build analysis prompt with CSV data references and optional signal context.

        Args:
            csv_files: Dict mapping timeframe to CSV file path
            signal_context: Optional context from recent signals

        Returns:
            Prompt string for analysis
        """
        prompt_parts = [
            "## MANDATORY OUTPUT FORMAT",
            "",
            "You MUST respond with ONLY a JSON code block. NO OTHER TEXT.",
            "",
            "```json",
            '{"timestamp": "...", "symbol": "XAUUSD", "signal": {...}}',
            "```",
            "",
            "VIOLATIONS THAT CAUSE SYSTEM CRASH:",
            "- ANY text before the ```json block = CRASH",
            "- ANY markdown headers (##, ###) = CRASH",
            "- ANY tables (|---|) = CRASH",
            "- ANY prose or analysis = CRASH",
            "- ANY text after ```json block closes = CRASH",
            "",
            "---",
            "",
        ]

        # Add signal context if available
        if signal_context:
            prompt_parts.extend([
                "## PREVIOUS ANALYSIS CONTEXT",
                "",
                f"**Last Signal:** {signal_context['last_action']} "
                f"(confidence: {signal_context['last_confidence']}%) "
                f"at {signal_context['last_time']}",
                f"**Time Since Last:** {signal_context['minutes_since_last']} minutes",
                f"**Recent Sequence:** {signal_context['recent_sequence']}",
            ])

            if signal_context.get("wave_position"):
                prompt_parts.append(
                    f"**Last Wave Position:** {signal_context['wave_position']}"
                )

            prompt_parts.extend([
                "",
                "## DIRECTION CHANGE REQUIREMENTS",
                "",
                "If your analysis suggests a DIFFERENT direction from the last signal:",
                "",
                "1. **Explain Wave Count Change:** What price action invalidated previous count?",
                "2. **Identify Trigger:** What new development triggered this reassessment?",
                "3. **Confidence Threshold:** Direction changes require confidence >= 75%",
                "4. **Time Consideration:** Signals within 60 min of opposite need strong justification",
                "",
                "If market conditions similar to last analysis, maintain consistency unless clear evidence of change.",
                "",
                "---",
                "",
            ])

        prompt_parts.append("STEP 1: Read these CSV files using the Read tool:")

        for tf, path in sorted(csv_files.items()):
            # Provide full path for Read tool access
            prompt_parts.append(f"- {tf}: {path}")

        prompt_parts.extend([
            "",
            "STEP 2: Analyze the OHLCV data silently using Elliott Wave theory.",
            "",
            "STEP 3: Output ONLY ```json {...} ``` - nothing else.",
            "Your entire response = one JSON code block. Nothing else.",
        ])

        return "\n".join(prompt_parts)

    def _build_command(
        self, csv_files: dict[str, Path], settings_file: Optional[Path] = None
    ) -> list[str]:
        """Build Claude CLI command.

        Args:
            csv_files: Dict mapping timeframe to CSV file path
            settings_file: Optional path to settings JSON file with system prompt

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
        ]

        # Use settings file for system prompt (avoids Windows cmd line length limit)
        if settings_file and settings_file.exists():
            cmd.extend(["--settings", str(settings_file)])

        # Add CSV directory for tool access (--add-dir grants Read access)
        csv_dirs = set()
        for tf in ["H4", "H1", "M30", "M15"]:
            if tf in csv_files and csv_files[tf].exists():
                validated_csv = self._validate_path(csv_files[tf])
                csv_dirs.add(validated_csv.parent)

        for csv_dir in csv_dirs:
            cmd.extend(["--add-dir", str(csv_dir)])

        return cmd

    def _create_settings_file(self, system_prompt: str) -> Path:
        """Create temporary settings file with system prompt.

        This avoids Windows command line length limits by putting the
        system prompt in a file rather than passing it as an argument.

        Args:
            system_prompt: System prompt content

        Returns:
            Path to temporary settings file
        """
        # Create temp file that persists until explicitly deleted
        fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="claude_settings_")
        try:
            settings = {"systemPrompt": system_prompt}
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(settings, f)
            return Path(temp_path)
        except Exception:
            # Clean up on error
            Path(temp_path).unlink(missing_ok=True)
            raise

    def _run_cli(self, cmd: list[str], prompt: str) -> str:
        """Execute CLI command with timeout.

        Args:
            cmd: Command to execute
            prompt: User prompt to send via stdin (avoids cmd line length limit)

        Returns:
            CLI stdout output

        Raises:
            ClaudeTimeoutError: If command times out
            ClaudeClientError: If command fails
        """
        # Log command (without stdin content for brevity)
        cmd_display = " ".join(cmd)
        logger.info("[CLI] Executing Claude Code CLI...")
        logger.debug(f"[CLI] Command: {cmd_display}")
        logger.debug(f"[CLI] Prompt length: {len(prompt)} chars")

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                input=prompt,  # Send prompt via stdin (avoids cmd line length limit)
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
        self,
        csv_files: dict[str, Path],
        signal_context: Optional[dict] = None,
        attempt: int = 0,
    ) -> Optional[str]:
        """Execute CLI with exponential backoff retry.

        Args:
            csv_files: CSV files for analysis
            signal_context: Optional context from recent signals
            attempt: Current attempt number

        Returns:
            CLI output or None if all retries fail
        """
        prompt = self._build_prompt(csv_files, signal_context=signal_context)
        settings_file = None

        try:
            # Create settings file with system prompt (avoids Windows cmd line limit)
            if self.instructions_path.exists():
                validated_instructions = self._validate_path(self.instructions_path)
                with open(validated_instructions, "r", encoding="utf-8") as f:
                    system_prompt_content = f.read()
                settings_file = self._create_settings_file(system_prompt_content)
                logger.debug(f"[CLI] Created settings file: {settings_file}")

            cmd = self._build_command(csv_files, settings_file)
            return self._run_cli(cmd, prompt)

        except (ClaudeTimeoutError, ClaudeClientError) as e:
            if attempt < self.max_retries:
                delay = 2 ** attempt * 5  # 5s, 10s, 20s...
                logger.warning(f"Retry {attempt + 1}/{self.max_retries} after {delay}s: {e}")
                time.sleep(delay)
                return self._retry_with_backoff(csv_files, signal_context, attempt + 1)
            logger.error(f"All retries exhausted: {e}")
            return None

        finally:
            # Clean up temp settings file
            if settings_file and settings_file.exists():
                try:
                    settings_file.unlink()
                    logger.debug(f"[CLI] Cleaned up settings file: {settings_file}")
                except Exception as cleanup_err:
                    logger.warning(f"[CLI] Failed to clean up settings file: {cleanup_err}")

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

        # Get signal context from database if available
        signal_context = None
        if self._db:
            try:
                signal_context = self._db.get_signal_context(limit=3)
                if signal_context:
                    logger.info(
                        f"[ANALYSIS] Signal context: last={signal_context['last_action']}, "
                        f"seq={signal_context['recent_sequence']}, "
                        f"mins_ago={signal_context['minutes_since_last']}"
                    )
                else:
                    logger.debug("[ANALYSIS] No previous signals for context")
            except Exception as ctx_err:
                logger.warning(f"[ANALYSIS] Failed to get signal context: {ctx_err}")

        # Run analysis with retry
        response = self._retry_with_backoff(csv_files, signal_context=signal_context)
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
                    f"[SIGNAL] Wave: trend={wave.h4_trend}, "
                    f"position={wave.wave_position or wave.current_wave}"
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
                    "h4_trend": wave.h4_trend,
                    "current_wave": wave.current_wave,
                    "wave_position": wave.wave_position,
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
