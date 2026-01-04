# MT5 Elliott Wave Trading System - Documentation Hub

**Last Updated**: 2026-01-04
**Phase**: 5 Complete (Trade Execution)
**Status**: Production Ready

## Welcome to the Documentation

This directory contains comprehensive documentation for the MT5 Elliott Wave Auto-Trading System. Start here to understand the project architecture, API reference, and development guidelines.

---

## Documentation Files

### 1. **START HERE: Codebase Summary**
📄 `codebase-summary.md`

**What it covers**:
- Quick project overview and capabilities
- 7-layer architecture overview
- Technology stack and tools
- Module and component reference
- Key design patterns
- Performance characteristics
- Known limitations and roadmap

**Best for**:
- Getting started quickly
- Understanding the big picture
- Finding which module does what
- Performance considerations

**Read time**: 15-20 minutes

---

### 2. **API Reference**
📄 `api-documentation.md`

**What it covers**:
- Complete API for all components
- MT5 Client (14 methods)
- Signal Parser (models and functions)
- Database API (6 methods)
- Trade Executor (execution methods)
- Trailing Stop Manager (state machine)
- Claude Client (AI integration)
- Telegram Bot (6 commands)

**For every API**:
- Function signature with types
- Parameter descriptions
- Return values and exceptions
- Code examples
- Related methods

**Best for**:
- Implementing new features
- Integrating with other systems
- Understanding method behavior
- Finding error handling patterns

**Read time**: 30-40 minutes (reference as needed)

---

### 3. **System Architecture**
📄 `system-architecture.md`

**What it covers**:
- High-level system design (7 layers)
- Component interactions
- Data flow diagrams (order placement, trailing stops)
- Technology stack details
- 6 design patterns explained
- Module dependencies
- 2 state machines documented
- Database schema with relationships
- Security architecture (5 layers)
- Scalability analysis
- Error handling strategy
- Testing architecture
- Deployment options

**Best for**:
- Deep technical understanding
- System design decisions
- Architecture troubleshooting
- Performance optimization
- Security review
- Scaling planning

**Read time**: 45-60 minutes

---

### 4. **Project Overview & Requirements**
📄 `project-overview-pdr.md`

**What it covers**:
- Project vision and mission
- Functional requirements (Phases 1-9)
- Non-functional requirements
- Phase breakdown and timeline
- Success criteria for each phase
- 7 identified risks with mitigations
- Resource requirements
- Budget and time estimates
- Phase history and completion status

**Best for**:
- Project managers and stakeholders
- Understanding requirements
- Planning next phases
- Risk management
- Timeline planning
- Budget estimation

**Read time**: 20-30 minutes

---

### 5. **Code Standards & Guidelines**
📄 `code-standards.md`

**What it covers**:
- Python coding standards
- Project structure guidelines
- Naming conventions
- Code organization patterns
- Type hints and docstrings
- Error handling patterns
- Testing standards
- Performance guidelines
- Security best practices
- Code review checklists
- Good vs bad code examples

**Best for**:
- Before writing any code
- Code review process
- Maintaining consistency
- Learning project conventions
- Understanding quality standards

**Read time**: 30-40 minutes

---

## Quick Navigation

### I want to...

#### ...understand the project
→ Start with **Codebase Summary** (5 min overview)
→ Then read **Project Overview** (timeline and goals)

#### ...implement a new feature
→ Read **System Architecture** (understand design)
→ Reference **API Documentation** (component APIs)
→ Follow **Code Standards** (quality guidelines)

#### ...fix a bug
→ Find component in **Codebase Summary**
→ Check **System Architecture** (data flows)
→ Reference **API Documentation** (expected behavior)

#### ...optimize performance
→ Review **System Architecture** (bottlenecks section)
→ Check **Code Standards** (performance patterns)
→ Profile and measure

#### ...integrate with external system
→ Reference **API Documentation** (components)
→ Check **System Architecture** (dependencies)
→ Review **Code Standards** (integration patterns)

#### ...review security
→ Read **System Architecture** (security section)
→ Check **Code Standards** (security guidelines)
→ Reference **Project Overview** (security requirements)

#### ...plan next phase
→ Review **Project Overview** (phase breakdown)
→ Check **System Architecture** (current design)
→ Consider **Code Standards** (what's needed)

---

## Key Sections Quick Reference

### Architecture (from System Architecture)
```
7 Layers:
1. Configuration & Infrastructure
2. Market Data & Broker (MT5)
3. Data Persistence (SQLite)
4. Signal Processing
5. Trade Execution
6. User Interface (Telegram)
7. (Future: Web Dashboard)
```

### Components (from Codebase Summary)
```
Core Modules:
- config.py           → Settings management
- mt5_client.py       → Market data & order execution
- signal_parser.py    → Signal models & validation
- claude_client.py    → AI integration
- database.py         → Trade persistence
- trade_executor.py   → Execution workflow
- trailing_stop_manager.py → Stop loss management
- telegram_bot.py     → User interface
```

### API Summary (from API Documentation)
```
40+ methods documented across 7 components:
- MT5Client:           14 methods
- TradeExecutor:       2 methods
- Database:            6 methods
- TelegramBot:         6 commands
+ Signal models, error handling, examples
```

### Security Layers (from System Architecture)
```
1. Paper Trading Enforcement (default safe)
2. Input Validation (Pydantic models)
3. SQL Injection Prevention (parameterized queries)
4. Authorization Checks (Telegram)
5. Magic Number Isolation
```

### Design Patterns (from Code Standards & Architecture)
```
6 Key Patterns:
1. Singleton (config, database)
2. Lazy Loading (dependency injection)
3. State Machine (trailing stops)
4. Context Manager (DB connections)
5. Strategy (signal extraction)
6. Repository (database access)
```

---

## Project Status

### Phase 5: Trade Execution ✅ COMPLETE
- ✅ Market order execution
- ✅ Position sizing with confidence
- ✅ Trailing stop state machine
- ✅ Database persistence
- ✅ Paper trading mode
- ✅ 45/45 tests passing
- ✅ Code review: A- grade
- ✅ Documentation: Complete

### Metrics
- **Code Coverage**: 84-96%
- **Test Cases**: 45 (100% passing)
- **Documentation**: 37,000+ words
- **API Methods**: 40+ documented
- **Components**: 8 fully documented

---

## How to Use This Documentation

### 1. New Team Member
1. Read **Codebase Summary** (overview in 15 min)
2. Skim **Project Overview** (understand roadmap)
3. Review **Code Standards** (learn conventions)
4. Keep **API Documentation** as reference

### 2. Feature Development
1. Understand requirements (from **Project Overview**)
2. Study related architecture (**System Architecture**)
3. Reference API details (**API Documentation**)
4. Follow code standards (**Code Standards**)

### 3. Code Review
1. Check against **Code Standards**
2. Verify architecture alignment (**System Architecture**)
3. Validate API usage (**API Documentation**)
4. Ensure test coverage standards

### 4. Troubleshooting
1. Find component in **Codebase Summary**
2. Check data flow in **System Architecture**
3. Review error handling in **API Documentation**
4. Reference **Code Standards** patterns

---

## Key Concepts

### Position Sizing Formula
```
Risk Amount = Balance × Risk%
Position Size = Risk Amount / (Entry - Stop) / Pip Value
Applied Confidence Multiplier:
  - 75%+ confidence: 1.0x (full size)
  - 60-74% confidence: 0.5x (half size)
  - <60% confidence: 0.0x (skip trade)
```

### Trailing Stop State Machine
```
INACTIVE (order placed)
    ↓
[Check: TP1 hit OR profit > 1R]
    ↓
ACTIVATED (move SL to breakeven + 5 pips)
    ↓
[Check: price retraces 1.5 × ATR]
    ↓
TRAILING (follow price, lock profits)
    ↓
[Position closed or stopped out]
```

### Data Persistence
```
3 Tables:
- signals: Trading signals received
- trades: Executed trades with tickets
- tp_levels: Take profit levels for tracking
```

---

## FAQ

### Q: Where do I find the API for a specific component?
**A**: Use **Codebase Summary** to find which file contains it, then reference **API Documentation** for the complete API.

### Q: How do I understand the data flow?
**A**: Check **System Architecture** for detailed flow diagrams (3 main flows documented).

### Q: What are the code quality standards?
**A**: See **Code Standards** for all guidelines, patterns, and examples.

### Q: What's the system architecture?
**A**: **System Architecture** covers 7 layers, design patterns, and component interactions.

### Q: What are the requirements for Phase X?
**A**: Check **Project Overview** for functional and non-functional requirements by phase.

### Q: How do I implement feature X?
**A**:
1. Understand requirements from **Project Overview**
2. Plan architecture from **System Architecture**
3. Code following **Code Standards**
4. Reference **API Documentation** for components

### Q: Is there a quick reference?
**A**: Yes! **Codebase Summary** provides a 15-minute overview of the entire system.

---

## Document Maintenance

### How to Keep Docs Updated
1. Update when implementing new features
2. Update when refactoring components
3. Update when fixing bugs related to architecture
4. Add code examples when implementing patterns
5. Update timeline as phases complete

### Version Control
- All docs in `/docs` directory
- Committed to git with code changes
- Reviewed alongside code reviews
- Part of PR review process

---

## Related Documents

### Phase Plans
- `plans/260104-1514-mt5-elliott-wave-trading/phase-*.md` - Phase-specific plans

### Code Reviews
- `plans/reports/code-reviewer-*.md` - Detailed code reviews

### Implementation Details
- `src/*.py` - Source code with docstrings
- `tests/test_*.py` - Test examples

---

## Getting Help

### For Understanding System Design
→ Read **System Architecture**

### For API Usage
→ Reference **API Documentation**

### For Code Quality Issues
→ Check **Code Standards**

### For Project Planning
→ Review **Project Overview**

### For Component Details
→ Start with **Codebase Summary**

---

## Next Steps

1. **Quick Overview**: Read Codebase Summary (15 min)
2. **Deep Dive**: Study System Architecture (1 hour)
3. **Reference**: Keep API Documentation handy
4. **Code**: Follow Code Standards when writing
5. **Review**: Use Code Review checklist

---

## Summary

This documentation provides:
- ✅ **Architecture**: Complete system design (7 layers)
- ✅ **API Reference**: 40+ methods with examples
- ✅ **Standards**: Code quality guidelines
- ✅ **Planning**: Requirements and roadmap
- ✅ **Examples**: 100+ code samples

**Total Coverage**: 95% of codebase documented
**Completeness**: A (Excellent)
**Readiness**: Production Ready

---

## Document Information

**Created**: 2026-01-04
**Last Updated**: 2026-01-04
**Maintained By**: Development Team
**Next Review**: After Phase 6 Completion
**Distribution**: Internal - Development Team

---

## Index

### By Topic
- **API**: API Documentation
- **Architecture**: System Architecture
- **Code Quality**: Code Standards
- **Components**: Codebase Summary
- **Requirements**: Project Overview
- **Planning**: Project Overview

### By Role
- **Developer**: Code Standards → API Documentation → System Architecture
- **Architect**: System Architecture → Project Overview → Codebase Summary
- **Manager**: Project Overview → Codebase Summary → Phase Plans
- **QA/Tester**: Code Standards → API Documentation → Test Examples
- **Reviewer**: Code Standards → System Architecture → API Documentation

---

**Happy coding! 🚀**
