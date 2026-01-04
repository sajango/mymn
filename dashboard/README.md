# MT5 Trading Dashboard

Web dashboard for visualizing trading performance and analytics.

## Quick Start

### Development Mode

```bash
# Start backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Production Mode (Docker)

```bash
cd dashboard
docker-compose up -d --build
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000

### Commands

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

## Features

- **Stats Cards**: Total P&L, win rate, trade count, profit factor
- **Equity Curve**: Cumulative P&L line chart
- **Daily P&L**: Bar chart of daily performance
- **Confidence Analysis**: Signal confidence vs trade outcome
- **Time Heatmap**: Performance by hour and day of week
- **Open Positions**: Current active trades
- **Trade History**: Paginated trade table with filters

## Architecture

```
Trading Bot (main.py)
        │
        ▼
  SQLite (data/trading.db)
        │ (read-only)
        ▼
┌─────────────────────────┐
│    Dashboard API        │
│    (FastAPI :8000)      │
│    - /api/stats         │
│    - /api/trades        │
│    - /api/equity        │
│    - /api/positions     │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│    React Frontend       │
│    (Vite :3000)         │
│    - Recharts           │
│    - TailwindCSS        │
│    - React Query        │
└─────────────────────────┘
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/stats` | Overall performance statistics |
| `/api/trades` | Trade history with pagination |
| `/api/trades/{id}` | Single trade with events |
| `/api/signals` | Signal history |
| `/api/positions` | Current open positions |
| `/api/equity` | Equity curve data |
| `/api/daily-pnl` | Daily P&L summary |
| `/api/confidence-analysis` | Confidence vs outcome |
| `/api/time-analysis` | Performance by time |
| `/api/skipped-signals` | Skipped signal summary |
| `/api/weekly-summary` | Week-over-week stats |
| `/api/health` | Health check |
