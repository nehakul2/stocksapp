"""Named watchlists, per-watchlist alerts, alert history, and CSV export."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth
import core
from db import Alert, AlertEvent, User, Watchlist, WatchlistItem, WatchlistTicker, get_db

router = APIRouter()

MAX_TICKERS = 30
MAX_WATCHLISTS = 10
MAX_ALERTS_PER_TICKER = 10
DEFAULT_NAME = "My Watchlist"


# ------------------------------------------------------------------ helpers
def ensure_watchlists(db: Session, user: User) -> list:
    """Returns the user's watchlists in order. A user who has none yet (everyone, the
    first time after this feature shipped) gets one named 'My Watchlist', filled from
    the single list they had before, so nothing they saved is lost."""
    rows = list(db.scalars(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.position, Watchlist.id)))
    if rows:
        return rows
    wl = Watchlist(user_id=user.id, name=DEFAULT_NAME, position=0)
    db.add(wl)
    db.flush()
    legacy = db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.position))
    for i, item in enumerate(legacy):
        db.add(WatchlistTicker(watchlist_id=wl.id, ticker=item.ticker, position=i))
    try:
        db.commit()
    except IntegrityError:  # two requests raced to create it; use the winner's
        db.rollback()
        return list(db.scalars(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.position, Watchlist.id)))
    return [wl]


def get_owned(db: Session, user: User, watchlist_id: int) -> Watchlist:
    ensure_watchlists(db, user)
    wl = db.get(Watchlist, watchlist_id)
    if wl is None or wl.user_id != user.id:
        raise HTTPException(404, "Watchlist not found.")
    return wl


def tickers_of(db: Session, watchlist_id: int) -> list:
    rows = db.scalars(select(WatchlistTicker).where(WatchlistTicker.watchlist_id == watchlist_id).order_by(WatchlistTicker.position))
    return [r.ticker for r in rows]


def alert_json(a: Alert) -> dict:
    return {"id": a.id, "watchlist_id": a.watchlist_id, "ticker": a.ticker, "type": a.type,
            "value": a.value, "label": core.alert_label(a.type, a.value)}


def clean_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise HTTPException(400, "Give the watchlist a name.")
    if len(name) > 40:
        raise HTTPException(400, "Watchlist names can be at most 40 characters.")
    return name


def watchlist_json(db: Session, wl: Watchlist) -> dict:
    return {"id": wl.id, "name": wl.name, "tickers": tickers_of(db, wl.id)}


def set_tickers(db: Session, wl: Watchlist, raw: list) -> list:
    tickers = list(dict.fromkeys(core.normalize_ticker(t) for t in raw if t.strip()))
    if len(tickers) > MAX_TICKERS:
        raise HTTPException(400, f"A watchlist can hold at most {MAX_TICKERS} tickers.")
    db.query(WatchlistTicker).filter(WatchlistTicker.watchlist_id == wl.id).delete()
    for i, t in enumerate(tickers):
        db.add(WatchlistTicker(watchlist_id=wl.id, ticker=t, position=i))
    # Alerts on tickers that were removed no longer mean anything.
    db.query(Alert).filter(Alert.watchlist_id == wl.id, Alert.ticker.notin_(tickers or [""])).delete(synchronize_session=False)
    db.commit()
    return tickers


# ------------------------------------------------------------------ watchlists
class NameBody(BaseModel):
    name: str


class TickersBody(BaseModel):
    tickers: list[str]


@router.get("/api/watchlists")
def list_watchlists(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return {"watchlists": [watchlist_json(db, wl) for wl in ensure_watchlists(db, user)]}


@router.post("/api/watchlists", status_code=201)
def create_watchlist(body: NameBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    existing = ensure_watchlists(db, user)
    if len(existing) >= MAX_WATCHLISTS:
        raise HTTPException(400, f"You can have at most {MAX_WATCHLISTS} watchlists.")
    wl = Watchlist(user_id=user.id, name=clean_name(body.name), position=len(existing))
    db.add(wl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a watchlist with that name.")
    return watchlist_json(db, wl)


@router.patch("/api/watchlists/{watchlist_id}")
def rename_watchlist(watchlist_id: int, body: NameBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    wl = get_owned(db, user, watchlist_id)
    wl.name = clean_name(body.name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a watchlist with that name.")
    return watchlist_json(db, wl)


@router.delete("/api/watchlists/{watchlist_id}")
def delete_watchlist(watchlist_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    wl = get_owned(db, user, watchlist_id)
    if len(ensure_watchlists(db, user)) <= 1:
        raise HTTPException(400, "You need at least one watchlist.")
    db.query(WatchlistTicker).filter(WatchlistTicker.watchlist_id == wl.id).delete()
    db.query(Alert).filter(Alert.watchlist_id == wl.id).delete()
    db.delete(wl)
    db.commit()
    return {"watchlists": [watchlist_json(db, w) for w in ensure_watchlists(db, user)]}


@router.put("/api/watchlists/{watchlist_id}/tickers")
def put_tickers(watchlist_id: int, body: TickersBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    wl = get_owned(db, user, watchlist_id)
    return {"tickers": set_tickers(db, wl, body.tickers)}


# The original single-list endpoints keep working: they read and write the first watchlist.
@router.get("/api/watchlist")
def legacy_get(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return {"tickers": tickers_of(db, ensure_watchlists(db, user)[0].id)}


@router.put("/api/watchlist")
def legacy_put(body: TickersBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return {"tickers": set_tickers(db, ensure_watchlists(db, user)[0], body.tickers)}


# ------------------------------------------------------------------ alerts
class AlertBody(BaseModel):
    ticker: str
    type: str
    value: float


@router.get("/api/watchlists/{watchlist_id}/alerts")
def list_alerts(watchlist_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    wl = get_owned(db, user, watchlist_id)
    rows = db.scalars(select(Alert).where(Alert.watchlist_id == wl.id).order_by(Alert.id))
    return {"alerts": [alert_json(a) for a in rows]}


@router.post("/api/watchlists/{watchlist_id}/alerts", status_code=201)
def add_alert(watchlist_id: int, body: AlertBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    wl = get_owned(db, user, watchlist_id)
    ticker = core.normalize_ticker(body.ticker)
    if body.type not in core.ALERT_TYPES:
        raise HTTPException(400, f"Alert type must be one of {list(core.ALERT_TYPES)}.")
    if ticker not in tickers_of(db, wl.id):
        raise HTTPException(400, f"Add {ticker} to the '{wl.name}' watchlist first.")
    if body.type.startswith("price_"):
        if not body.value > 0:
            raise HTTPException(400, "The price level must be above zero.")
    elif body.value not in core.SMA_WINDOWS:
        raise HTTPException(400, f"The average must be one of {core.SMA_WINDOWS} days.")
    count = db.query(Alert).filter(Alert.watchlist_id == wl.id, Alert.ticker == ticker).count()
    if count >= MAX_ALERTS_PER_TICKER:
        raise HTTPException(400, f"At most {MAX_ALERTS_PER_TICKER} alerts per stock.")
    alert = Alert(watchlist_id=wl.id, ticker=ticker, type=body.type, value=float(body.value))
    db.add(alert)
    db.commit()
    return alert_json(alert)


@router.delete("/api/alerts/history")
def clear_history(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    db.query(AlertEvent).filter(AlertEvent.user_id == user.id).delete()
    db.commit()
    return {"ok": True}


@router.delete("/api/alerts/{alert_id}")
def delete_alert(alert_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found.")
    get_owned(db, user, alert.watchlist_id)  # 404 if it belongs to someone else
    db.delete(alert)
    db.commit()
    return {"ok": True}


@router.post("/api/alerts/check")
def check_alerts(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Checks every alert the user has, across all their watchlists, against the latest
    prices. New firings are added to the history once per day. Returns what is firing now."""
    lists = ensure_watchlists(db, user)
    by_id = {wl.id: wl for wl in lists}
    alerts = list(db.scalars(select(Alert).where(Alert.watchlist_id.in_(list(by_id)))))
    hist_cache: dict = {}
    firing = []
    problems = []
    for a in alerts:
        if a.ticker not in hist_cache:
            try:
                hist_cache[a.ticker] = core.add_smas(core.fetch_history(a.ticker, core.ALERT_FETCH_PERIOD))
            except Exception:
                hist_cache[a.ticker] = None
        hist = hist_cache[a.ticker]
        if hist is None:
            problems.append(a.ticker)
            continue
        message = core.evaluate_alert(a.ticker, hist, a.type, a.value)
        if message:
            firing.append({"alert_id": a.id, "watchlist_id": a.watchlist_id, "watchlist": by_id[a.watchlist_id].name,
                           "ticker": a.ticker, "type": a.type, "message": message})
    today = date.today().isoformat()
    for f in firing:
        db.add(AlertEvent(user_id=user.id, watchlist_name=f["watchlist"], ticker=f["ticker"], day=today, message=f["message"][:200]))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # already logged today
    return {"firing": firing, "unavailable": sorted(set(problems)), "checked": len(alerts)}


@router.get("/api/alerts/history")
def alert_history(limit: int = Query(50, ge=1, le=200), user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AlertEvent).where(AlertEvent.user_id == user.id).order_by(AlertEvent.id.desc()).limit(limit))
    return {"events": [{"id": e.id, "day": e.day, "watchlist": e.watchlist_name, "ticker": e.ticker, "message": e.message} for e in rows]}


# ------------------------------------------------------------------ CSV export
@router.get("/api/stocks/{ticker}/export.csv")
def export_history(ticker: str, start: str = Query(...), end: str = Query(...)):
    """Daily open/high/low/close for a date range, newest first, as a CSV download."""
    try:
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Dates must look like 2026-01-31.")
    if d0 > d1:
        raise HTTPException(400, "The start date must be on or before the end date.")
    ticker = core.normalize_ticker(ticker)
    try:
        hist = core.fetch_history(ticker, "6y")
    except Exception as e:
        raise HTTPException(404, str(e))
    part = hist.loc[start:end, ["Open", "High", "Low", "Close"]].round(2)
    if part.empty:
        raise HTTPException(404, "No trading days in that range.")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Open", "High", "Low", "Close"])
    for ts, r in part.iloc[::-1].iterrows():
        writer.writerow([ts.strftime("%Y-%m-%d"), r["Open"], r["High"], r["Low"], r["Close"]])
    safe = ticker.replace("^", "").replace("=", "")
    return Response(
        out.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}_{start}_to_{end}.csv"',
                 "Access-Control-Expose-Headers": "Content-Disposition"},
    )
