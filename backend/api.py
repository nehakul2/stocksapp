"""JSON API for the Stock Insights app (web and mobile clients both call this).

Run locally:  uvicorn api:app --reload --port 8000
Docs (auto-generated): http://localhost:8000/docs
"""
import math
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads backend/.env if present
except ImportError:
    pass

import ai
import auth
import core
from db import User, WatchlistItem, get_db, init_db

app = FastAPI(title="Stock Insights API", version="0.2.0")

# Only these websites may call the API from a browser. In production set
# CORS_ORIGINS to your frontend's address (comma-separated for several).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3002,http://127.0.0.1:3002",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()

# Same ranges as the Streamlit app: (data to fetch, days of chart to show)
# (data to fetch, days of chart to show). Every range fetches at least 2 years
# so the 200-day SMA can be computed (it needs ~200 trading days of history,
# which 9 months does not provide).
RANGES = {"1mo": ("2y", 22), "6mo": ("2y", 130), "1y": ("2y", 252), "5y": ("6y", 1260)}
SMA_FETCH_PERIOD = "2y"
MAX_TICKERS = 30


def clean(value):
    """Make pandas/numpy values JSON-safe (NaN/inf -> None)."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if (math.isnan(value) or math.isinf(value)) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def parse_tickers(raw: str) -> list:
    items = [core.normalize_ticker(t) for t in raw.split(",") if t.strip()]
    items = list(dict.fromkeys(items))
    if not items:
        raise HTTPException(400, "Provide at least one ticker, comma-separated.")
    if len(items) > MAX_TICKERS:
        raise HTTPException(400, f"At most {MAX_TICKERS} tickers per request.")
    return items


def load_history(ticker: str, period: str) -> pd.DataFrame:
    try:
        return core.fetch_history(ticker, period)
    except Exception as e:
        raise HTTPException(404, str(e))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search(q: str = Query(..., min_length=2)):
    return {"results": core.search_tickers(q)}


@app.get("/api/overview")
def overview(tickers: str):
    """The SMA Overview table: one row per ticker."""
    table = core.build_sma_table(parse_tickers(tickers), SMA_FETCH_PERIOD)
    return {"rows": clean(table.where(table.notna(), None).to_dict(orient="records"))}


@app.get("/api/attention")
def attention(tickers: str):
    """'Needs attention' pointers, highest priority first; quiet tickers omitted."""
    results = [core.compute_attention(t) for t in parse_tickers(tickers)]
    results = [r for r in results if r["score"] > 0]
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"items": clean(results)}


@app.get("/api/stocks/{ticker}")
def stock_detail(ticker: str, range: str = "6mo"):
    """Everything the detail view needs in one call."""
    if range not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    ticker = core.normalize_ticker(ticker)
    fetch_period, _ = RANGES[range]
    try:
        summary = core.get_stock_summary(ticker)
    except Exception as e:
        raise HTTPException(404, str(e))
    hist = core.add_smas(load_history(ticker, fetch_period))
    news = core.get_news(ticker)

    trend = None
    try:
        _, predictions, direction, _ = core.estimate_trend(hist)
        trend = {"direction": direction, "estimates": predictions,
                 "disclaimer": "Naive momentum extrapolation, not a forecast. Not financial advice."}
    except Exception:
        pass

    prev_day = None
    if len(hist) >= 2:
        p = hist.iloc[-2]
        prev_day = {"date": hist.index[-2].strftime("%Y-%m-%d"), "open": p["Open"], "high": p["High"],
                    "low": p["Low"], "close": p["Close"]}

    latest = hist.iloc[-1]
    smas = {str(w): latest.get(f"SMA_{w}") for w in core.SMA_WINDOWS}

    return clean({
        "summary": summary,
        "smas": smas,
        "previous_day": prev_day,
        "trend": trend,
        "explanation": core.explain_price_move(ticker, hist, news),
        "news": news,
        "next_earnings": core.get_next_earnings_date(ticker),
    })


@app.get("/api/stocks/{ticker}/history")
def stock_history(ticker: str, range: str = "6mo"):
    if range not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    ticker = core.normalize_ticker(ticker)
    fetch_period, days = RANGES[range]
    hist = core.add_smas(load_history(ticker, fetch_period)).tail(days)
    cols = ["Open", "High", "Low", "Close", "Volume"] + [f"SMA_{w}" for w in core.SMA_WINDOWS]
    rows = []
    for ts, r in hist.iterrows():
        row = {"date": ts.strftime("%Y-%m-%d")}
        for c in cols:
            row[c.lower()] = r[c]
        rows.append(row)
    return {"ticker": ticker, "range": range, "bars": clean(rows)}


@app.get("/api/stocks/{ticker}/intraday")
def stock_intraday(ticker: str):
    """1-minute bars incl. pre/after-hours. Empty list if unavailable (indexes, some futures)."""
    ticker = core.normalize_ticker(ticker)
    df = core.fetch_intraday_extended(ticker)
    bars = [{"time": ts.isoformat(), "close": r["Close"], "volume": r["Volume"]} for ts, r in df.iterrows()] if not df.empty else []
    return {"ticker": ticker, "bars": clean(bars)}


@app.post("/api/stocks/{ticker}/ai-summary")
def ai_summary(
    ticker: str,
    x_anthropic_key: Optional[str] = Header(default=None),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Plain-English explanation of today's move, plus the headlines that matter.
    Requires sign-in. Uses the server's Anthropic key and counts against the user's
    daily limit. A caller may instead send their own key in X-Anthropic-Key; that key
    is used for this one request, never stored or logged, and is not limited."""
    own_key = (x_anthropic_key or "").strip()
    key = own_key or ai.server_key()
    if not key:
        raise HTTPException(503, "AI explanations aren't set up on this server yet.")

    ticker = core.normalize_ticker(ticker)
    hist = core.add_smas(load_history(ticker, SMA_FETCH_PERIOD))
    news = core.get_news(ticker, max_items=10)
    explanation = core.explain_price_move(ticker, hist, news)
    if explanation["pct_change"] is None:
        raise HTTPException(422, "Not enough price history to summarize.")

    counted = not own_key
    if counted:
        ai.reserve(db, user.id)  # only after the data checks, so bad requests don't cost quota
    try:
        result = ai.explain_move(key, ticker, explanation, news)
    except Exception:
        ai.log.exception("AI call failed for %s", ticker)
        if counted:
            ai.refund(db, user.id)
        raise HTTPException(502, "The AI service didn't respond. Try again in a moment.")
    return {"ticker": ticker, **result, "usage": ai.usage(db, user.id)}


@app.get("/api/ai/usage")
def ai_usage(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return {**ai.usage(db, user.id), "enabled": bool(ai.server_key())}


# ---------------------------------------------------------------- accounts
class Credentials(BaseModel):
    email: str
    password: str


class WatchlistBody(BaseModel):
    tickers: list[str]


def session_payload(user: User) -> dict:
    return {"token": auth.make_token(user), "user": {"id": user.id, "email": user.email}}


@app.post("/api/auth/signup", status_code=201)
def signup(body: Credentials, db: Session = Depends(get_db)):
    email = auth.normalize_email(body.email)
    auth.check_password(body.password)
    user = User(email=email, password_hash=auth.hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    return session_payload(user)


@app.post("/api/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    email = (body.email or "").strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Same message for unknown email and wrong password, so emails can't be probed.
    if user is None or not auth.verify_password(body.password or "", user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return session_payload(user)


@app.get("/api/me")
def me(user: User = Depends(auth.current_user)):
    return {"id": user.id, "email": user.email}


def _saved_tickers(db: Session, user_id: int) -> list:
    rows = db.scalars(
        select(WatchlistItem).where(WatchlistItem.user_id == user_id).order_by(WatchlistItem.position)
    )
    return [r.ticker for r in rows]


@app.get("/api/watchlist")
def get_watchlist(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return {"tickers": _saved_tickers(db, user.id)}


@app.put("/api/watchlist")
def put_watchlist(
    body: WatchlistBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)
):
    tickers = list(dict.fromkeys(core.normalize_ticker(t) for t in body.tickers if t.strip()))
    if len(tickers) > MAX_TICKERS:
        raise HTTPException(400, f"A watchlist can hold at most {MAX_TICKERS} tickers.")
    db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id).delete()
    for i, t in enumerate(tickers):
        db.add(WatchlistItem(user_id=user.id, ticker=t, position=i))
    db.commit()
    return {"tickers": tickers}
