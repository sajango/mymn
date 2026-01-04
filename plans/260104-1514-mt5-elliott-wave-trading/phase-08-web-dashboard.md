# Phase 8: Web Dashboard

## Context Links
- [Plan Overview](./plan.md)
- [Phase 7: Testing](./phase-07-testing.md)

## Overview
- **Priority**: P2
- **Status**: Pending
- **Effort**: 6h
- **Description**: Full analytics web dashboard using FastAPI + React (separate process)

## Key Insights
- Separate process from trading bot for stability
- Read-only access to SQLite database
- React frontend with Recharts for visualizations
- FastAPI backend provides REST endpoints
- No authentication needed (local use only)
- **Docker Compose for deployment** (API + Web in containers)

## Requirements

### Functional
- Equity curve chart (cumulative P&L over time)
- Daily/weekly/monthly P&L bar charts
- Win rate and trade statistics
- Signal confidence vs outcome analysis
- Best/worst trading times heatmap
- Recent trades table with filters
- Open positions status

### Non-Functional
- Responsive design (desktop + mobile)
- Auto-refresh every 30 seconds
- SQLite read-only connection
- Runs on localhost:3000 (React) + localhost:8000 (API)

## Architecture

### System Overview
```
┌─────────────────────────────────────────────────────────────┐
│                     Trading Bot Process                     │
│  (main.py - APScheduler, Telegram, MT5, Claude CLI)        │
│                           │                                 │
│                           ▼                                 │
│                    SQLite Database                          │
│                    (data/trading.db)                        │
└───────────────────────────┬─────────────────────────────────┘
                            │ (read-only)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Dashboard Process                         │
│  ┌──────────────┐         ┌──────────────────────────────┐ │
│  │   FastAPI    │◄───────►│         React App            │ │
│  │  (port 8000) │  REST   │       (port 3000)            │ │
│  │              │         │  - Recharts                  │ │
│  │  /api/stats  │         │  - TailwindCSS               │ │
│  │  /api/trades │         │  - React Query               │ │
│  │  /api/equity │         │                              │ │
│  └──────────────┘         └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | Overall performance stats |
| `/api/trades` | GET | Trade history with pagination |
| `/api/signals` | GET | Signal history with outcomes |
| `/api/equity` | GET | Equity curve data points |
| `/api/daily-pnl` | GET | Daily P&L summary |
| `/api/positions` | GET | Current open positions |
| `/api/confidence-analysis` | GET | Confidence vs outcome correlation |
| `/api/time-analysis` | GET | Performance by hour/day |

## Project Structure

```
dashboard/
  backend/
    main.py           # FastAPI app entry
    routes/
      stats.py        # Stats endpoints
      trades.py       # Trade history
      analytics.py    # Charts data
    services/
      database.py     # SQLite read-only connection
      analytics.py    # Calculation logic
    Dockerfile        # Backend container
    requirements.txt  # FastAPI dependencies
  frontend/
    src/
      components/
        EquityCurve.tsx
        DailyPnLChart.tsx
        TradesTable.tsx
        StatsCards.tsx
        ConfidenceChart.tsx
        TimeHeatmap.tsx
      pages/
        Dashboard.tsx
      hooks/
        useStats.ts
        useTrades.ts
      App.tsx
    package.json
    tailwind.config.js
    Dockerfile        # Frontend container
    nginx.conf        # Production nginx config
  docker-compose.yml  # Orchestrate both services
  .env.example        # Environment template
```

## Implementation Steps

### 1. Backend Setup (FastAPI)

```python
# dashboard/backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from pathlib import Path

app = FastAPI(title="Trading Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trading.db"

def get_db():
    """Read-only connection to trading database"""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/stats")
def get_stats():
    conn = get_db()

    # Total trades
    total = conn.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed'").fetchone()[0]

    # Win rate
    wins = conn.execute("SELECT COUNT(*) FROM trades WHERE profit > 0 AND status = 'closed'").fetchone()[0]
    win_rate = (wins / total * 100) if total > 0 else 0

    # Total P&L
    total_pnl = conn.execute("SELECT COALESCE(SUM(profit), 0) FROM trades").fetchone()[0]

    # Max drawdown (simplified)
    # ... calculation

    conn.close()

    return {
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "wins": wins,
        "losses": total - wins,
    }

@app.get("/api/equity")
def get_equity_curve():
    conn = get_db()
    rows = conn.execute("""
        SELECT close_time, profit,
               SUM(profit) OVER (ORDER BY close_time) as cumulative
        FROM trades
        WHERE status = 'closed'
        ORDER BY close_time
    """).fetchall()
    conn.close()

    return [{"time": r["close_time"], "equity": r["cumulative"]} for r in rows]

@app.get("/api/trades")
def get_trades(limit: int = 50, offset: int = 0):
    conn = get_db()
    rows = conn.execute("""
        SELECT t.*, s.confidence, s.action as signal_action
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        ORDER BY t.open_time DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()

    return [dict(r) for r in rows]

@app.get("/api/confidence-analysis")
def get_confidence_analysis():
    """Analyze signal confidence vs actual outcome"""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            CASE
                WHEN s.confidence >= 75 THEN 'High (75-100)'
                WHEN s.confidence >= 60 THEN 'Medium (60-74)'
                ELSE 'Low (45-59)'
            END as confidence_band,
            COUNT(*) as total,
            SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) as wins,
            AVG(t.profit) as avg_profit
        FROM trades t
        JOIN signals s ON t.signal_id = s.id
        WHERE t.status = 'closed'
        GROUP BY confidence_band
    """).fetchall()
    conn.close()

    return [dict(r) for r in rows]
```

### 2. Frontend Setup (React + Vite)

```bash
cd dashboard/frontend
npm create vite@latest . -- --template react-ts
npm install recharts @tanstack/react-query axios tailwindcss
npx tailwindcss init
```

```tsx
// dashboard/frontend/src/components/StatsCards.tsx
interface Stats {
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  wins: number;
  losses: number;
}

export function StatsCards({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-4 gap-4">
      <Card title="Total P&L" value={`$${stats.total_pnl}`}
            color={stats.total_pnl >= 0 ? 'green' : 'red'} />
      <Card title="Win Rate" value={`${stats.win_rate}%`} />
      <Card title="Total Trades" value={stats.total_trades} />
      <Card title="W/L" value={`${stats.wins}/${stats.losses}`} />
    </div>
  );
}
```

```tsx
// dashboard/frontend/src/components/EquityCurve.tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export function EquityCurve({ data }) {
  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <h3 className="text-lg font-semibold mb-4">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <XAxis dataKey="time" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="equity" stroke="#10b981" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### 3. Docker Configuration

#### Backend Dockerfile

```dockerfile
# dashboard/backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Database will be mounted as volume
ENV DB_PATH=/data/trading.db

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Frontend Dockerfile (Multi-stage build)

```dockerfile
# dashboard/frontend/Dockerfile

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

#### Nginx Config

```nginx
# dashboard/frontend/nginx.conf
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # React SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to backend
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Docker Compose

```yaml
# dashboard/docker-compose.yml
version: '3.8'

services:
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: trading-api
    volumes:
      # Mount SQLite database (read-only)
      - ../data:/data:ro
    environment:
      - DB_PATH=/data/trading.db
    ports:
      - "8000:8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/stats"]
      interval: 30s
      timeout: 10s
      retries: 3

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: trading-web
    ports:
      - "3000:80"
    depends_on:
      - api
    restart: unless-stopped

networks:
  default:
    name: trading-dashboard
```

#### Environment Template

```bash
# dashboard/.env.example
# API Configuration
API_PORT=8000
WEB_PORT=3000

# Database path (relative to project root)
DB_PATH=../data/trading.db
```

### 4. Usage Commands

```bash
# Build and start containers
cd dashboard
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Access dashboard
# → http://localhost:3000
```

## Dependencies

### Backend (requirements.txt)
```
fastapi>=0.104.0
uvicorn>=0.24.0
```

### Frontend (package.json additions)
```json
{
  "dependencies": {
    "recharts": "^2.10.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "tailwindcss": "^3.4.0"
  }
}
```

### Docker Requirements
- Docker Desktop (Windows) or Docker Engine (Linux)
- Docker Compose v2.0+

## Todo List

- [ ] Create dashboard/ directory structure
- [ ] Setup FastAPI backend with routes
- [ ] Implement database service (read-only)
- [ ] Create stats/trades/equity endpoints
- [ ] Setup React + Vite frontend
- [ ] Implement StatsCards component
- [ ] Implement EquityCurve chart
- [ ] Implement DailyPnLChart
- [ ] Implement TradesTable with pagination
- [ ] Implement ConfidenceAnalysis chart
- [ ] Implement TimeHeatmap component
- [ ] Add auto-refresh (30s polling)
- [ ] Create Backend Dockerfile
- [ ] Create Frontend Dockerfile (multi-stage)
- [ ] Create nginx.conf for React SPA
- [ ] Create docker-compose.yml
- [ ] Test with docker-compose up
- [ ] Test with sample data

## Success Criteria

- [ ] `docker-compose up -d` starts both containers
- [ ] Dashboard loads at localhost:3000
- [ ] API responds at localhost:8000/api/stats
- [ ] All charts render correctly
- [ ] Auto-refresh updates data
- [ ] Trades table shows history with filters
- [ ] Responsive on mobile devices
- [ ] Containers restart automatically on failure
- [ ] No impact on trading bot performance

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Database lock contention | Low | Medium | Read-only mode, WAL enabled |
| Memory usage | Low | Low | Pagination, data limits |
| Port conflicts | Low | Low | Configurable ports |

## Security Considerations

- Local access only (localhost)
- Read-only database connection
- No authentication (single user)
- CORS restricted to localhost:3000

## Next Steps

After Phase 8:
- Optional: Add export to CSV/PDF
- Optional: Add comparison with benchmark
- Optional: Add Traefik for HTTPS (if remote access needed)
