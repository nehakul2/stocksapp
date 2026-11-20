"""Buy / hold / sell ideas for the stocks in a watchlist.

The label comes from plain trend rules (core.suggest). An AI paragraph can sit on top that ties
a watchlist's ideas together; it uses the person's daily AI limit and can only restate the facts
it is given."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

import ai
import auth
import core
import lists
from db import User, get_db

router = APIRouter()

MAX_TICKERS = 30


def parse_tickers(raw: str) -> list:
    items = list(dict.fromkeys(core.normalize_ticker(t) for t in raw.split(",") if t.strip()))
    if not items:
        raise HTTPException(400, "Provide at least one ticker, comma-separated.")
    if len(items) > MAX_TICKERS:
        raise HTTPException(400, f"At most {MAX_TICKERS} tickers per request.")
    return items


ORDER = {"buy": 0, "sell": 1, "hold": 2}  # things that need a look first


def build(tickers: list) -> dict:
    items, unavailable = [], []
    for t in tickers:
        try:
            items.append(core.suggest(t))
        except Exception:
            unavailable.append(t)
    items.sort(key=lambda i: (ORDER[i["action"]], -abs(i["score"]), i["ticker"]))
    return {"items": items, "unavailable": unavailable, "disclaimer": core.SUGGEST_DISCLAIMER}


@router.get("/api/suggestions")
def suggestions(tickers: str = Query(...)):
    return build(parse_tickers(tickers))


WORD = {"buy": "leans toward buying", "hold": "no clear signal (hold)", "sell": "leans toward selling"}


@router.post("/api/watchlists/{watchlist_id}/suggestions/summary")
def summary(
    watchlist_id: int,
    x_anthropic_key: Optional[str] = Header(default=None),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    own_key = (x_anthropic_key or "").strip()
    key = own_key or ai.server_key()
    if not key:
        raise HTTPException(503, "AI summaries aren't set up on this server yet.")
    wl = lists.get_owned(db, user, watchlist_id)
    tickers = lists.tickers_of(db, wl.id)
    if not tickers:
        raise HTTPException(400, "Add a few stocks to this watchlist first.")
    data = build(tickers)
    if not data["items"]:
        raise HTTPException(502, "Couldn't load price data for this watchlist right now. Try again in a minute.")

    facts = []
    for i in data["items"]:
        line = f"{i['ticker']}: {WORD[i['action']]} ({i['strength']}). " + " ".join(i["reasons"][:3])
        if i["cautions"]:
            line += " Caution: " + " ".join(i["cautions"])
        facts.append(line)
    prompt = (
        "You are a plain-English markets explainer for a casual retail investor, not a financial advisor. "
        f"Below are rule-based trend ideas for the stocks in their watchlist \"{wl.name}\".\n\n<data>\n"
        + "\n".join(facts) + "\n</data>\n\n"
        "Write 3-5 short sentences that tie these together for the whole watchlist: which stocks look strongest, "
        "which look weakest, and the main things to be careful about (such as earnings soon, or stocks that swing a lot). "
        "Use only the facts above and invent nothing. Do not give price targets or promise outcomes, and say these are "
        "ideas from simple trend rules, not advice, in one short clause. Plain text only, no lists."
    )
    counted = not own_key
    if counted:
        ai.reserve(db, user.id)
    try:
        text = ai.ask_claude(key, prompt, max_tokens=400)
    except Exception:
        ai.log.exception("Suggestions summary failed")
        if counted:
            ai.refund(db, user.id)
        raise HTTPException(502, "The AI service didn't respond. Try again in a moment.")
    return {"summary": text, "usage": ai.usage(db, user.id)}
