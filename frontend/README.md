# Stock Insights web app (frontend)

Next.js + TypeScript. Talks to the API in ../backend.

## Run it (two terminals)

Terminal 1: the API
```
cd backend
source .venv/bin/activate
uvicorn api:app --reload --port 8001
```

Terminal 2: the web app
```
cd frontend
npm install
npm run dev
```
Open http://localhost:3000

`frontend/.env.local` points the web app at the API (`http://127.0.0.1:8001`). If your API
runs on another port, change that one line and restart `npm run dev`.

## What's here
- `/` : "Worth a look today" pointers, then your watchlist as a ledger
- `/stock/TGT` : why it moved, chart (candles/line/area, 1M-5Y, SMAs, volume), key figures, news, AI summary
- Display menu: light/dark/system, and color-blind-friendly gain/loss colors

## Known limits (next phases)
- The watchlist is saved in this browser only. Logins and a database come next.
- Search results come from Yahoo; an ETF or index may need its Yahoo symbol (^GSPC, GC=F).
