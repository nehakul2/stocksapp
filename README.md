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
Signed in, the watchlist is saved to your account. Signed out, it stays in the browser.
There is no password reset yet (it needs an email service).

## Database (Neon)
1. Create a free project at neon.tech and copy its connection string (starts with `postgresql://`).
2. Local: put it in `backend/.env` as `DATABASE_URL=...`. Deployed: set it as a variable on the backend service.
3. Tables are created automatically on startup.
Railway's own Postgres works too: only the `DATABASE_URL` value changes, not the code.

## Deploy on Railway
Create two services from this repo:

| Service | Root directory | Variables |
|---|---|---|
| backend | `backend` | `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS` (the frontend's public URL) |
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
| GET, PUT | /api/watchlist | saved tickers for the signed-in user |
| GET | /api/search?q= | company name -> ticker |
| GET | /api/overview?tickers= | SMA overview rows |
| GET | /api/attention?tickers= | "Worth a look" pointers |
| GET | /api/stocks/{t}?range= | summary, SMAs, trend, why it moved, news |
| GET | /api/stocks/{t}/history?range= | OHLC, volume and SMA series |
| GET | /api/stocks/{t}/intraday | 1-minute bars incl. pre/after-hours |
| POST | /api/stocks/{t}/ai-summary | AI summary; key in `X-Anthropic-Key` |

## Roadmap
1. Backend API, done. 2. Web app, done. 3. Accounts + database, this PR. 4. Mobile app (Expo).
5. AI skills: relevant headlines, peer comparison, risks, Q&A. 6. Alerts and saved profiles per user.
