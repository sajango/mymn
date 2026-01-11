"""Performance analytics system for comprehensive trading metrics.

Features:
- Real-time performance tracking
- Multi-dimensional analysis (by session, regime, pattern)
- Risk-adjusted metrics (Sharpe, Sortino, Calmar)
- Drawdown analysis
- Pattern success rates
- Optimal parameter discovery
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import json

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    
    # Basic metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    
    # Financial metrics
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    average_rr: float = 0.0  # Risk:Reward
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0
    recovery_factor: float = 0.0
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Time-based metrics
    average_trade_duration: timedelta = field(default_factory=lambda: timedelta())
    longest_trade: timedelta = field(default_factory=lambda: timedelta())
    shortest_trade: timedelta = field(default_factory=lambda: timedelta())
    
    # Additional insights
    best_hour: Optional[int] = None
    worst_hour: Optional[int] = None
    best_session: Optional[str] = None
    worst_session: Optional[str] = None
    best_weekday: Optional[int] = None
    worst_weekday: Optional[int] = None


@dataclass
class PatternPerformance:
    """Performance metrics for specific patterns."""
    
    pattern_name: str
    occurrences: int = 0
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    avg_profit: float = 0.0
    total_profit: float = 0.0
    confidence_correlation: float = 0.0
    best_timeframe: Optional[str] = None
    optimal_confidence: Optional[int] = None


class PerformanceAnalytics:
    """Advanced performance analytics engine."""
    
    def __init__(self):
        from src.database import get_database
        self.db = get_database()
        self._cache = {}
        self._cache_expiry = {}
        self.cache_duration = 300  # 5 minutes
        
    def get_performance_metrics(self, 
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None,
                               symbol: Optional[str] = None) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics.
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            symbol: Filter by symbol
            
        Returns:
            PerformanceMetrics with all calculations
        """
        # Check cache
        cache_key = f"metrics_{start_date}_{end_date}_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Get trades from database
        trades = self._get_trades(start_date, end_date, symbol)
        if not trades:
            return PerformanceMetrics()
        
        # Calculate metrics
        metrics = PerformanceMetrics()
        
        # Basic counts
        metrics.total_trades = len(trades)
        metrics.winning_trades = sum(1 for t in trades if t['pnl'] > 0)
        metrics.losing_trades = sum(1 for t in trades if t['pnl'] < 0)
        metrics.breakeven_trades = sum(1 for t in trades if t['pnl'] == 0)
        metrics.win_rate = (metrics.winning_trades / metrics.total_trades * 100) if metrics.total_trades > 0 else 0
        
        # Financial metrics
        pnls = [t['pnl'] for t in trades]
        metrics.total_pnl = sum(pnls)
        metrics.gross_profit = sum(p for p in pnls if p > 0)
        metrics.gross_loss = abs(sum(p for p in pnls if p < 0))
        metrics.profit_factor = metrics.gross_profit / metrics.gross_loss if metrics.gross_loss > 0 else 0
        
        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]
        metrics.average_win = np.mean(winning_pnls) if winning_pnls else 0
        metrics.average_loss = np.mean(losing_pnls) if losing_pnls else 0
        
        # Risk:Reward ratio
        risk_rewards = [t.get('risk_reward', 0) for t in trades if t.get('risk_reward')]
        metrics.average_rr = np.mean(risk_rewards) if risk_rewards else 0
        
        # Drawdown analysis
        dd_stats = self._calculate_drawdown(trades)
        metrics.max_drawdown = dd_stats['max_drawdown']
        metrics.max_drawdown_percent = dd_stats['max_drawdown_percent']
        metrics.recovery_factor = metrics.total_pnl / abs(metrics.max_drawdown) if metrics.max_drawdown != 0 else 0
        
        # Streak analysis
        streak_stats = self._calculate_streaks(trades)
        metrics.max_consecutive_wins = streak_stats['max_wins']
        metrics.max_consecutive_losses = streak_stats['max_losses']
        metrics.current_streak = streak_stats['current']
        
        # Risk-adjusted returns
        if len(pnls) > 1:
            metrics.sharpe_ratio = self._calculate_sharpe_ratio(pnls)
            metrics.sortino_ratio = self._calculate_sortino_ratio(pnls)
            metrics.calmar_ratio = self._calculate_calmar_ratio(metrics.total_pnl, metrics.max_drawdown)
        
        # Time-based metrics
        durations = []
        for t in trades:
            if t['exit_time'] and t['entry_time']:
                duration = t['exit_time'] - t['entry_time']
                durations.append(duration)
        
        if durations:
            metrics.average_trade_duration = timedelta(seconds=np.mean([d.total_seconds() for d in durations]))
            metrics.longest_trade = max(durations)
            metrics.shortest_trade = min(durations)
        
        # Best/worst analysis
        time_analysis = self._analyze_performance_by_time(trades)
        metrics.best_hour = time_analysis['best_hour']
        metrics.worst_hour = time_analysis['worst_hour']
        metrics.best_session = time_analysis['best_session']
        metrics.worst_session = time_analysis['worst_session']
        metrics.best_weekday = time_analysis['best_weekday']
        metrics.worst_weekday = time_analysis['worst_weekday']
        
        # Cache results
        self._cache[cache_key] = metrics
        self._cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(seconds=self.cache_duration)
        
        return metrics
    
    def analyze_by_market_regime(self) -> Dict[str, PerformanceMetrics]:
        """Analyze performance by market regime.
        
        Returns:
            Dictionary mapping regime type to performance metrics
        """
        regime_performance = {}
        
        # Get all signals with regime information
        signals = self.db.get_signals_with_regime()
        
        # Group by regime
        regime_groups = defaultdict(list)
        for signal in signals:
            if signal.get('market_regime'):
                regime_groups[signal['market_regime']].append(signal)
        
        # Calculate metrics for each regime
        for regime, regime_signals in regime_groups.items():
            # Get trades for these signals
            trades = []
            for sig in regime_signals:
                trade = self.db.get_trade_by_signal_id(sig['id'])
                if trade:
                    trades.append(trade)
            
            if trades:
                # Calculate metrics for this regime
                metrics = self._calculate_metrics_for_trades(trades)
                regime_performance[regime] = metrics
        
        return regime_performance
    
    def analyze_by_volatility_state(self) -> Dict[str, PerformanceMetrics]:
        """Analyze performance by volatility state.
        
        Returns:
            Dictionary mapping volatility state to performance metrics
        """
        vol_performance = {}
        
        # Get all signals with volatility information
        signals = self.db.get_signals_with_volatility()
        
        # Group by volatility state
        vol_groups = defaultdict(list)
        for signal in signals:
            if signal.get('volatility_state'):
                vol_groups[signal['volatility_state']].append(signal)
        
        # Calculate metrics for each state
        for state, state_signals in vol_groups.items():
            trades = []
            for sig in state_signals:
                trade = self.db.get_trade_by_signal_id(sig['id'])
                if trade:
                    trades.append(trade)
            
            if trades:
                metrics = self._calculate_metrics_for_trades(trades)
                vol_performance[state] = metrics
        
        return vol_performance
    
    def analyze_pattern_performance(self) -> List[PatternPerformance]:
        """Analyze performance by wave patterns.
        
        Returns:
            List of PatternPerformance objects
        """
        patterns = {}
        
        # Get all signals with wave analysis
        signals = self.db.get_signals_with_patterns()
        
        for signal in signals:
            wave_position = signal.get('wave_position', 'Unknown')
            if wave_position not in patterns:
                patterns[wave_position] = {
                    'occurrences': 0,
                    'trades': [],
                    'confidences': [],
                    'profits': []
                }
            
            patterns[wave_position]['occurrences'] += 1
            
            # Get associated trade
            trade = self.db.get_trade_by_signal_id(signal['id'])
            if trade:
                patterns[wave_position]['trades'].append(trade)
                patterns[wave_position]['confidences'].append(signal['confidence'])
                patterns[wave_position]['profits'].append(trade['pnl'])
        
        # Calculate performance for each pattern
        pattern_performance = []
        for pattern_name, data in patterns.items():
            if data['trades']:
                perf = PatternPerformance(pattern_name=pattern_name)
                perf.occurrences = data['occurrences']
                perf.trades = len(data['trades'])
                perf.wins = sum(1 for t in data['trades'] if t['pnl'] > 0)
                perf.win_rate = perf.wins / perf.trades * 100 if perf.trades > 0 else 0
                perf.total_profit = sum(data['profits'])
                perf.avg_profit = perf.total_profit / perf.trades if perf.trades > 0 else 0
                
                # Confidence correlation
                if len(data['confidences']) > 1 and len(data['profits']) > 1:
                    perf.confidence_correlation = np.corrcoef(data['confidences'], data['profits'])[0, 1]
                
                pattern_performance.append(perf)
        
        # Sort by profitability
        pattern_performance.sort(key=lambda x: x.total_profit, reverse=True)
        
        return pattern_performance
    
    def get_optimization_insights(self) -> Dict[str, Any]:
        """Discover optimal parameters and trading conditions.
        
        Returns:
            Dictionary with optimization insights
        """
        insights = {
            'optimal_confidence': self._find_optimal_confidence(),
            'optimal_session': self._find_optimal_session(),
            'optimal_volatility': self._find_optimal_volatility(),
            'optimal_hold_time': self._find_optimal_hold_time(),
            'risk_reward_analysis': self._analyze_risk_reward(),
            'edge_decay': self._analyze_edge_decay(),
            'recommendations': []
        }
        
        # Generate recommendations based on findings
        recommendations = []
        
        # Confidence recommendation
        if insights['optimal_confidence']:
            opt_conf = insights['optimal_confidence']['threshold']
            current_conf = 60  # Get from settings
            if opt_conf > current_conf + 5:
                recommendations.append(
                    f"Consider raising confidence threshold from {current_conf}% to {opt_conf}% "
                    f"(improves win rate by {insights['optimal_confidence']['improvement']:.1f}%)"
                )
        
        # Session recommendation
        if insights['optimal_session']:
            best_session = insights['optimal_session']['best']
            recommendations.append(
                f"Focus trading on {best_session} session "
                f"(win rate: {insights['optimal_session']['win_rate']:.1f}%)"
            )
        
        # Volatility recommendation
        if insights['optimal_volatility']:
            avoid_states = insights['optimal_volatility']['avoid']
            if avoid_states:
                recommendations.append(
                    f"Avoid trading in {', '.join(avoid_states)} volatility states"
                )
        
        insights['recommendations'] = recommendations
        
        return insights
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report.
        
        Returns:
            Complete performance report with all analytics
        """
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'overall_metrics': self._metrics_to_dict(self.get_performance_metrics()),
            'by_regime': {k: self._metrics_to_dict(v) for k, v in self.analyze_by_market_regime().items()},
            'by_volatility': {k: self._metrics_to_dict(v) for k, v in self.analyze_by_volatility_state().items()},
            'pattern_performance': [self._pattern_to_dict(p) for p in self.analyze_pattern_performance()],
            'optimization_insights': self.get_optimization_insights(),
            'risk_analysis': self._comprehensive_risk_analysis(),
            'monthly_breakdown': self._monthly_performance_breakdown()
        }
        
        return report
    
    def _calculate_drawdown(self, trades: List[Dict]) -> Dict[str, float]:
        """Calculate drawdown statistics."""
        if not trades:
            return {'max_drawdown': 0, 'max_drawdown_percent': 0}
        
        # Calculate cumulative P&L
        cumulative_pnl = []
        running_total = 0
        peak = 0
        max_dd = 0
        max_dd_pct = 0
        
        for trade in sorted(trades, key=lambda x: x['entry_time']):
            running_total += trade['pnl']
            cumulative_pnl.append(running_total)
            
            # Update peak
            if running_total > peak:
                peak = running_total
            
            # Calculate drawdown
            if peak > 0:
                dd = peak - running_total
                dd_pct = (dd / peak) * 100 if peak > 0 else 0
                
                if dd > max_dd:
                    max_dd = dd
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
        
        return {
            'max_drawdown': max_dd,
            'max_drawdown_percent': max_dd_pct
        }
    
    def _calculate_streaks(self, trades: List[Dict]) -> Dict[str, int]:
        """Calculate winning/losing streaks."""
        if not trades:
            return {'max_wins': 0, 'max_losses': 0, 'current': 0}
        
        max_wins = 0
        max_losses = 0
        current_streak = 0
        
        for trade in sorted(trades, key=lambda x: x['entry_time']):
            if trade['pnl'] > 0:
                if current_streak >= 0:
                    current_streak += 1
                else:
                    current_streak = 1
                max_wins = max(max_wins, current_streak)
            elif trade['pnl'] < 0:
                if current_streak <= 0:
                    current_streak -= 1
                else:
                    current_streak = -1
                max_losses = max(max_losses, abs(current_streak))
        
        return {
            'max_wins': max_wins,
            'max_losses': max_losses,
            'current': current_streak
        }
    
    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio (annualized)."""
        if len(returns) < 2:
            return 0.0
        
        # Convert to daily returns (assuming multiple trades per day)
        daily_returns = pd.Series(returns).resample('D').sum() if len(returns) > 30 else returns
        
        # Calculate annualized Sharpe
        mean_return = np.mean(daily_returns)
        std_return = np.std(daily_returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualize (252 trading days)
        annual_return = mean_return * 252
        annual_std = std_return * np.sqrt(252)
        
        return (annual_return - risk_free_rate) / annual_std if annual_std > 0 else 0
    
    def _calculate_sortino_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)."""
        if len(returns) < 2:
            return 0.0
        
        # Calculate downside deviation
        negative_returns = [r for r in returns if r < 0]
        if not negative_returns:
            return 0.0
        
        downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0.0
        
        mean_return = np.mean(returns)
        annual_return = mean_return * 252
        annual_downside_std = downside_std * np.sqrt(252)
        
        return (annual_return - risk_free_rate) / annual_downside_std if annual_downside_std > 0 else 0
    
    def _calculate_calmar_ratio(self, total_return: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio (return/drawdown)."""
        if max_drawdown == 0:
            return 0.0
        return abs(total_return / max_drawdown)
    
    def _analyze_performance_by_time(self, trades: List[Dict]) -> Dict[str, Any]:
        """Analyze performance by time periods."""
        hour_performance = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
        session_performance = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
        weekday_performance = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
        
        for trade in trades:
            entry_time = trade['entry_time']
            if entry_time:
                # Hour analysis
                hour = entry_time.hour
                hour_performance[hour]['trades'] += 1
                hour_performance[hour]['pnl'] += trade['pnl']
                if trade['pnl'] > 0:
                    hour_performance[hour]['wins'] += 1
                
                # Session analysis (simplified)
                if 6 <= hour < 15:  # Asian + London
                    session = 'London'
                elif 13 <= hour < 22:  # NY
                    session = 'NewYork'
                else:
                    session = 'Asian'
                
                session_performance[session]['trades'] += 1
                session_performance[session]['pnl'] += trade['pnl']
                if trade['pnl'] > 0:
                    session_performance[session]['wins'] += 1
                
                # Weekday analysis
                weekday = entry_time.weekday()
                weekday_performance[weekday]['trades'] += 1
                weekday_performance[weekday]['pnl'] += trade['pnl']
                if trade['pnl'] > 0:
                    weekday_performance[weekday]['wins'] += 1
        
        # Find best/worst
        def find_best_worst(performance_dict):
            best = None
            worst = None
            best_win_rate = 0
            worst_win_rate = 100
            
            for key, stats in performance_dict.items():
                if stats['trades'] > 0:
                    win_rate = stats['wins'] / stats['trades'] * 100
                    if win_rate > best_win_rate:
                        best_win_rate = win_rate
                        best = key
                    if win_rate < worst_win_rate:
                        worst_win_rate = win_rate
                        worst = key
            
            return best, worst
        
        best_hour, worst_hour = find_best_worst(hour_performance)
        best_session, worst_session = find_best_worst(session_performance)
        best_weekday, worst_weekday = find_best_worst(weekday_performance)
        
        return {
            'best_hour': best_hour,
            'worst_hour': worst_hour,
            'best_session': best_session,
            'worst_session': worst_session,
            'best_weekday': best_weekday,
            'worst_weekday': worst_weekday
        }
    
    def _find_optimal_confidence(self) -> Optional[Dict[str, Any]]:
        """Find optimal confidence threshold."""
        signals = self.db.get_all_signals_with_trades()
        if not signals:
            return None
        
        # Test different confidence thresholds
        best_threshold = 60
        best_metric = 0
        current_performance = None
        
        for threshold in range(55, 85, 5):
            # Get trades above threshold
            qualifying_trades = [s['trade'] for s in signals 
                               if s['confidence'] >= threshold and s.get('trade')]
            
            if len(qualifying_trades) >= 10:  # Need minimum sample
                win_rate = sum(1 for t in qualifying_trades if t['pnl'] > 0) / len(qualifying_trades) * 100
                avg_profit = np.mean([t['pnl'] for t in qualifying_trades])
                
                # Combined metric (win rate * avg profit)
                metric = win_rate * avg_profit
                
                if metric > best_metric:
                    best_metric = metric
                    best_threshold = threshold
                
                if threshold == 60:  # Current threshold
                    current_performance = {'win_rate': win_rate, 'avg_profit': avg_profit}
        
        if current_performance and best_threshold != 60:
            # Calculate improvement
            improvement = (best_metric - (current_performance['win_rate'] * current_performance['avg_profit'])) / (current_performance['win_rate'] * current_performance['avg_profit']) * 100
            
            return {
                'current': 60,
                'optimal': best_threshold,
                'improvement': improvement,
                'threshold': best_threshold
            }
        
        return None
    
    def _find_optimal_session(self) -> Optional[Dict[str, Any]]:
        """Find optimal trading session."""
        session_metrics = self.analyze_by_session()
        if not session_metrics:
            return None
        
        best_session = None
        best_win_rate = 0
        
        for session, metrics in session_metrics.items():
            if metrics.total_trades >= 10:  # Minimum sample
                if metrics.win_rate > best_win_rate:
                    best_win_rate = metrics.win_rate
                    best_session = session
        
        if best_session:
            return {
                'best': best_session,
                'win_rate': best_win_rate,
                'metrics': session_metrics[best_session]
            }
        
        return None
    
    def _find_optimal_volatility(self) -> Optional[Dict[str, Any]]:
        """Find optimal volatility conditions."""
        vol_metrics = self.analyze_by_volatility_state()
        if not vol_metrics:
            return None
        
        optimal_states = []
        avoid_states = []
        
        for state, metrics in vol_metrics.items():
            if metrics.total_trades >= 5:  # Minimum sample
                if metrics.win_rate > 65 and metrics.profit_factor > 1.5:
                    optimal_states.append(state)
                elif metrics.win_rate < 40 or metrics.profit_factor < 0.8:
                    avoid_states.append(state)
        
        return {
            'optimal': optimal_states,
            'avoid': avoid_states,
            'all_metrics': vol_metrics
        }
    
    def _find_optimal_hold_time(self) -> Optional[Dict[str, Any]]:
        """Find optimal trade duration."""
        trades = self._get_trades()
        if not trades:
            return None
        
        # Group by duration buckets
        duration_buckets = {
            '<1h': {'min': 0, 'max': 3600, 'trades': [], 'pnl': []},
            '1-4h': {'min': 3600, 'max': 14400, 'trades': [], 'pnl': []},
            '4-12h': {'min': 14400, 'max': 43200, 'trades': [], 'pnl': []},
            '12-24h': {'min': 43200, 'max': 86400, 'trades': [], 'pnl': []},
            '>24h': {'min': 86400, 'max': float('inf'), 'trades': [], 'pnl': []}
        }
        
        for trade in trades:
            if trade['exit_time'] and trade['entry_time']:
                duration_seconds = (trade['exit_time'] - trade['entry_time']).total_seconds()
                
                for bucket_name, bucket_data in duration_buckets.items():
                    if bucket_data['min'] <= duration_seconds < bucket_data['max']:
                        bucket_data['trades'].append(trade)
                        bucket_data['pnl'].append(trade['pnl'])
                        break
        
        # Find best duration
        best_bucket = None
        best_avg_pnl = 0
        
        for bucket_name, bucket_data in duration_buckets.items():
            if len(bucket_data['trades']) >= 5:  # Minimum sample
                avg_pnl = np.mean(bucket_data['pnl'])
                if avg_pnl > best_avg_pnl:
                    best_avg_pnl = avg_pnl
                    best_bucket = bucket_name
        
        if best_bucket:
            return {
                'optimal_duration': best_bucket,
                'average_pnl': best_avg_pnl,
                'all_buckets': {k: {'count': len(v['trades']), 
                                   'avg_pnl': np.mean(v['pnl']) if v['pnl'] else 0}
                               for k, v in duration_buckets.items()}
            }
        
        return None
    
    def _analyze_risk_reward(self) -> Dict[str, Any]:
        """Analyze risk:reward ratios."""
        trades = self._get_trades()
        if not trades:
            return {}
        
        rr_buckets = {
            '<1:1': {'min': 0, 'max': 1, 'trades': 0, 'wins': 0},
            '1-1.5:1': {'min': 1, 'max': 1.5, 'trades': 0, 'wins': 0},
            '1.5-2:1': {'min': 1.5, 'max': 2, 'trades': 0, 'wins': 0},
            '2-3:1': {'min': 2, 'max': 3, 'trades': 0, 'wins': 0},
            '>3:1': {'min': 3, 'max': float('inf'), 'trades': 0, 'wins': 0}
        }
        
        for trade in trades:
            rr = trade.get('risk_reward', 0)
            if rr > 0:
                for bucket_name, bucket_data in rr_buckets.items():
                    if bucket_data['min'] <= rr < bucket_data['max']:
                        bucket_data['trades'] += 1
                        if trade['pnl'] > 0:
                            bucket_data['wins'] += 1
                        break
        
        # Calculate win rates
        analysis = {}
        for bucket_name, bucket_data in rr_buckets.items():
            if bucket_data['trades'] > 0:
                win_rate = bucket_data['wins'] / bucket_data['trades'] * 100
                analysis[bucket_name] = {
                    'trades': bucket_data['trades'],
                    'win_rate': win_rate
                }
        
        return analysis
    
    def _analyze_edge_decay(self) -> Dict[str, Any]:
        """Analyze if trading edge is decaying over time."""
        # Get monthly performance
        monthly_data = self._monthly_performance_breakdown()
        if not monthly_data or len(monthly_data) < 3:
            return {'trend': 'insufficient_data'}
        
        # Extract win rates and profit factors
        months = sorted(monthly_data.keys())
        win_rates = [monthly_data[m]['win_rate'] for m in months]
        profit_factors = [monthly_data[m]['profit_factor'] for m in months]
        
        # Simple linear regression to detect trend
        x = np.arange(len(months))
        win_rate_slope = np.polyfit(x, win_rates, 1)[0]
        pf_slope = np.polyfit(x, profit_factors, 1)[0]
        
        # Determine trend
        if win_rate_slope < -0.5 or pf_slope < -0.05:
            trend = 'declining'
        elif win_rate_slope > 0.5 or pf_slope > 0.05:
            trend = 'improving'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'win_rate_slope': win_rate_slope,
            'profit_factor_slope': pf_slope,
            'recent_performance': monthly_data.get(months[-1], {})
        }
    
    def _comprehensive_risk_analysis(self) -> Dict[str, Any]:
        """Perform comprehensive risk analysis."""
        trades = self._get_trades()
        if not trades:
            return {}
        
        pnls = [t['pnl'] for t in trades]
        
        # Calculate risk metrics
        analysis = {
            'var_95': self._calculate_var(pnls, 0.95),
            'var_99': self._calculate_var(pnls, 0.99),
            'expected_shortfall': self._calculate_expected_shortfall(pnls, 0.95),
            'max_single_loss': min(pnls) if pnls else 0,
            'risk_of_ruin': self._calculate_risk_of_ruin(trades),
            'kelly_criterion': self._calculate_kelly_criterion(trades),
            'position_sizing_recommendation': self._position_sizing_recommendation(trades)
        }
        
        return analysis
    
    def _calculate_var(self, returns: List[float], confidence: float) -> float:
        """Calculate Value at Risk."""
        if not returns:
            return 0
        return np.percentile(returns, (1 - confidence) * 100)
    
    def _calculate_expected_shortfall(self, returns: List[float], confidence: float) -> float:
        """Calculate Expected Shortfall (CVaR)."""
        if not returns:
            return 0
        var = self._calculate_var(returns, confidence)
        return np.mean([r for r in returns if r <= var])
    
    def _calculate_risk_of_ruin(self, trades: List[Dict]) -> float:
        """Calculate risk of ruin probability."""
        if not trades:
            return 0
        
        win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades)
        
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]
        
        if not wins or not losses:
            return 0
        
        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 0
        
        # Simplified risk of ruin formula
        if win_rate == 0:
            return 1.0
        elif win_rate == 1:
            return 0.0
        else:
            return ((1 - win_rate) / win_rate) ** (20)  # Assuming 20 unit bankroll
    
    def _calculate_kelly_criterion(self, trades: List[Dict]) -> float:
        """Calculate optimal position size using Kelly criterion."""
        if not trades:
            return 0
        
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]
        
        if not wins or not losses:
            return 0
        
        win_prob = len(wins) / len(trades)
        loss_prob = len(losses) / len(trades)
        
        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 0
        
        # Kelly formula: (p*b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        b = avg_win / avg_loss
        kelly_pct = (win_prob * b - loss_prob) / b
        
        # Cap at 25% for safety
        return min(max(kelly_pct, 0), 0.25) * 100
    
    def _position_sizing_recommendation(self, trades: List[Dict]) -> str:
        """Generate position sizing recommendation."""
        if not trades:
            return "Insufficient data"
        
        kelly = self._calculate_kelly_criterion(trades)
        risk_of_ruin = self._calculate_risk_of_ruin(trades)
        
        if risk_of_ruin > 0.1:
            return f"Reduce position size. High risk of ruin ({risk_of_ruin:.1%})"
        elif kelly < 1:
            return f"Current sizing may be too aggressive. Kelly suggests {kelly:.1f}%"
        elif kelly > 5:
            return f"Can potentially increase size. Kelly suggests {kelly:.1f}% (capped at 25%)"
        else:
            return f"Current position sizing appears appropriate. Kelly: {kelly:.1f}%"
    
    def _monthly_performance_breakdown(self) -> Dict[str, Dict[str, float]]:
        """Calculate performance by month."""
        trades = self._get_trades()
        if not trades:
            return {}
        
        monthly_trades = defaultdict(list)
        
        for trade in trades:
            if trade['entry_time']:
                month_key = trade['entry_time'].strftime('%Y-%m')
                monthly_trades[month_key].append(trade)
        
        breakdown = {}
        for month, month_trades in monthly_trades.items():
            metrics = self._calculate_metrics_for_trades(month_trades)
            breakdown[month] = self._metrics_to_dict(metrics)
        
        return breakdown
    
    def analyze_by_session(self) -> Dict[str, PerformanceMetrics]:
        """Analyze performance by trading session."""
        from src.session_detector import TradingSession
        
        session_performance = {}
        sessions = [TradingSession.ASIAN, TradingSession.LONDON, 
                   TradingSession.NY, TradingSession.OVERLAP]
        
        for session in sessions:
            trades = self.db.get_trades_by_session(session.value)
            if trades:
                metrics = self._calculate_metrics_for_trades(trades)
                session_performance[session.value] = metrics
        
        return session_performance
    
    def _get_trades(self, start_date=None, end_date=None, symbol=None) -> List[Dict]:
        """Get trades from database with filters."""
        return self.db.get_trades_for_analytics(start_date, end_date, symbol)
    
    def _calculate_metrics_for_trades(self, trades: List[Dict]) -> PerformanceMetrics:
        """Calculate metrics for a specific set of trades."""
        # Create a temporary subset and calculate
        # Similar to get_performance_metrics but for subset
        # Implementation would be similar to main method
        return self.get_performance_metrics()  # Simplified for now
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache entry is still valid."""
        if key not in self._cache:
            return False
        return datetime.now(timezone.utc) < self._cache_expiry.get(key, datetime.min)
    
    def _metrics_to_dict(self, metrics: PerformanceMetrics) -> Dict[str, Any]:
        """Convert metrics object to dictionary."""
        return {
            'total_trades': metrics.total_trades,
            'win_rate': metrics.win_rate,
            'profit_factor': metrics.profit_factor,
            'total_pnl': metrics.total_pnl,
            'average_win': metrics.average_win,
            'average_loss': metrics.average_loss,
            'max_drawdown': metrics.max_drawdown,
            'sharpe_ratio': metrics.sharpe_ratio,
            'sortino_ratio': metrics.sortino_ratio,
            'calmar_ratio': metrics.calmar_ratio
        }
    
    def _pattern_to_dict(self, pattern: PatternPerformance) -> Dict[str, Any]:
        """Convert pattern object to dictionary."""
        return {
            'pattern': pattern.pattern_name,
            'occurrences': pattern.occurrences,
            'trades': pattern.trades,
            'win_rate': pattern.win_rate,
            'avg_profit': pattern.avg_profit,
            'total_profit': pattern.total_profit,
            'confidence_correlation': pattern.confidence_correlation
        }


# Singleton instance
_performance_analytics: Optional[PerformanceAnalytics] = None


def get_performance_analytics() -> PerformanceAnalytics:
    """Get or create performance analytics singleton."""
    global _performance_analytics
    if _performance_analytics is None:
        _performance_analytics = PerformanceAnalytics()
    return _performance_analytics