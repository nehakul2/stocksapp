# Stock Insights

Why your stocks moved, and which ones deserve a look today.

```
frontend (Next.js)  ->  backend (FastAPI)  ->  Yahoo Finance
                            |-> Postgres: accounts and watchlists (SQLite file when running locally)
                            |-> Anthropic API (user's own key, sent per request, never stored)
```

## Run it locally
Backend (terminal 1):
```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional locally: empty DATABASE_URL uses a local SQLite file
uvicorn api:app --reload --port 8001
```
Frontend (terminal 2):
```
cd frontend
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
npm install
npm run dev
```
Open the `Local:` address that `npm run dev` prints. API docs: http://127.0.0.1:8001/docs

## Accounts
Email + password. Passwords are hashed (scrypt); sessions are signed tokens valid for 30 days.
Signed in, the watchlist is saved to your account. Signed out, it stays in the browser. A new account starts with the default list.
There is no password reset yet (it needs an email service).

## AI explanations
Signed-in users can ask for a short explanation of a stock's move, plus the headlines that bear on it.
The server uses one Anthropic key (`ANTHROPIC_API_KEY`), so friends don't need their own. Cost is capped:
`AI_DAILY_LIMIT` per user per day (default 10) and `AI_GLOBAL_DAILY_LIMIT` for everyone (default 200).
Failed AI calls aren't counted. Also set a monthly spending limit in the Anthropic console.
Without the key the AI section says it isn't switched on.

## Watchlists, alerts and downloads
Signed-in users can keep up to 10 named watchlists. Each stock on a watchlist can have alerts:
price above or below a level, or price crossing its 5, 20, 50, 100 or 200-day average. Alerts are checked
when the app is open (and every 5 minutes after) and listed on the Alerts page, with history.
Price history for any date range, and the watchlist table, download as CSV.

## Email alerts
Optional. Set `RESEND_API_KEY` (from resend.com) on the backend to switch it on. A background thread then
checks every `ALERT_EMAIL_MINUTES` (default 15) and emails each user who turned it on, once when an alert
starts firing (and again only if it stops and fires again). Until you verify a domain with Resend it can only
deliver to your own address, so set `EMAIL_ALLOWED_TO` to that address. Other users see that email is not
available for them yet. `EMAIL_FROM`, `FRONTEND_URL` and `ALERT_TIMEZONE` (the zone for times inside emails, default UTC) are optional.
The Alerts page has a "Send me a test email" button that shows the provider's exact error if sending fails.

## Chat
Each stock page, and the home page, has a chat box. Questions use that stock's data (price, averages,
news, earnings, peers) and your watchlists as context, and count against the same daily AI limit.
Watchlist changes asked for in chat (create, add, remove, rename) are only proposed: the page shows each one
with a Confirm button, and nothing changes until you click it. Voice uses the browser's built-in speech
recognition and speech synthesis (Chrome, Edge, Safari); the buttons are hidden where a browser lacks them.

## Database (Neon)
1. Create a free project at neon.tech and copy its connection string (starts with `postgresql://`).
2. Local: put it in `backend/.env` as `DATABASE_URL=...`. Deployed: set it as a variable on the backend service.
3. Tables are created automatically on startup.
Railway's own Postgres works too: only the `DATABASE_URL` value changes, not the code.

## Deploy on Railway
Create two services from this repo:

| Service | Root directory | Variables |
|---|---|---|
| backend | `backend` | `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS` (the frontend's public URL), `ANTHROPIC_API_KEY` (for AI) |
| frontend | `frontend` | `NEXT_PUBLIC_API_URL` (the backend's public URL) |

`NEXT_PUBLIC_API_URL` is baked in at build time, so redeploy the frontend after changing it.
Deploy the backend first, copy its URL into the frontend variable, deploy the frontend, then
put the frontend's URL into the backend's `CORS_ORIGINS`.
Without `SECRET_KEY` the backend refuses to start on Railway.

## Tests (offline)
```
cd backend && pip install pytest && pytest
```

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | /api/auth/signup, /api/auth/login | create account / sign in, returns a token |
| GET | /api/me | who is signed in |
| GET, POST | /api/watchlists | list / create watchlists |
| PATCH, DELETE | /api/watchlists/{id} | rename / delete a watchlist |
| PUT | /api/watchlists/{id}/tickers | set a watchlist's tickers |
| GET, POST | /api/watchlists/{id}/alerts | list / add alerts |
| DELETE | /api/alerts/{id} | remove an alert |
| POST | /api/alerts/check | check all alerts now, returns what is firing |
| GET, DELETE | /api/alerts/history | alerts that fired |
| GET, PUT | /api/settings | email alerts on or off |
| POST | /api/chat | ask a question (optionally about a ticker); may propose watchlist changes |
| GET | /api/stocks/{t}/peers | the stock next to similar companies and the S&P 500 |
| GET | /api/stocks/{t}/export.csv?start=&end= | price history download |
| GET, PUT | /api/watchlist | original single-list endpoints (use the first watchlist) |
| GET | /api/search?q= | company name -> ticker |
| GET | /api/overview?tickers= | SMA overview rows |
| GET | /api/attention?tickers= | "Worth a look" pointers |
| GET | /api/stocks/{t}?range= | summary, SMAs, trend, why it moved, news |
| GET | /api/stocks/{t}/history?range= | OHLC, volume and SMA series |
| GET | /api/stocks/{t}/intraday | 1-minute bars incl. pre/after-hours |
| POST | /api/stocks/{t}/ai-summary | AI explanation + relevant headlines (sign-in required, daily limit) |
| GET | /api/ai/usage | how many AI explanations you have left today |

## Roadmap
Done: backend API, web app, accounts, AI explanations, peer comparison, multiple watchlists, alerts
(in-app and email), CSV downloads, chat with voice. Next: mobile app (Expo), risk summary, fundamentals.
