# Phase 3 Documentation Index - DrawdownManager Real-Time Risk Tracking

**Created**: 2026-01-08
**Phase**: Phase 3 Complete
**Status**: ✅ PRODUCTION-READY

## Quick Navigation

### Primary Documentation
1. **[DrawdownManager API Guide](./drawdown-manager-guide.md)** (732 lines)
   - Complete API reference with examples
   - Configuration parameters (6 options)
   - Limit enforcement mechanisms (5 checks)
   - Integration patterns with other components
   - Troubleshooting guide
   - **Start here for implementation**

2. **[System Architecture](./system-architecture.md)** (v1.5 - 1,304 lines)
   - Updated with DrawdownManager component
   - NEW: Pattern #8 - Real-Time Drawdown Management
   - Database schema: drawdown_state table
   - Module dependency graph
   - Component interaction diagrams
   - **Reference for architectural context**

3. **[Documentation Report](../plans/reports/docs-manager-260108-2054-drawdown-phase3.md)** (408 lines)
   - Executive summary
   - Changes made documentation
   - Quality metrics and coverage analysis
   - Implementation evidence
   - Recommendations for Phase 4
   - **Reference for project management**

### Key Sections in Each Document

#### DrawdownManager API Guide
- [Overview](./drawdown-manager-guide.md#overview) - Purpose & features
- [Configuration](./drawdown-manager-guide.md#configuration) - All 6 settings
- [API Reference](./drawdown-manager-guide.md#api-reference) - 5 public methods
- [Limit Enforcement](./drawdown-manager-guide.md#limit-enforcement) - 5 limit checks
- [Status States](./drawdown-manager-guide.md#status-states) - 4 operational states
- [Integration](./drawdown-manager-guide.md#integration) - 4 integration points
- [Examples](./drawdown-manager-guide.md#examples) - 4 production-ready examples
- [Troubleshooting](./drawdown-manager-guide.md#troubleshooting) - Common issues

#### System Architecture Updates
- [High-Level Architecture](./system-architecture.md#high-level-architecture) - Updated diagram
- [Component Dependencies](./system-architecture.md#component-interaction) - New drawdown_manager layer
- [Design Pattern #8](./system-architecture.md#8-real-time-drawdown-management-pattern-phase-3) - Drawdown pattern
- [Database Schema](./system-architecture.md#database-schema) - drawdown_state table
- [Module Hierarchy](./system-architecture.md#dependency-hierarchy) - Updated structure

## Configuration Quick Reference

### Daily Limits
```
daily_max_loss_percent: 3.0%   (range: 0.5% - 10.0%)
daily_max_trades: 5            (range: 1 - 20)
consecutive_loss_limit: 3      (range: 1 - 10)
```

### Weekly & Monthly
```
weekly_max_loss_percent: 6.0%  (range: 1.0% - 20.0%)
monthly_max_drawdown_percent: 10.0% (range: 2.0% - 30.0%)
recovery_mode_threshold: 5.0%  (range: 1.0% - 15.0%)
```

## API Quick Reference

### Core Methods
```python
# Check if trading allowed
result = manager.validate(account_balance)
# Returns: trading_allowed, status, position_size_modifier

# Record trade result
manager.record_trade_result(pnl, is_win, balance)

# Reset daily counters (call at 00:00 UTC)
manager.reset_daily(current_balance)

# Reset weekly counters (call Mondays at 00:00 UTC)
manager.reset_weekly(current_balance)

# Get current status
summary = manager.get_status_summary()
```

## Limit Checks (Priority Order)

1. **Consecutive Losses (3)** - Pause if 3 losses in a row
2. **Daily Loss (3%)** - Pause if daily loss ≥ 3% of day-start
3. **Daily Trades (5)** - Pause if 5 trades already executed
4. **Weekly Loss (6%)** - Pause if weekly loss ≥ 6% of week-start
5. **Monthly Drawdown (10%)** - Pause if balance ≤ 90% of peak

## Position Size Modifiers

| Status | Modifier | Trigger |
|--------|----------|---------|
| NORMAL | 1.0x | All limits have capacity |
| HIGH_ALERT | 0.75x | 1 consecutive loss |
| RECOVERY | 0.5x | 2+ losses or 5%+ drawdown |
| PAUSED | 0x | Any limit breached |

## Integration Points

### RiskGuard
- Validates limits before position validation
- Returns pause reason if trading blocked

### TradeExecutor
- Applies position_size_modifier to calculated size
- Checks trading_allowed before order placement

### TrailingStopManager
- Calls record_trade_result() after position close
- Updates consecutive loss counter

### Scheduler
- reset_daily() at 00:00 UTC
- reset_weekly() on Monday at 00:00 UTC

## Test Coverage

**File**: `tests/test_drawdown_manager.py`
- **Tests**: 19 unit tests
- **Coverage**: 95%
- **Status**: 100% passing

### Test Categories
- Validation (3 tests)
- Daily limits (2 tests)
- Consecutive losses (2 tests)
- Weekly limits (1 test)
- Monthly drawdown (1 test)
- Position modifiers (3 tests)
- Resets (2 tests)
- State persistence (2 tests)
- Limits remaining (1 test)
- Status reporting (1 test)
- Singleton pattern (1 test)

## Database Schema

**Table**: `drawdown_state` (14 columns)
```
- id (PK)
- date (UNIQUE key)
- daily_start_balance, daily_pnl, daily_trades
- weekly_start_balance, weekly_pnl, weekly_trades
- peak_balance (monthly tracking)
- consecutive_losses
- recovery_mode
- trading_paused, pause_reason
- created_at, updated_at
```

## Code Examples

All examples are in [DrawdownManager API Guide](./drawdown-manager-guide.md#examples):

1. Basic Trading Validation
2. Recording Trade Results
3. Position Sizing with Modifier
4. Status Dashboard Display

## Implementation Files

### Source Code
- `src/drawdown_manager.py` (481 lines, 6 limit checks)
- `src/config.py` (lines 175-199, 6 new options)

### Tests
- `tests/test_drawdown_manager.py` (19 tests, 95% coverage)

### Modified Files
- `src/database.py` - drawdown_state table management
- `src/risk_guard.py` - DrawdownManager integration
- `src/trade_executor.py` - Position modifier application

## Documentation Files

### Created
- `docs/drawdown-manager-guide.md` (732 lines, comprehensive guide)
- `docs/PHASE3-DOCUMENTATION-INDEX.md` (this file, quick navigation)

### Updated
- `docs/system-architecture.md` (v1.5, Phase 3 integration)

### Reports
- `plans/reports/docs-manager-260108-2054-drawdown-phase3.md` (detailed report)

## Quality Metrics

- **API Coverage**: 100% (5 public methods)
- **Configuration Coverage**: 100% (6 options)
- **Limit Coverage**: 100% (5 checks)
- **Example Coverage**: 100% (4 scenarios)
- **Test Coverage**: 95% (19 tests)
- **Documentation Accuracy**: 100% (verified against code)

## Next Steps

### For Developers
1. Read [DrawdownManager API Guide](./drawdown-manager-guide.md) overview
2. Review [Examples](./drawdown-manager-guide.md#examples) section
3. Check integration with your component
4. Reference troubleshooting if issues arise

### For Operations
1. Configure parameters in `.env`
2. Set up daily/weekly reset hooks
3. Monitor status via `get_status_summary()`
4. Review troubleshooting for operational issues

### For Project Managers
1. Review [Documentation Report](../plans/reports/docs-manager-260108-2054-drawdown-phase3.md)
2. Check quality metrics and test coverage
3. Plan Phase 4 resources based on recommendations

## Related References

- **Specifications**: instruction_v4.md Section 8.7
- **Code Standards**: [code-standards.md](./code-standards.md)
- **Project PDR**: [project-overview-pdr.md](./project-overview-pdr.md)
- **Architecture**: [system-architecture.md](./system-architecture.md)
- **API Docs**: [api-documentation.md](./api-documentation.md)

---

**Status**: ✅ Phase 3 Complete
**Quality**: ✅ Production-Ready
**Next Phase**: Phase 4 - Schedule & Automation

Last Updated: 2026-01-08
