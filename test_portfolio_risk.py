"""Test portfolio risk management system."""

from src.portfolio_risk_manager import PortfolioRiskManager, get_portfolio_risk_manager
from datetime import datetime, timezone, timedelta
import json


def test_portfolio_heat():
    """Test portfolio heat calculation."""
    print("=== Testing Portfolio Heat Calculation ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Get current heat
    heat = manager.calculate_portfolio_heat()
    
    print("Portfolio Heat Analysis:")
    print(f"Total Exposure: ${heat.total_exposure}")
    print(f"Heat Percentage: {heat.heat_percentage:.2f}%")
    print(f"Position Count: {heat.position_count}")
    print(f"Average Risk: ${heat.avg_position_risk:.2f}")
    print(f"Max Single Risk: ${heat.max_position_risk:.2f}")
    print(f"Correlation Risk: {heat.correlated_risk:.2f}%")
    print(f"Risk Status: {heat.risk_status}")
    
    # Show thresholds
    print(f"\nThresholds:")
    print(f"Warning at: {manager.warning_heat * 100:.0f}%")
    print(f"Max allowed: {manager.max_portfolio_heat * 100:.0f}%")


def test_position_allowed():
    """Test if new positions are allowed."""
    print("\n\n=== Testing Position Allowance ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Test scenarios
    test_cases = [
        ('XAUUSD', 100, "Small gold position"),
        ('XAUUSD', 500, "Large gold position"),
        ('XAUEUR', 200, "Correlated gold position"),
        ('EURUSD', 150, "Uncorrelated forex position")
    ]
    
    for symbol, risk, desc in test_cases:
        allowed, reason = manager.check_position_allowed(symbol, risk)
        print(f"\n{desc}:")
        print(f"Symbol: {symbol}, Risk: ${risk}")
        print(f"Allowed: {'YES' if allowed else 'NO'}")
        print(f"Reason: {reason}")


def test_dynamic_risk_adjustment():
    """Test dynamic risk calculation based on performance."""
    print("\n\n=== Testing Dynamic Risk Adjustment ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Calculate dynamic risk
    adjustment = manager.calculate_dynamic_risk()
    
    print("Dynamic Risk Adjustment:")
    print(f"Current Risk: {adjustment.current_risk_percent}%")
    print(f"Recommended Risk: {adjustment.recommended_risk_percent}%")
    print(f"Adjustment Factor: {adjustment.adjustment_factor}x")
    print(f"Reason: {adjustment.reason}")
    print(f"Confidence: {adjustment.confidence}%")
    
    # Show impact on position sizes
    base_lots = 0.10
    adjusted_lots = base_lots * adjustment.adjustment_factor
    print(f"\nPosition Size Impact:")
    print(f"Base Size: {base_lots} lots")
    print(f"Adjusted Size: {adjusted_lots:.2f} lots")


def test_correlation_risk():
    """Test correlation risk calculations."""
    print("\n\n=== Testing Correlation Risk ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Show correlation matrix
    print("Correlation Matrix:")
    for pair, corr in manager.correlation_matrix.items():
        print(f"{pair[0]}/{pair[1]}: {corr:+.2f}")
    
    # Test correlation impact on positions
    print("\n\nCorrelation Scenarios:")
    
    # Mock position data for testing
    positions = {
        'XAUUSD': [{'risk': 200}],
        'XAUEUR': [{'risk': 150}]
    }
    
    corr_risk = manager._calculate_correlation_risk(positions, 10000)
    print(f"XAUUSD + XAUEUR correlation risk: {corr_risk:.2f}%")
    
    # Add uncorrelated position
    positions['EURUSD'] = [{'risk': 100}]
    corr_risk2 = manager._calculate_correlation_risk(positions, 10000)
    print(f"Adding EURUSD, total correlation risk: {corr_risk2:.2f}%")


def test_trading_pause_conditions():
    """Test when trading should be paused."""
    print("\n\n=== Testing Trading Pause Conditions ===\n")
    
    manager = get_portfolio_risk_manager()
    
    should_pause, reason = manager.should_pause_trading()
    
    print(f"Should Pause Trading: {'YES' if should_pause else 'NO'}")
    print(f"Reason: {reason}")
    
    # Check specific conditions
    print("\nPause Triggers:")
    print(f"- Portfolio heat > {manager.max_portfolio_heat * 100:.0f}%")
    print(f"- Consecutive losses > {manager.max_consecutive_losses}")
    print(f"- Daily loss > 3%")


def test_position_size_recommendation():
    """Test position size recommendations."""
    print("\n\n=== Testing Position Size Recommendations ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Test for different stop loss distances
    test_scenarios = [
        ('XAUUSD', 10, "Tight stop (10 pips)"),
        ('XAUUSD', 20, "Normal stop (20 pips)"),
        ('XAUUSD', 30, "Wide stop (30 pips)"),
        ('XAUUSD', 50, "Very wide stop (50 pips)")
    ]
    
    for symbol, sl_pips, desc in test_scenarios:
        recommendation = manager.get_position_size_recommendation(symbol, sl_pips)
        
        print(f"\n{desc}:")
        print(f"Recommended: {recommendation['recommended_lots']} lots")
        print(f"Maximum: {recommendation['max_lots']} lots")
        print(f"Risk %: {recommendation['risk_percent']}%")
        print(f"Adjustment: {recommendation['adjustment_factor']}x")
        
        if recommendation.get('warnings'):
            print("Warnings:")
            for warning in recommendation['warnings']:
                print(f"  - {warning}")


def test_comprehensive_risk_report():
    """Test comprehensive risk report generation."""
    print("\n\n=== Testing Comprehensive Risk Report ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Generate full report
    report = manager.get_risk_report()
    
    print("Risk Report Summary:")
    print("-" * 50)
    
    # Portfolio Heat
    heat = report['portfolio_heat']
    print(f"\nPortfolio Heat: {heat['heat_percentage']:.1f}% ({heat['status']})")
    print(f"Positions: {heat['position_count']}")
    print(f"Correlation Risk: +{heat['correlated_risk']:.1f}%")
    
    # Risk Adjustment
    adj = report['risk_adjustment']
    print(f"\nRisk Adjustment:")
    print(f"Current: {adj['current_risk']}% -> Recommended: {adj['recommended_risk']}%")
    print(f"Factor: {adj['adjustment_factor']}x")
    
    # Trading Status
    status = report['trading_status']
    print(f"\nTrading Status: {'PAUSED' if status['paused'] else 'ACTIVE'}")
    if status['paused']:
        print(f"Reason: {status['reason']}")
    
    # Correlations
    if report.get('correlations'):
        print(f"\nCorrelation Risks: {len(report['correlations'])} pairs")
        for corr in report['correlations'][:2]:
            print(f"  {corr['pair']}: {corr['correlation']:.0%} ({corr['risk']})")
    
    # Recommendations
    if report.get('recommendations'):
        print(f"\nRecommendations:")
        for rec in report['recommendations']:
            print(f"  {rec}")
    
    # Export as JSON for inspection
    print("\n\nFull Report JSON:")
    print(json.dumps(report, indent=2, default=str))


def test_consecutive_loss_tracking():
    """Test consecutive loss detection."""
    print("\n\n=== Testing Consecutive Loss Tracking ===\n")
    
    manager = get_portfolio_risk_manager()
    
    # Mock trade data
    test_trades = [
        {'profit': 100, 'close_time': '2024-01-01T10:00:00Z'},
        {'profit': -50, 'close_time': '2024-01-01T11:00:00Z'},
        {'profit': -75, 'close_time': '2024-01-01T12:00:00Z'},
        {'profit': -60, 'close_time': '2024-01-01T13:00:00Z'},
        {'profit': 80, 'close_time': '2024-01-01T14:00:00Z'},
        {'profit': -40, 'close_time': '2024-01-01T15:00:00Z'},
    ]
    
    # Count consecutive losses
    consecutive = manager._count_consecutive_losses(test_trades)
    print(f"Consecutive losses from end: {consecutive}")
    
    # Test with all losses
    all_losses = [{'profit': -50, 'close_time': f'2024-01-01T{i:02d}:00:00Z'} 
                  for i in range(5)]
    consecutive2 = manager._count_consecutive_losses(all_losses)
    print(f"All losses scenario: {consecutive2} consecutive losses")
    
    # Test with all wins
    all_wins = [{'profit': 50, 'close_time': f'2024-01-01T{i:02d}:00:00Z'} 
                for i in range(5)]
    consecutive3 = manager._count_consecutive_losses(all_wins)
    print(f"All wins scenario: {consecutive3} consecutive losses")


if __name__ == "__main__":
    test_portfolio_heat()
    test_position_allowed()
    test_dynamic_risk_adjustment()
    test_correlation_risk()
    test_trading_pause_conditions()
    test_position_size_recommendation()
    test_comprehensive_risk_report()
    test_consecutive_loss_tracking()
    
    print("\n\nAll portfolio risk tests completed!")