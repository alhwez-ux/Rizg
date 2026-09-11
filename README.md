# Rizg Liquidity Tracker

Production-ready FastAPI backend for ingesting top-of-book quotes, computing liquidity metrics, and streaming updates over WebSockets.

## Features

- Modular layout: routers, core config/database, services, and Pydantic v2 models
- REST endpoints for quote ingestion, snapshots, and rolling liquidity statistics
- WebSocket fan-out for real-time liquidity updates
- Request-ID logging and consistent JSON error responses

## Project structure

```
app/
  main.py              # application factory and lifespan
  core/
    config.py          # environment-backed settings
    database.py        # in-memory market data store
    logging.py         # logging configuration
    middleware.py      # request context and error handlers
    exceptions.py      # domain errors
  models/              # Pydantic v2 schemas and quote model
  routers/             # HTTP and WebSocket routes
  services/            # liquidity math, ingestion, broadcasting
```

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer (for the dashboard)

## Run locally

Start the API from the project root (`Rizg`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is then available at:

- App: http://127.0.0.1:8000
- OpenAPI docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

In a second terminal, start the dashboard:

```powershell
cd web
npm install
npm run dev
```

Open http://127.0.0.1:3000. The dashboard shows a liquidity radar, a personal watchlist, entry/exit badges with suggested prices, and a live tape for the selected symbol.

Copy `web/.env.example` to `web/.env.local` for local API URLs.

## Deploy on Vercel (frontend)

Vercel hosts the Next.js app in `web/`. The FastAPI backend (quotes, screener, WebSocket) must run separately (Render, Railway, Fly.io, or a VPS) because it is a long-lived process with WebSockets.

1. Deploy the API first, for example:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set `SAHMK_API_KEY`, `CORS_ORIGINS` to your Vercel URL (or `["*"]`), and `ENABLE_MOCK_FEED=false` in production.

2. In Vercel, import this Git repo.
3. Set **Root Directory** to `web`.
4. Add environment variables:

| Variable | Example |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://your-api.example.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://your-api.example.com` |
| `API_PROXY_URL` | `https://your-api.example.com` (optional same-origin REST rewrite) |

5. Deploy. Open the Vercel URL and confirm the radar loads.

## Quick start

## Quick start

Ingest a quote:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/quotes -H "Content-Type: application/json" -d "{\"symbol\":\"AAPL\",\"bid\":189.12,\"ask\":189.18,\"bid_size\":1200,\"ask_size\":800,\"last_price\":189.15,\"volume\":1250000}"
```

Read the latest liquidity snapshot:

```powershell
curl http://127.0.0.1:8000/api/v1/liquidity/AAPL
```

Stream net flow and buy/sell volume for one ticker. With `SAHMK_API_KEY` set, the API polls delayed Tadawul quotes for `4030` (Al-Bahri, ~15 minutes behind on Starter) and classifies volume increases through `LiquidityEngine`. After upgrading SAHMK, set `SAHMK_DATA_MODE=realtime`. Mock tape is used only when no SAHMK key is configured and `ENABLE_MOCK_FEED=true`:

```powershell
websockets ws://127.0.0.1:8000/ws/liquidity/AAPL
```

Each message includes `net_flow`, `inflow`, `outflow`, `buy_volume`, and `sell_volume`. Send `ping` to keep the socket alive.

The multi-symbol endpoint still accepts a subscribe list:

```powershell
websockets ws://127.0.0.1:8000/ws/liquidity?symbols=AAPL,MSFT
```

```json
{"action": "subscribe", "symbols": ["AAPL", "MSFT"]}
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `Rizg Liquidity Tracker` | Service name returned by `/health` |
| `ENVIRONMENT` | `development` | Runtime environment label |
| `DEBUG` | `false` | Reserved debug flag |
| `LOG_LEVEL` | `INFO` | Root log level |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address used by process managers |
| `CORS_ORIGINS` | `["*"]` | Allowed browser origins |
| `QUOTE_HISTORY_LIMIT` | `1000` | Per-symbol in-memory history size |
| `WS_HEARTBEAT_SECONDS` | `20` | WebSocket ping interval |
| `ENABLE_MOCK_FEED` | `true` | Generate mock ticks only when no `SAHMK_API_KEY` is set |
| `MOCK_FEED_INTERVAL_SECONDS` | `0.5` | Delay between simulated trades |
| `MOCK_FEED_SYMBOLS` | `AAPL,MSFT,TSLA,NVDA,4030` | Tickers included in the mock tape |
| `SAHMK_API_KEY` | empty | SAHMK API key (keep in `.env` only) |
| `SAHMK_DATA_MODE` | `delayed` | `delayed` (~15 min Starter) or `realtime` after upgrading |
| `SAHMK_POLL_SECONDS` | `30` | How often to refresh the delayed quote for 4030 |
| `SAHMK_SYMBOLS` | `["4030"]` | Symbols polled from SAHMK (Al-Bahri) |
| `ALERT_WINDOW_SECONDS` | `60` | Rolling window used to detect liquidity spikes |
| `ALERT_INFLOW_THRESHOLD` | `25000` | Inflow (SAR) that triggers an accumulation alert |
| `ALERT_NET_FLOW_THRESHOLD` | `15000` | Absolute net flow (SAR) that triggers accumulation or distribution |
| `TELEGRAM_BOT_TOKEN` | empty | Bot token from BotFather (keep in `.env` only) |
| `TELEGRAM_CHAT_ID` | empty | Numeric Telegram chat id that should receive interval reports |
| `TELEGRAM_REPORT_INTERVAL_MINUTES` | `30` | How often to send one aggregated Telegram summary (15 / 30 / 60) |
| `TELEGRAM_REPORT_SYMBOLS` | `["4030"]` | Tickers included in the periodic Telegram report |

## API overview

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness check |
| `POST` | `/api/v1/quotes` | Ingest a top-of-book quote |
| `GET` | `/api/v1/quotes/symbols` | List tracked symbols |
| `GET` | `/api/v1/quotes/{symbol}` | Latest quote |
| `GET` | `/api/v1/quotes/{symbol}/history` | Recent quotes |
| `GET` | `/api/v1/liquidity/{symbol}` | Current spread, depth, and related metrics |
| `GET` | `/api/v1/liquidity/{symbol}/stats` | Rolling-window stats (Pandas) |
| `GET` | `/api/v1/screener` | Watchlist + radar snapshot with entry/exit prices |
| `GET` | `/api/v1/watchlist` | Custom TASI watchlist |
| `POST` | `/api/v1/watchlist` | Add a 4-digit symbol |
| `DELETE` | `/api/v1/watchlist/{symbol}` | Remove a symbol |
| `WS` | `/ws/liquidity/{symbol}` | Real-time net flow and buy/sell volume |
| `WS` | `/ws/liquidity` | Multi-symbol liquidity stream |
