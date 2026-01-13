"""Portfolio-level risk management with dynamic adjustment.

Features:
- Portfolio heat monitoring (total exposure vs account)
- Correlation analysis between positions
- Dynamic risk adjustment based on performance
- Maximum drawdown protection
- Risk-per-trade optimization
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import defaultdict

from src.database import Database, get_database
from src.mt5_client import MT5Client, mt5_client

logger = logging.getLogger(__name__)


@dataclass
class PortfolioHeat:
    """Current portfolio heat metrics."""
    
    total_exposure: float          # Total $ at risk
    heat_percentage: float         # % of account at risk
    position_count: int           
    avg_position_risk: float       # Average risk per position
    max_position_risk: float       # Largest single position risk
    correlated_risk: float        # Additional risk from correlations
    risk_status: str              # green/yellow/red


@dataclass
class PositionCorrelation:
    """Correlation between two positions."""
    
    symbol1: str
    symbol2: str
    correlation: float            # -1 to 1
    shared_risk_factor: float     # 0 to 1 (how much risk overlaps)


@dataclass
class RiskAdjustment:
    """Dynamic risk adjustment recommendation."""
    
    current_risk_percent: float
    recommended_risk_percent: float
    adjustment_factor: float      # Multiplier for position size
    reason: str
    confidence: int


class PortfolioRiskManager:
    """Manages portfolio-level risk across all positions."""

    # Correlation thresholds (0-1 scale)
    CORRELATION_SIGNIFICANT = 0.3   # Report as risk factor
    CORRELATION_STRONG = 0.5        # Apply risk impact calculation
    CORRELATION_EXTREME = 0.7       # Reduce position size

    def __init__(self, mt5: Optional[MT5Client] = None,
                 db: Optional[Database] = None):
        self._mt5 = mt5
        self._db = db

        # Risk thresholds (as percentage 0-100)
        self.max_portfolio_heat = 6.0       # Max 6% of account at risk
        self.warning_heat = 4.0             # Warning at 4%
        self.max_positions = 3              # Max concurrent positions
        self.max_correlated_risk = 8.0      # Max 8% with correlations

        # Performance-based adjustments (all percentages use 0-100 scale)
        self.win_rate_target = 40.0         # Target 40% win rate
        self.profit_factor_target = 1.5     # Target 1.5 profit factor
        self.max_consecutive_losses = 3     # Reduce after 3 losses

        # Correlation matrix (simplified for gold pairs)
        self.correlation_matrix = {
            ('XAUUSD', 'XAUEUR'): 0.95,
            ('XAUUSD', 'XAGUSD'): 0.75,    # Gold vs Silver
            ('XAUUSD', 'EURUSD'): -0.30,   # Inverse correlation
            ('XAUUSD', 'USDJPY'): -0.25,
        }
    
    @property
    def mt5(self) -> MT5Client:
        """Lazy load MT5 client."""
        if self._mt5 is None:
            self._mt5 = mt5_client
        return self._mt5
    
    @property
    def db(self) -> Database:
        """Lazy load database."""
        if self._db is None:
            self._db = get_database()
        return self._db
    
    def calculate_portfolio_heat(self) -> PortfolioHeat:
        """Calculate current portfolio heat (total risk exposure).
        
        Returns:
            PortfolioHeat with current risk metrics
        """
        account_info = self.mt5.get_account_info()
        if not account_info:
            logger.error("Cannot get account info for heat calculation")
            return PortfolioHeat(
                total_exposure=0,
                heat_percentage=0,
                position_count=0,
                avg_position_risk=0,
                max_position_risk=0,
                correlated_risk=0,
                risk_status='unknown'
            )
        
        balance = account_info['balance']
        open_trades = self.db.get_open_trades()

        logger.info(f"[PortfolioHeat] Starting calculation - Balance: ${balance:,.2f}, Open trades: {len(open_trades) if open_trades else 0}")

        if not open_trades:
            logger.info("[PortfolioHeat] No open trades - returning green status")
            return PortfolioHeat(
                total_exposure=0,
                heat_percentage=0,
                position_count=0,
                avg_position_risk=0,
                max_position_risk=0,
                correlated_risk=0,
                risk_status='green'
            )
        
        # Calculate individual position risks
        position_risks = []
        positions_by_symbol = defaultdict(list)
        
        for trade in open_trades:
            # Get current position from MT5
            position = self.mt5.get_position_by_ticket(trade['ticket'])
            if not position:
                continue
            
            # Calculate risk for this position
            entry = trade['entry_price']
            sl = trade['stop_loss']
            volume = trade['volume']
            symbol = trade['symbol']
            
            # Risk in pips
            risk_pips = abs(entry - sl)

            # Risk in dollars (simplified for XAUUSD)
            # For gold: 1 lot = 100 oz, 1 pip = $0.10/oz = $10/lot
            risk_dollars = risk_pips * volume * 100

            logger.info(
                f"[PortfolioHeat] Position #{trade['ticket']}: "
                f"{symbol} {trade.get('action', 'N/A')} | "
                f"Entry: {entry:.2f}, SL: {sl:.2f} | "
                f"Vol: {volume} lots | "
                f"Risk: {risk_pips:.2f} pips = ${risk_dollars:.2f}"
            )

            position_risks.append(risk_dollars)
            positions_by_symbol[symbol].append({
                'trade': trade,
                'risk': risk_dollars
            })
        
        # Calculate base metrics
        total_exposure = sum(position_risks)
        heat_percentage = (total_exposure / balance) * 100 if balance > 0 else 0
        position_count = len(position_risks)
        avg_position_risk = np.mean(position_risks) if position_risks else 0
        max_position_risk = max(position_risks) if position_risks else 0
        
        # Calculate correlation risk
        correlated_risk = self._calculate_correlation_risk(
            positions_by_symbol, balance
        )
        
        # Log calculation summary
        logger.info(
            f"[PortfolioHeat] Summary: "
            f"Total Exposure: ${total_exposure:.2f} | "
            f"Positions: {position_count} | "
            f"Avg Risk: ${avg_position_risk:.2f} | "
            f"Max Risk: ${max_position_risk:.2f}"
        )

        # Determine risk status
        total_heat_with_correlation = heat_percentage + correlated_risk
        if total_heat_with_correlation >= self.max_portfolio_heat:
            risk_status = 'red'
        elif total_heat_with_correlation >= self.warning_heat:
            risk_status = 'yellow'
        else:
            risk_status = 'green'

        logger.info(
            f"[PortfolioHeat] Final: "
            f"Base Heat: {heat_percentage:.2f}% + Correlated: {correlated_risk:.2f}% = "
            f"Total: {total_heat_with_correlation:.2f}% | "
            f"Thresholds: warn={self.warning_heat:.0f}%, max={self.max_portfolio_heat:.0f}% | "
            f"Status: {risk_status.upper()}"
        )
        
        return PortfolioHeat(
            total_exposure=round(total_exposure, 2),
            heat_percentage=round(heat_percentage, 2),
            position_count=position_count,
            avg_position_risk=round(avg_position_risk, 2),
            max_position_risk=round(max_position_risk, 2),
            correlated_risk=round(correlated_risk, 2),
            risk_status=risk_status
        )
    
    def _calculate_correlation_risk(self, positions_by_symbol: Dict,
                                   balance: float) -> float:
        """Calculate additional risk from correlated positions.
        
        Args:
            positions_by_symbol: Dict of symbol -> position info
            balance: Account balance
            
        Returns:
            Additional risk percentage from correlations
        """
        if len(positions_by_symbol) <= 1:
            return 0.0
        
        additional_risk = 0.0
        symbols = list(positions_by_symbol.keys())
        
        # Check each pair of positions
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                symbol1, symbol2 = symbols[i], symbols[j]
                
                # Get correlation
                correlation = self._get_correlation(symbol1, symbol2)
                
                if abs(correlation) > self.CORRELATION_SIGNIFICANT:
                    # Calculate overlapping risk
                    risk1 = sum(p['risk'] for p in positions_by_symbol[symbol1])
                    risk2 = sum(p['risk'] for p in positions_by_symbol[symbol2])
                    
                    # Correlated risk = correlation * smaller risk
                    corr_risk = abs(correlation) * min(risk1, risk2)
                    additional_risk += corr_risk
        
        # Convert to percentage of balance
        return (additional_risk / balance * 100) if balance > 0 else 0
    
    def _get_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation coefficient between two symbols.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            
        Returns:
            Correlation coefficient (-1 to 1)
        """
        # Check direct correlation
        key1 = (symbol1, symbol2)
        key2 = (symbol2, symbol1)
        
        if key1 in self.correlation_matrix:
            return self.correlation_matrix[key1]
        elif key2 in self.correlation_matrix:
            return self.correlation_matrix[key2]
        else:
            # No known correlation
            return 0.0
    
    def check_position_allowed(self, symbol: str, 
                              proposed_risk_dollars: float) -> Tuple[bool, str]:
        """Check if a new position is allowed given current portfolio risk.
        
        Args:
            symbol: Symbol for new position
            proposed_risk_dollars: Risk amount for new position
            
        Returns:
            Tuple of (allowed, reason)
        """
        # Get current heat
        heat = self.calculate_portfolio_heat()
        
        # Check position count
        if heat.position_count >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"
        
        # Get account info
        account_info = self.mt5.get_account_info()
        if not account_info:
            return False, "Cannot get account info"
        
        balance = account_info['balance']
        
        # Calculate new heat with proposed position
        new_risk_pct = proposed_risk_dollars / balance * 100
        new_total_heat = heat.heat_percentage + new_risk_pct
        
        # Check if similar position exists (concentration risk)
        open_trades = self.db.get_open_trades()
        same_symbol_count = sum(1 for t in open_trades if t['symbol'] == symbol)
        if same_symbol_count >= 2:
            return False, f"Too many {symbol} positions (max 2)"
        
        # Calculate correlation impact
        correlation_impact = 0
        for trade in open_trades:
            correlation = self._get_correlation(symbol, trade['symbol'])
            if abs(correlation) > self.CORRELATION_STRONG:
                correlation_impact += abs(correlation) * new_risk_pct * 0.5
        
        total_heat_with_correlation = new_total_heat + correlation_impact
        
        # Check against limits
        if total_heat_with_correlation > self.max_portfolio_heat:
            return False, (f"Portfolio heat too high: "
                          f"{total_heat_with_correlation:.1f}% > "
                          f"{self.max_portfolio_heat:.0f}%")
        
        return True, "Position allowed"
    
    def calculate_dynamic_risk(self) -> RiskAdjustment:
        """Calculate dynamic risk adjustment based on recent performance.
        
        Returns:
            RiskAdjustment with recommended risk parameters
        """
        from src.config import get_settings
        settings = get_settings()
        base_risk = settings.risk_percent
        
        # Get recent performance
        lookback_days = 30
        start_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        
        recent_trades = self.db.get_trades_for_analytics(
            start_date=start_date.isoformat()
        )
        
        if len(recent_trades) < 5:
            # Not enough data, use base risk
            return RiskAdjustment(
                current_risk_percent=base_risk,
                recommended_risk_percent=base_risk,
                adjustment_factor=1.0,
                reason="Insufficient trade history",
                confidence=50
            )
        
        # Calculate performance metrics
        wins = [t for t in recent_trades if t['profit'] > 0]
        losses = [t for t in recent_trades if t['profit'] <= 0]
        
        win_rate = (len(wins) / len(recent_trades) * 100) if recent_trades else 0  # 0-100 scale
        avg_win = np.mean([t['profit'] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t['profit'] for t in losses])) if losses else 1
        
        profit_factor = (avg_win * len(wins)) / (avg_loss * len(losses)) if losses else 0
        
        # Check consecutive losses
        consecutive_losses = self._count_consecutive_losses(recent_trades)
        
        # Start with base risk
        recommended_risk = base_risk
        adjustment_factor = 1.0
        reasons = []
        
        # Adjust based on win rate (0-100 scale)
        if win_rate < 30.0:
            adjustment_factor *= 0.7
            reasons.append(f"Low win rate ({win_rate:.1f}%)")
        elif win_rate > 50.0:
            adjustment_factor *= 1.1
            reasons.append(f"High win rate ({win_rate:.1f}%)")
        
        # Adjust based on profit factor
        if profit_factor < 1.0:
            adjustment_factor *= 0.8
            reasons.append(f"Profit factor < 1.0 ({profit_factor:.1f})")
        elif profit_factor > 2.0:
            adjustment_factor *= 1.2
            reasons.append(f"Strong profit factor ({profit_factor:.1f})")
        
        # Adjust based on consecutive losses
        if consecutive_losses >= self.max_consecutive_losses:
            adjustment_factor *= 0.5
            reasons.append(f"{consecutive_losses} consecutive losses")
        
        # Account health check
        account_info = self.mt5.get_account_info()
        if account_info:
            equity = account_info['equity']
            balance = account_info['balance']
            
            # Check drawdown
            if equity < balance * 0.90:  # 10% drawdown
                adjustment_factor *= 0.7
                reasons.append("Account in drawdown")
        
        # Apply limits
        adjustment_factor = max(0.3, min(1.5, adjustment_factor))
        recommended_risk = base_risk * adjustment_factor
        
        # Confidence based on data quality
        confidence = min(90, 50 + len(recent_trades) * 2)
        
        reason = ", ".join(reasons) if reasons else "Normal conditions"
        
        logger.info(
            f"Risk adjustment: {base_risk}% -> {recommended_risk:.1f}% "
            f"(factor={adjustment_factor:.2f}), Reason: {reason}"
        )
        
        return RiskAdjustment(
            current_risk_percent=base_risk,
            recommended_risk_percent=round(recommended_risk, 1),
            adjustment_factor=round(adjustment_factor, 2),
            reason=reason,
            confidence=confidence
        )
    
    def _count_consecutive_losses(self, trades: List[dict]) -> int:
        """Count consecutive losses from most recent trades.
        
        Args:
            trades: List of trade dicts sorted by time
            
        Returns:
            Number of consecutive losses
        """
        if not trades:
            return 0
        
        # Sort by close time (most recent first)
        sorted_trades = sorted(
            trades,
            key=lambda t: t.get('close_time', t.get('open_time', '')),
            reverse=True
        )
        
        consecutive = 0
        for trade in sorted_trades:
            if trade['profit'] <= 0:
                consecutive += 1
            else:
                break
        
        return consecutive
    
    def get_position_size_recommendation(self, symbol: str, 
                                       stop_loss_pips: float) -> Dict:
        """Get recommended position size based on portfolio risk.
        
        Args:
            symbol: Trading symbol
            stop_loss_pips: Stop loss distance in pips
            
        Returns:
            Dict with size recommendations
        """
        # Get current portfolio state
        heat = self.calculate_portfolio_heat()
        risk_adj = self.calculate_dynamic_risk()
        
        # Get account info
        account_info = self.mt5.get_account_info()
        if not account_info:
            return {
                'recommended_lots': 0.01,
                'max_lots': 0.01,
                'risk_percent': 1.0,
                'warnings': ['Cannot get account info']
            }
        
        balance = account_info['balance']
        
        # Calculate position size based on adjusted risk
        risk_amount = balance * (risk_adj.recommended_risk_percent / 100)
        
        # For XAUUSD: pip value = $10 per lot
        pip_value = 10  # Would get from symbol info
        
        lots = risk_amount / (stop_loss_pips * pip_value)
        lots = round(lots, 2)
        
        # Apply portfolio heat limits
        warnings = []
        max_lots = lots
        
        if heat.risk_status == 'yellow':
            max_lots = lots * 0.8
            warnings.append('Portfolio heat elevated - size reduced 20%')
        elif heat.risk_status == 'red':
            max_lots = lots * 0.5
            warnings.append('Portfolio heat critical - size reduced 50%')
        
        # Check correlation impact
        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            correlation = self._get_correlation(symbol, trade['symbol'])
            if abs(correlation) > self.CORRELATION_EXTREME:
                max_lots *= (1 - abs(correlation) * 0.3)
                warnings.append(
                    f'High correlation with {trade["symbol"]} '
                    f'({correlation:.0%})'
                )
        
        # Apply minimum
        max_lots = max(0.01, round(max_lots, 2))
        
        return {
            'recommended_lots': lots,
            'max_lots': max_lots,
            'risk_percent': risk_adj.recommended_risk_percent,
            'adjustment_factor': risk_adj.adjustment_factor,
            'portfolio_heat': heat.heat_percentage,
            'warnings': warnings
        }
    
    def should_pause_trading(self) -> Tuple[bool, str]:
        """Determine if trading should be paused due to risk.
        
        Returns:
            Tuple of (should_pause, reason)
        """
        # Check portfolio heat
        heat = self.calculate_portfolio_heat()
        if heat.risk_status == 'red':
            return True, f"Portfolio heat critical: {heat.heat_percentage:.1f}%"
        
        # Check consecutive losses
        recent_trades = self.db.get_trades_for_analytics(
            start_date=(datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        )
        
        consecutive_losses = self._count_consecutive_losses(recent_trades)
        if consecutive_losses >= self.max_consecutive_losses + 2:
            return True, f"{consecutive_losses} consecutive losses"
        
        # Check daily loss limit
        today_trades = [
            t for t in recent_trades
            if datetime.fromisoformat(t['open_time'].replace('Z', '+00:00')).date() == 
               datetime.now(timezone.utc).date()
        ]
        
        if today_trades:
            daily_pnl = sum(t['profit'] for t in today_trades)
            account_info = self.mt5.get_account_info()
            
            if account_info:
                balance = account_info['balance']
                daily_loss_pct = abs(daily_pnl / balance * 100)
                
                if daily_pnl < 0 and daily_loss_pct > 3:
                    return True, f"Daily loss limit: -{daily_loss_pct:.1f}%"
        
        return False, "Trading allowed"
    
    def get_risk_report(self) -> Dict:
        """Generate comprehensive risk report.
        
        Returns:
            Dict with risk metrics and recommendations
        """
        heat = self.calculate_portfolio_heat()
        risk_adj = self.calculate_dynamic_risk()
        should_pause, pause_reason = self.should_pause_trading()
        
        # Get correlation analysis
        correlations = self._analyze_portfolio_correlations()
        
        # Get position concentration
        concentration = self._analyze_position_concentration()
        
        report = {
            'portfolio_heat': {
                'total_exposure': heat.total_exposure,
                'heat_percentage': heat.heat_percentage,
                'position_count': heat.position_count,
                'status': heat.risk_status,
                'correlated_risk': heat.correlated_risk
            },
            'risk_adjustment': {
                'current_risk': risk_adj.current_risk_percent,
                'recommended_risk': risk_adj.recommended_risk_percent,
                'adjustment_factor': risk_adj.adjustment_factor,
                'reason': risk_adj.reason
            },
            'trading_status': {
                'paused': should_pause,
                'reason': pause_reason if should_pause else 'Active'
            },
            'correlations': correlations,
            'concentration': concentration,
            'recommendations': self._generate_recommendations(
                heat, risk_adj, correlations, concentration
            )
        }
        
        return report
    
    def _analyze_portfolio_correlations(self) -> List[Dict]:
        """Analyze correlations between open positions.
        
        Returns:
            List of correlation info dicts
        """
        open_trades = self.db.get_open_trades()
        if len(open_trades) <= 1:
            return []
        
        correlations = []
        symbols = list(set(t['symbol'] for t in open_trades))
        
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                corr = self._get_correlation(symbols[i], symbols[j])
                if abs(corr) > self.CORRELATION_SIGNIFICANT:
                    correlations.append({
                        'pair': f"{symbols[i]}/{symbols[j]}",
                        'correlation': corr,
                        'risk': 'High' if abs(corr) > self.CORRELATION_EXTREME else 'Medium'
                    })
        
        return correlations
    
    def _analyze_position_concentration(self) -> Dict:
        """Analyze position concentration by symbol.
        
        Returns:
            Dict with concentration metrics
        """
        open_trades = self.db.get_open_trades()
        if not open_trades:
            return {'concentrated': False, 'symbols': {}}
        
        # Count by symbol
        symbol_counts = defaultdict(int)
        symbol_exposure = defaultdict(float)
        
        for trade in open_trades:
            symbol = trade['symbol']
            symbol_counts[symbol] += 1
            
            # Calculate exposure
            risk = abs(trade['entry_price'] - trade['stop_loss']) * trade['volume'] * 100
            symbol_exposure[symbol] += risk
        
        # Check concentration
        total_positions = len(open_trades)
        concentrated = any(count > total_positions * 0.5 
                          for count in symbol_counts.values())
        
        return {
            'concentrated': concentrated,
            'symbols': dict(symbol_counts),
            'exposure': dict(symbol_exposure)
        }
    
    def _generate_recommendations(self, heat: PortfolioHeat,
                                risk_adj: RiskAdjustment,
                                correlations: List[Dict],
                                concentration: Dict) -> List[str]:
        """Generate risk management recommendations.
        
        Args:
            heat: Portfolio heat metrics
            risk_adj: Risk adjustment info
            correlations: Correlation analysis
            concentration: Position concentration
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Heat recommendations
        if heat.risk_status == 'red':
            recommendations.append("⚠️ Reduce position sizes or close some positions")
        elif heat.risk_status == 'yellow':
            recommendations.append("📊 Monitor positions closely, avoid new trades")
        
        # Risk adjustment recommendations
        if risk_adj.adjustment_factor < 0.7:
            recommendations.append("📉 Consider reducing risk per trade")
        elif risk_adj.adjustment_factor > 1.2:
            recommendations.append("📈 Can cautiously increase position sizes")
        
        # Correlation recommendations
        high_corr = [c for c in correlations if c['risk'] == 'High']
        if high_corr:
            recommendations.append(
                f"🔗 High correlation detected: {high_corr[0]['pair']}"
            )
        
        # Concentration recommendations
        if concentration['concentrated']:
            recommendations.append("🎯 Diversify - too concentrated in one symbol")
        
        # Position count
        if heat.position_count >= self.max_positions:
            recommendations.append(f"📍 At max positions ({self.max_positions})")
        
        return recommendations


# Singleton instance
_portfolio_risk_manager: Optional[PortfolioRiskManager] = None


def get_portfolio_risk_manager() -> PortfolioRiskManager:
    """Get or create portfolio risk manager singleton."""
    global _portfolio_risk_manager
    if _portfolio_risk_manager is None:
        _portfolio_risk_manager = PortfolioRiskManager()
    return _portfolio_risk_manager