# Profiteer

Live stock data + social paper trading. Look up real quotes, charts, and news, and
paper-trade against a persisted portfolio.

**v1 (this milestone):** user accounts, live market data (unofficial Yahoo via `yfinance`),
and paper trading (buy/sell, positions, live P&L). Social features (following, competitions),
options, and AWS hosting are planned for later phases — the schema and provider abstraction
are laid so they slot in without a rewrite.

## Stack
- **Backend:** FastAPI (Python), SQLAlchemy + Alembic, JWT auth. SQLite for local dev,
  Postgres-ready via `DATABASE_URL`.
- **Frontend:** React + Vite + TypeScript + Tailwind CSS, Recharts for charts.
- **Market data:** `yfinance`, behind a swappable `MarketDataProvider` interface
  (`backend/app/services/market_data.py`) with short-lived TTL caching to avoid rate limits.

## Prerequisites
- Python 3.11+ (developed on 3.14)
- Node.js 18+ (developed on 24 LTS)

## Run the backend
```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

# (optional) copy env template and set a real SECRET_KEY
cp .env.example .env

# create/upgrade the schema (or let the app auto-create tables on first run)
.venv/Scripts/python.exe -m alembic upgrade head

.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```
API runs at http://127.0.0.1:8000 — interactive docs at http://127.0.0.1:8000/docs.

## Run the frontend
```bash
cd frontend
npm install
npm run dev
```
App runs at http://localhost:5173 (expects the backend at http://127.0.0.1:8000;
override with `VITE_API_URL` in `frontend/.env`).

## Verified happy path
Sign up → land on the dashboard ($100k paper cash) → search a symbol (e.g. `AAPL`) →
view live quote, price chart, and news → buy shares → see cash drop and the position appear
with live P&L → sell to close. Over-buying (beyond cash) and over-selling (beyond shares held)
are rejected with clear errors.

## Project layout
```
backend/   FastAPI app (app/), Alembic migrations (alembic/)
frontend/  Vite + React + TS app (src/)
```

## Notes & roadmap
- Market data uses an **unofficial** Yahoo source; it can break if Yahoo changes endpoints.
  Only `market_data.py` needs changing to swap in an official API (Finnhub, Alpha Vantage).
- No market-hours enforcement in v1: trades execute at the latest fetched price; the UI shows
  market status.
- **Next up:** watchlists, named portfolios, following/competitions + leaderboard, options,
  performance-over-time charts, and AWS deployment (RDS Postgres + containerized API).
