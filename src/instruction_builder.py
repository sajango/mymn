"""Dynamic instruction assembly for Claude trading signals.

Assembles modular instruction sets based on market conditions, reducing token usage
from ~34K (monolithic) to ~12-15K (assembled). Supports regime-aware module selection
and performance context injection.
"""

import logging
from pathlib import Path
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"  # src/instructions/
DEFAULT_TOKEN_BUDGET = 15000


class InstructionBuilder:
    """Assemble instruction set dynamically based on market conditions."""

    def __init__(self, token_budget: Optional[int] = None):
        """Initialize InstructionBuilder.

        Args:
            token_budget: Maximum token budget for assembled instructions.
                         If None, uses config value or DEFAULT_TOKEN_BUDGET.
        """
        self.instructions_dir = INSTRUCTIONS_DIR
        self._cache = {}

        # Load token budget from config or use default
        if token_budget is not None:
            self.token_budget = token_budget
        else:
            try:
                from src.config import get_settings
                self.token_budget = get_settings().instruction_token_budget
            except Exception:
                self.token_budget = DEFAULT_TOKEN_BUDGET

    @lru_cache(maxsize=32)
    def _load_module(self, relative_path: str) -> str:
        """Load and cache instruction module.

        Args:
            relative_path: Path relative to instructions directory

        Returns:
            Module content or empty string if not found
        """
        path = self.instructions_dir / relative_path
        if not path.exists():
            logger.warning(f"Instruction module not found: {path}")
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def build(
        self,
        market_regime: Optional[dict] = None,
        signal_context: Optional[dict] = None,
        volatility_state: Optional[dict] = None,
    ) -> str:
        """Build complete instruction set.

        Args:
            market_regime: Current market regime info (adx, regime_type)
            signal_context: Recent signal context (looking_for, wave_ambiguity, performance)
            volatility_state: Current volatility state (atr_percentile)

        Returns:
            Assembled instruction string (~12-15K tokens)
        """
        parts = []

        # 1. Core rules (always included)
        parts.append(self._load_module("core/essential-rules.md"))
        parts.append(self._load_module("core/confidence-scoring.md"))

        # 2. Regime-specific module (pick ONE based on conditions)
        regime_module = self._select_regime_module(market_regime, volatility_state)
        parts.append(self._load_module(regime_module))

        # 3. Wave pattern modules (context-dependent)
        wave_modules = self._select_wave_modules(signal_context)
        for module in wave_modules:
            parts.append(self._load_module(module))

        # 4. Indicator confluence (if module exists)
        confluence = self._load_module("indicators/confluence.md")
        if confluence:
            parts.append(confluence)

        # 5. Performance context (dynamic injection)
        perf_context = self._build_performance_context(signal_context)
        if perf_context:
            parts.append(perf_context)

        # 6. Output format (always last)
        parts.append(self._load_module("core/output-format.md"))

        # Join with clear section separators
        assembled = "\n\n---\n\n".join(filter(None, parts))

        # Token count validation and metrics logging
        token_estimate = self.estimate_tokens(assembled)
        logger.info(
            f"[INSTRUCTIONS] Assembled ~{token_estimate} tokens | "
            f"Budget: {self.token_budget} | "
            f"Regime: {regime_module.split('/')[-1].replace('.md', '')}"
        )

        if token_estimate > self.token_budget:
            logger.warning(
                f"[INSTRUCTIONS] Token count ({token_estimate}) exceeds {self.token_budget} budget!"
            )
        elif token_estimate > self.token_budget * 0.8:
            logger.info(f"[INSTRUCTIONS] Token count within target range (80-100% of budget)")

        return assembled

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count using character-based approximation.

        Uses chars/4 approximation which is reasonably accurate for English text.
        For more precise counting, consider using tiktoken library.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def _select_regime_module(
        self,
        market_regime: Optional[dict],
        volatility_state: Optional[dict],
    ) -> str:
        """Select appropriate regime module based on market conditions.

        Args:
            market_regime: Dict with adx, regime_type fields
            volatility_state: Dict with atr_percentile field

        Returns:
            Relative path to regime module
        """
        if not market_regime:
            logger.warning("[INSTRUCTIONS] No market_regime data, using default trending-strong")
            return "regime/trending-strong.md"  # Default

        # Check volatility first (overrides trend)
        if volatility_state:
            atr_percentile = volatility_state.get("atr_percentile", 50)
            if atr_percentile > 80:
                return "regime/volatile.md"

        # Extract regime data
        adx = market_regime.get("adx", 25)
        regime_type = market_regime.get("regime_type", "").lower()

        # Priority 1: Check explicit regime_type first (more specific than ADX)
        if "ranging" in regime_type:
            return "regime/ranging.md"
        if "strong" in regime_type:
            return "regime/trending-strong.md"
        if "weak" in regime_type:
            return "regime/trending-weak.md"

        # Priority 2: ADX-based selection when no explicit regime_type
        if adx >= 25:
            return "regime/trending-strong.md"
        elif adx >= 15:
            return "regime/trending-weak.md"
        else:  # adx < 15
            return "regime/ranging.md"

    def _select_wave_modules(self, signal_context: Optional[dict]) -> list:
        """Select relevant wave pattern modules based on context.

        Args:
            signal_context: Dict with looking_for, wave_ambiguity fields

        Returns:
            List of relative paths to wave pattern modules
        """
        if not signal_context:
            # Default: entry patterns
            return ["wave-patterns/wave-2-entry.md", "wave-patterns/wave-4-entry.md"]

        modules = []
        looking_for = signal_context.get("looking_for", "entry")

        if looking_for == "entry":
            modules.append("wave-patterns/wave-2-entry.md")
            modules.append("wave-patterns/wave-4-entry.md")
        elif looking_for == "exit":
            modules.append("wave-patterns/wave-5-exit.md")

        # Add complex corrections if recent ambiguity
        if signal_context.get("wave_ambiguity", 0) > 30:
            modules.append("wave-patterns/complex-corrections.md")

        return modules

    def _build_performance_context(self, signal_context: Optional[dict]) -> str:
        """Build performance context with historical data.

        Args:
            signal_context: Dict with performance statistics

        Returns:
            Populated template string or empty string
        """
        if not signal_context:
            return ""

        template = self._load_module("context/performance-template.md")
        if not template:
            return ""

        # Replace placeholders with actual data
        replacements = {
            "{{WIN_RATE}}": str(signal_context.get("overall_win_rate", "N/A")),
            "{{WIN_RATE_COMMENT}}": self._win_rate_comment(
                signal_context.get("overall_win_rate")
            ),
            "{{BEST_WAVE}}": signal_context.get("best_wave_position", "N/A"),
            "{{WORST_WAVE}}": signal_context.get("worst_wave_position", "N/A"),
            "{{BEST_SESSION}}": signal_context.get("best_session", "N/A"),
            "{{WORST_SESSION}}": signal_context.get("worst_session", "N/A"),
            "{{CALIBRATED_MIN}}": str(
                signal_context.get("calibrated_min_confidence", 60)
            ),
            "{{STREAK_WARNING}}": self._streak_warning(signal_context),
        }

        # Confidence bucket win rates
        conf_perf = signal_context.get("confidence_performance", {})
        for bucket in ["80", "70", "60", "50"]:
            bucket_data = conf_perf.get(f"{bucket}+", {})
            replacements[f"{{{{WIN_RATE_{bucket}}}}}"] = str(
                bucket_data.get("win_rate", "N/A")
            )
            replacements[f"{{{{SAMPLE_{bucket}}}}}"] = str(
                bucket_data.get("total", 0)
            )

        for key, value in replacements.items():
            template = template.replace(key, value)

        # Validate no unreplaced placeholders remain
        if "{{" in template and "}}" in template:
            logger.warning("[INSTRUCTIONS] Some placeholders not replaced in performance template")

        return template

    def _win_rate_comment(self, win_rate: Optional[float]) -> str:
        """Generate comment based on win rate.

        Args:
            win_rate: Win rate percentage (0-100)

        Returns:
            Advisory comment string
        """
        if win_rate is None:
            return "Insufficient data"
        if win_rate >= 55:
            return "Good performance, maintain strategy"
        if win_rate >= 45:
            return "Marginal, increase selectivity"
        return "Poor, significantly increase confidence threshold"

    def _streak_warning(self, signal_context: dict) -> str:
        """Generate streak warning if applicable.

        Args:
            signal_context: Dict with current_streak field

        Returns:
            Warning message or neutral statement
        """
        streak = signal_context.get("current_streak", {})
        if streak.get("type") == "loss" and streak.get("count", 0) >= 2:
            count = streak["count"]
            return f"⚠️ WARNING: On a {count}-trade losing streak. Only signal HIGH confidence setups (75%+)."
        return "No streak warning."

    def clear_cache(self):
        """Clear the LRU cache for module loading."""
        self._load_module.cache_clear()
        logger.info("[INSTRUCTIONS] Module cache cleared")


# Singleton instance
_instruction_builder: Optional[InstructionBuilder] = None


def get_instruction_builder() -> InstructionBuilder:
    """Get or create InstructionBuilder singleton.

    Returns:
        InstructionBuilder singleton instance
    """
    global _instruction_builder
    if _instruction_builder is None:
        _instruction_builder = InstructionBuilder()
    return _instruction_builder
