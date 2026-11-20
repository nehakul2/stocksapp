"""Core stock logic, ported from the Streamlit app with no UI dependencies.

The function bodies are the same ones the Streamlit app runs; only the
Streamlit-specific caching decorator was swapped for a small TTL cache.
"""
import time
import functools
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression


def st_cache(ttl):
    """Tiny in-process TTL cache (replaces st.cache_data)."""
    def deco(fn):
        store = {}

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            hit = store.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
            value = fn(*args, **kwargs)  # exceptions are not cached
            store[key] = (now, value)
            return value

        wrapper.cache_clear = store.clear
        return wrapper
    return deco


SMA_WINDOWS = [5, 20, 50, 100, 200]

ALERT_FETCH_PERIOD = "2y"

INDEX_ALIASES = {
    "IXIC": "^IXIC", ".IXIC": "^IXIC",          # Nasdaq Composite
    "DJI": "^DJI", ".DJI": "^DJI",              # Dow Jones Industrial Average
    "SPX": "^GSPC", ".SPX": "^GSPC", ".INX": "^GSPC", "GSPC": "^GSPC",  # S&P 500
    "SP100": "^SP100", ".SP100": "^SP100", "OEX": "^OEX", ".OEX": "^OEX",  # S&P 100
    "RUT": "^RUT", ".RUT": "^RUT",              # Russell 2000
    "VIX": "^VIX", ".VIX": "^VIX",              # CBOE Volatility Index
    "FTSE": "^FTSE", ".FTSE": "^FTSE",          # FTSE 100
    "N225": "^N225", ".N225": "^N225",          # Nikkei 225

    # Precious/industrial metals: Yahoo Finance uses continuous front-month
    # futures notation (root symbol + "=F"), not an exchange's specific
    # contract-month code (e.g. CME's "SIZ6" for Dec-2026 Silver). These
    # aliases let common names or CME root symbols resolve to Yahoo's form.
    "GOLD": "GC=F", "XAU": "GC=F", "GC": "GC=F",
    "SILVER": "SI=F", "XAG": "SI=F", "SI": "SI=F",
    "PLATINUM": "PL=F", "XPT": "PL=F", "PL": "PL=F",
    "PALLADIUM": "PA=F", "XPD": "PA=F", "PA": "PA=F",
    "COPPER": "HG=F", "HG": "HG=F",
}

@st_cache(60)
def get_stock_summary(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    # Yahoo sometimes returns an empty/partial `info` (rate limiting on shared
    # cloud IPs is the usual cause), even for valid symbols like TGT. So every
    # field below has a fallback instead of failing on the first miss.
    try:
        info = stock.info or {}
    except Exception:
        info = {}

    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    week_52_high = info.get("fiftyTwoWeekHigh")
    week_52_low = info.get("fiftyTwoWeekLow")
    long_name = info.get("longName") or info.get("shortName") or ticker
    currency = info.get("currency", "")
    exchange = info.get("fullExchangeName") or info.get("exchange", "")

    if current_price is None:
        try:
            fast = stock.fast_info
            current_price = fast.get("last_price")
            week_52_high = week_52_high or fast.get("year_high")
            week_52_low = week_52_low or fast.get("year_low")
            currency = currency or fast.get("currency", "")
            exchange = exchange or fast.get("exchange", "")
        except Exception:
            pass

    if current_price is None:
        # Last resort: derive from a year of daily bars.
        try:
            h = stock.history(period="1y")
            if not h.empty:
                current_price = float(h["Close"].iloc[-1])
                week_52_high = week_52_high or float(h["High"].max())
                week_52_low = week_52_low or float(h["Low"].min())
        except Exception:
            pass

    if current_price is None:
        raise ValueError(
            f"Couldn't load data for '{ticker}' right now. The symbol may be wrong, or Yahoo Finance "
            "may be temporarily throttling requests - wait a minute and click 'Refresh now'."
        )

    return {
        "name": long_name,
        "ticker": ticker.upper(),
        "price": current_price,
        "high_52wk": week_52_high,
        "low_52wk": week_52_low,
        "currency": currency,
        "exchange": exchange,
        # Extended-hours fields: only meaningful for US equities/ETFs while
        # the market is in a pre-market or post-market state. yfinance omits
        # these keys entirely outside those windows, so all reads use .get().
        "market_state": info.get("marketState", ""),
        "pre_market_price": info.get("preMarketPrice"),
        "pre_market_change_pct": info.get("preMarketChangePercent"),
        "post_market_price": info.get("postMarketPrice"),
        "post_market_change_pct": info.get("postMarketChangePercent"),
    }


@st_cache(60)
def fetch_history(ticker: str, period: str) -> pd.DataFrame:
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        raise ValueError(f"No price history found for {ticker}. Check the symbol.")
    return hist


@st_cache(60)
def fetch_intraday_extended(ticker: str) -> pd.DataFrame:
    """1-minute intraday bars for the most recent trading day, including
    pre-market and after-hours prints (prepost=True). Extended-hours data is
    a US-market concept and 1-minute intraday isn't available for every
    instrument (indexes, some futures), so this can legitimately come back
    empty — callers should handle that rather than treat it as an error."""
    try:
        intraday = yf.Ticker(ticker).history(period="1d", interval="1m", prepost=True)
        if intraday.empty:
            # Market may be fully closed (weekend/holiday) with no "today" bars yet;
            # fall back to the most recent available day within the last 5.
            wider = yf.Ticker(ticker).history(period="5d", interval="1m", prepost=True)
            if wider.empty:
                return wider
            last_day = wider.index.max().date()
            intraday = wider[wider.index.date == last_day]
        return intraday
    except Exception:
        return pd.DataFrame()


@st_cache(600)
def get_news(ticker: str, max_items: int = 5) -> list:
    try:
        news = yf.Ticker(ticker).news or []
    except Exception:
        return []

    items = []
    for item in news[:max_items]:
        content = item.get("content", item)
        title = content.get("title")
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
        canonical = content.get("canonicalUrl")
        link = canonical.get("url") if isinstance(canonical, dict) else content.get("link")
        if title:
            items.append({"title": title, "publisher": publisher or "Unknown source", "link": link})
    return items


def _as_date(value):
    if hasattr(value, "date") and callable(value.date):
        return value.date()  # datetime / Timestamp
    if hasattr(value, "year") and hasattr(value, "month"):
        return value  # already a date
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


@st_cache(86400)  # the calendar rarely changes intraday, cache it for a day
def _earnings_dates(ticker: str) -> tuple:
    """All earnings dates Yahoo lists for the ticker, as sorted 'YYYY-MM-DD'
    strings. yfinance has returned the calendar as a dict or a DataFrame across
    versions, so both shapes are handled."""
    try:
        cal = yf.Ticker(ticker).calendar
    except Exception:
        return ()
    raw = []
    try:
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date")
            raw = list(dates) if isinstance(dates, (list, tuple)) else ([dates] if dates else [])
        elif cal is not None and hasattr(cal, "empty") and not cal.empty and "Earnings Date" in cal.index:
            val = cal.loc["Earnings Date"]
            raw = list(val) if hasattr(val, "__iter__") and not isinstance(val, str) else [val]
    except Exception:
        return ()
    found = sorted({d for d in (_as_date(v) for v in raw) if d is not None})
    return tuple(d.strftime("%Y-%m-%d") for d in found)


def get_next_earnings_date(ticker: str) -> str:
    """The next upcoming earnings date as 'YYYY-MM-DD' (today counts), or ''.
    Yahoo sometimes keeps listing the report that already happened, so past dates
    are skipped instead of being shown as upcoming. The comparison with today runs
    on every call, so a cached date can't go stale."""
    today = date.today().strftime("%Y-%m-%d")
    upcoming = [d for d in _earnings_dates(ticker) if d >= today]
    return upcoming[0] if upcoming else ""


@st_cache(3600)
def search_tickers(query: str, max_results: int = 8) -> list:
    """Looks up a company name or partial symbol via Yahoo Finance's search
    endpoint (yf.Search) and returns a list of {symbol, name, exchange, type}
    dicts. Returns an empty list on any error or if the query is too short."""
    query = (query or "").strip()
    if len(query) < 2:
        return []

    try:
        results = yf.Search(query, max_results=max_results).quotes
    except Exception:
        return []

    matches = []
    for item in results:
        symbol = item.get("symbol")
        if not symbol:
            continue
        matches.append({
            "symbol": symbol,
            "name": item.get("shortname") or item.get("longname") or symbol,
            "exchange": item.get("exchange", ""),
            "type": item.get("typeDisp") or item.get("quoteType", ""),
        })
    return matches


def normalize_ticker(raw: str) -> str:
    t = raw.strip().upper()
    if t in INDEX_ALIASES:
        return INDEX_ALIASES[t]
    if t.startswith(".") and t[1:] not in ("",):
        # Unrecognized leading-dot symbol: try the caret convention as a best guess.
        return "^" + t[1:]
    return t


def add_smas(hist: pd.DataFrame, windows: list = SMA_WINDOWS) -> pd.DataFrame:
    hist = hist.copy()
    for window in windows:
        hist[f"SMA_{window}"] = hist["Close"].rolling(window=window).mean()
    return hist


def estimate_trend(hist: pd.DataFrame, lookback_days: int = 90):
    recent = hist.tail(min(lookback_days, len(hist)))
    if len(recent) < 10:
        raise ValueError("Not enough recent price history to estimate a trend.")

    closes = recent["Close"].values
    days = np.arange(len(closes)).reshape(-1, 1)

    model = LinearRegression()
    model.fit(days, closes)

    horizons = {"1_day": 1, "7_day": 7, "30_day": 30}
    slope = model.coef_[0]
    # Anchor to the actual last close and extend by the fitted slope. (Reading
    # the regression line itself at the last day can sit well above or below the
    # real price, which made an "upward" trend show estimates under today's price.)
    last_close = float(closes[-1])
    predictions = {label: round(last_close + slope * h, 2) for label, h in horizons.items()}

    direction = "upward" if slope > 0 else "downward" if slope < 0 else "flat"

    return model, predictions, direction, recent


def build_sma_table(tickers: list, period: str) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        try:
            hist = fetch_history(ticker, period)
            hist_with_sma = add_smas(hist)
            latest = hist_with_sma.iloc[-1]

            try:
                exchange = get_stock_summary(ticker).get("exchange", "")
            except Exception:
                exchange = ""

            next_earnings = get_next_earnings_date(ticker)

            row = {
                "ticker": ticker.upper(),
                "exchange": exchange,
                "date": hist_with_sma.index[-1].strftime("%Y-%m-%d"),
                "close": round(float(latest["Close"]), 2),
                "prev_close": round(float(hist_with_sma.iloc[-2]["Close"]), 2) if len(hist_with_sma) >= 2 else None,
                "next_earnings": next_earnings,
                # last 30 closes, for the small trend line in the watchlist
                "spark": [round(float(v), 2) for v in hist_with_sma["Close"].tail(30).dropna()],
            }
            for window in SMA_WINDOWS:
                value = latest.get(f"SMA_{window}")
                row[f"sma_{window}"] = round(float(value), 2) if pd.notna(value) else None
            rows.append(row)
        except Exception as e:
            rows.append({"ticker": ticker.upper(), "exchange": "", "date": None, "close": None, "next_earnings": "", "error": str(e)})

    return pd.DataFrame(rows)


def compute_attention(ticker: str) -> dict:
    """Scans one ticker for things worth a closer look and returns
    {"ticker", "score", "reasons"}. Each reason is phrased as a pointer
    (what was noticed + what to check), not a verdict. Rule-based on price,
    volume, SMAs, RSI, 52-week range, and earnings timing - no API calls
    beyond the cached Yahoo data the rest of the app already uses."""
    out = {"ticker": ticker, "score": 0.0, "reasons": []}
    try:
        hist = add_smas(fetch_history(ticker, ALERT_FETCH_PERIOD))
    except Exception:
        return out
    if len(hist) < 22:
        return out

    close = hist["Close"]
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    reasons = out["reasons"]

    def add(weight, text):
        out["score"] += weight
        reasons.append(text)

    # 1. Big daily move
    pct = (last - prev) / prev * 100 if prev else 0
    if abs(pct) >= 3:
        word = "up" if pct > 0 else "down"
        add(2 + abs(pct) / 5, f"Moved {word} {abs(pct):.1f}% in the last session - open the ticker to see what's driving it.")

    # 2. Unusual volume (vs trailing 20-day average, excluding the latest day)
    if "Volume" in hist.columns:
        avg_vol = hist["Volume"].iloc[-21:-1].mean()
        last_vol = hist["Volume"].iloc[-1]
        if avg_vol and last_vol and last_vol / avg_vol >= 2:
            add(1.5, f"Volume is {last_vol / avg_vol:.1f}x its 20-day average - heavy trading often means news or a big holder moving.")

    # 3. Price crossing a key moving average on the latest bar
    for window in (50, 200):
        col = f"SMA_{window}"
        if pd.notna(hist[col].iloc[-1]) and pd.notna(hist[col].iloc[-2]):
            was_above = prev > hist[col].iloc[-2]
            is_above = last > hist[col].iloc[-1]
            if is_above and not was_above:
                add(1.5, f"Crossed above its {window}-day average - check whether volume confirms the move.")
            elif was_above and not is_above:
                add(1.5, f"Dropped below its {window}-day average - a level many traders watch for support.")

    # 4. 50/200 golden or death cross in the last 5 sessions
    if hist["SMA_200"].notna().sum() >= 6:
        diff = (hist["SMA_50"] - hist["SMA_200"]).iloc[-6:]
        if (diff.iloc[0] < 0) and (diff.iloc[-1] > 0):
            add(2, "50-day average crossed above the 200-day in the last week (a 'golden cross') - a long-term trend signal worth reading about.")
        elif (diff.iloc[0] > 0) and (diff.iloc[-1] < 0):
            add(2, "50-day average crossed below the 200-day in the last week (a 'death cross') - a long-term trend signal worth reading about.")

    # 5. Near 52-week high / low
    year = hist.tail(252)
    hi, lo = float(year["High"].max()), float(year["Low"].min())
    if hi and last >= hi * 0.98:
        add(1.5, "Within 2% of its 52-week high - ask whether the run-up is backed by earnings or just momentum.")
    elif lo and last <= lo * 1.02:
        add(1.5, "Within 2% of its 52-week low - check for company-specific bad news versus a broad selloff.")

    # 6. RSI(14) overbought / oversold
    delta = close.diff().iloc[-15:]
    gains, losses = delta.clip(lower=0).mean(), (-delta.clip(upper=0)).mean()
    if losses and losses > 0:
        rsi = 100 - 100 / (1 + gains / losses)
        if rsi >= 70:
            add(1, f"RSI is {rsi:.0f} (overbought territory) - after a strong run, moves can cool off.")
        elif rsi <= 30:
            add(1, f"RSI is {rsi:.0f} (oversold territory) - a heavy selloff; check why before assuming a bounce.")

    # 7. Earnings close by
    earn = get_next_earnings_date(ticker)
    if earn:
        try:
            days = (datetime.strptime(earn, "%Y-%m-%d").date() - datetime.now().date()).days
            if -1 <= days <= 3:
                when = "today" if days == 0 else ("tomorrow" if days == 1 else (f"in {days} days" if days > 1 else "yesterday"))
                add(2, f"Earnings report {when} ({earn}) - results often cause outsized moves; review expectations.")
        except Exception:
            pass

    return out


def explain_price_move(ticker: str, hist_with_sma: pd.DataFrame, news_items: list) -> dict:
    """Builds a heuristic 'why is this moving' explanation from data already
    on hand: today's move size, whether volume looks unusual, how the move
    compares to the S&P 500 over the same window, proximity to an earnings
    report, and recent headlines. This is pattern-matching over public data,
    not a verified causal explanation — headlines are surfaced as *possible*
    context, never a confirmed cause."""
    result = {
        "pct_change": None,
        "magnitude": "",
        "volume_note": "",
        "market_note": "",
        "earnings_note": "",
        "headlines": [],
    }

    if len(hist_with_sma) < 2:
        return result

    today_close = float(hist_with_sma.iloc[-1]["Close"])
    prev_close = float(hist_with_sma.iloc[-2]["Close"])
    pct_change = (today_close - prev_close) / prev_close * 100 if prev_close else None
    result["pct_change"] = pct_change

    if pct_change is not None:
        abs_pct = abs(pct_change)
        if abs_pct >= 5:
            result["magnitude"] = "a large move"
        elif abs_pct >= 2:
            result["magnitude"] = "a notable move"
        elif abs_pct >= 0.5:
            result["magnitude"] = "a modest move"
        else:
            result["magnitude"] = "a small, unremarkable move"

    # Volume vs. the trailing 20-day average (today excluded, so a spike isn't self-diluted).
    if "Volume" in hist_with_sma.columns and len(hist_with_sma) >= 21:
        today_volume = hist_with_sma.iloc[-1]["Volume"]
        avg_volume = hist_with_sma["Volume"].iloc[-21:-1].mean()
        if avg_volume and today_volume:
            ratio = today_volume / avg_volume
            if ratio >= 2:
                result["volume_note"] = (
                    f"Volume is running about {ratio:.1f}x the 20-day average — unusually heavy "
                    "trading, often a sign something specific (news, a large trade, options "
                    "activity) is driving today's move."
                )
            elif ratio >= 1.4:
                result["volume_note"] = f"Volume is about {ratio:.1f}x the 20-day average — somewhat elevated."
            elif ratio <= 0.6:
                result["volume_note"] = (
                    f"Volume is only about {ratio:.1f}x the 20-day average — a quiet day, so "
                    "today's move may just be normal drift on light trading."
                )

    # Proximity to an earnings report (checked first: it changes how we read the market gap).
    near_earnings = False
    earnings_date_str = get_next_earnings_date(ticker)
    if earnings_date_str:
        try:
            earnings_date = datetime.strptime(earnings_date_str, "%Y-%m-%d").date()
            days_diff = abs((earnings_date - datetime.now().date()).days)
            if days_diff <= 2:
                near_earnings = True
                result["earnings_note"] = (
                    f"This is close to its earnings report date ({earnings_date_str}) \u2014 earnings "
                    "reactions are a common driver of outsized moves."
                )
        except Exception:
            pass

    # Compare to the broader market (S&P 500) over the same window.
    try:
        benchmark = fetch_history("^GSPC", "1mo")
        if len(benchmark) >= 2:
            b_today = float(benchmark.iloc[-1]["Close"])
            b_prev = float(benchmark.iloc[-2]["Close"])
            b_pct = (b_today - b_prev) / b_prev * 100 if b_prev else None
            if b_pct is not None and pct_change is not None:
                diff = pct_change - b_pct
                t = ticker.upper()
                if abs(diff) <= 0.5:
                    result["market_note"] = (
                        f"The S&P 500 moved {b_pct:+.2f}% over the same period \u2014 {t} "
                        "is moving roughly in line with the broader market, so this may be more "
                        "market-wide than stock-specific."
                    )
                else:
                    verb = "outperformed" if diff > 0 else "lagged"
                    note = (
                        f"The S&P 500 moved {b_pct:+.2f}% over the same period and {t} moved "
                        f"{pct_change:+.2f}%, so {t} {verb} the market by {abs(diff):.1f} points."
                    )
                    if abs(diff) >= 2 and not near_earnings:
                        note += " A gap this large points to something specific to the stock."
                    elif abs(diff) >= 2:
                        note += " With earnings close, the report itself may be the reason."
                    else:
                        note += " A gap this size is within ordinary stock-to-stock variation."
                    result["market_note"] = note
    except Exception:
        pass

    # Headlines as possible (not confirmed) context.
    result["headlines"] = news_items[:3]

    return result


ALERT_TYPES = ("price_above", "price_below", "sma_cross_above", "sma_cross_below")


def alert_label(alert_type: str, value: float) -> str:
    v = int(value) if float(value).is_integer() else value
    return {
        "price_above": f"Price above {v}",
        "price_below": f"Price below {v}",
        "sma_cross_above": f"Crosses above SMA {v}",
        "sma_cross_below": f"Crosses below SMA {v}",
    }[alert_type]


def evaluate_alert(ticker: str, hist_with_sma: pd.DataFrame, alert_type: str, value: float):
    """Returns a message if the alert has fired as of the latest bar, else None.
    Price alerts fire while the price is past the level. SMA alerts fire only on the
    day the price crosses (it was on one side yesterday and the other side today)."""
    if len(hist_with_sma) < 2:
        return None
    latest, previous = hist_with_sma.iloc[-1], hist_with_sma.iloc[-2]
    close, prev_close = float(latest["Close"]), float(previous["Close"])
    v = int(value) if float(value).is_integer() else value

    if alert_type == "price_above" and close > value:
        return f"{ticker}: price {close:.2f} is above your level of {v}"
    if alert_type == "price_below" and close < value:
        return f"{ticker}: price {close:.2f} is below your level of {v}"
    if alert_type in ("sma_cross_above", "sma_cross_below"):
        col = f"SMA_{int(value)}"
        sma, prev_sma = latest.get(col), previous.get(col)
        if sma is None or prev_sma is None or pd.isna(sma) or pd.isna(prev_sma):
            return None
        if alert_type == "sma_cross_above" and prev_close <= prev_sma and close > sma:
            return f"{ticker}: price crossed above its {int(value)}-day average"
        if alert_type == "sma_cross_below" and prev_close >= prev_sma and close < sma:
            return f"{ticker}: price crossed below its {int(value)}-day average"
    return None


# Fallback peer groups, used only when Yahoo can't tell us a stock's industry peers.
PEER_GROUPS = [
    ["WMT", "TGT", "COST", "AMZN", "DG", "BJ"],
    ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"],
    ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "TSM"],
    ["JPM", "BAC", "WFC", "C", "GS", "MS"],
    ["XOM", "CVX", "COP", "OXY", "SLB"],
    ["JNJ", "PFE", "MRK", "LLY", "ABBV"],
    ["KO", "PEP", "MDLZ", "PG", "KHC"],
    ["TSLA", "F", "GM", "TM", "RIVN"],
    ["BABA", "JD", "PDD", "BIDU", "AMZN"],
    ["NFLX", "DIS", "WBD", "PARA", "CMCSA"],
]
MAX_PEERS = 4
MARKET_TICKER = "^GSPC"


@st_cache(86400)
def find_peers(ticker: str) -> dict:
    """Similar companies for a stock: Yahoo's top companies in the same industry,
    or a small built-in group if Yahoo has nothing. Returns
    {"sector", "industry", "peers": [{"ticker", "name"}], "source"}."""
    t = ticker.upper()
    sector = industry = ""
    peers = []
    try:
        info = yf.Ticker(t).info or {}
        sector = info.get("sector") or ""
        industry = info.get("industry") or ""
        key = info.get("industryKey")
        if key:
            top = yf.Industry(key).top_companies
            if top is not None and len(top):
                for sym, row in top.iterrows():
                    sym = str(sym).upper()
                    if sym != t and not sym.startswith("^"):
                        peers.append({"ticker": sym, "name": str(row.get("name", "") or "")})
    except Exception:
        peers = []
    source = "industry"
    if not peers:
        source = "builtin"
        for group in PEER_GROUPS:
            if t in group:
                peers = [{"ticker": s, "name": ""} for s in group if s != t]
                break
    return {"sector": sector, "industry": industry, "peers": peers[:MAX_PEERS], "source": source if peers else "none"}


def _moves(ticker: str) -> dict:
    """Today's % change and the ~1-month (21 trading days) % change."""
    hist = fetch_history(ticker, "3mo")
    close = hist["Close"].dropna()
    if len(close) < 2:
        raise ValueError("not enough data")
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    month = None
    if len(close) >= 22 and float(close.iloc[-22]):
        month = (last / float(close.iloc[-22]) - 1) * 100
    return {"price": round(last, 2), "day_pct": (last / prev - 1) * 100 if prev else None, "month_pct": month}


def compare_with_peers(ticker: str) -> dict:
    """The stock, its peers and the S&P 500, side by side. Peers whose data can't
    be loaded are left out rather than failing the whole table."""
    t = ticker.upper()
    found = find_peers(t)
    rows = [{"ticker": t, "name": "", "kind": "self", **_moves(t)}]
    for p in found["peers"]:
        try:
            rows.append({"ticker": p["ticker"], "name": p["name"], "kind": "peer", **_moves(p["ticker"])})
        except Exception:
            continue
    try:
        rows.append({"ticker": MARKET_TICKER, "name": "S&P 500", "kind": "market", **_moves(MARKET_TICKER)})
    except Exception:
        pass

    peer_rows = [r for r in rows if r["kind"] == "peer"]
    def median(key):
        vals = sorted(r[key] for r in peer_rows if r[key] is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {
        "ticker": t,
        "sector": found["sector"],
        "industry": found["industry"],
        "rows": rows,
        "peer_median_day_pct": median("day_pct"),
        "peer_median_month_pct": median("month_pct"),
    }


def peer_facts(comparison: dict) -> str:
    """Peer numbers for the AI prompt, with the gap worked out in code ('' if no peers)."""
    peers = [r for r in comparison["rows"] if r["kind"] == "peer" and r["day_pct"] is not None]
    if not peers:
        return ""
    listing = ", ".join(f"{r['ticker']} {r['day_pct']:+.2f}%" for r in peers)
    med = comparison["peer_median_day_pct"]
    text = f"Similar companies today: {listing} (median {med:+.2f}%)."
    own = next((r for r in comparison["rows"] if r["kind"] == "self"), None)
    if own and own["day_pct"] is not None and med is not None:
        gap = own["day_pct"] - med
        if abs(gap) < 0.5:
            text += f" {comparison['ticker']} moved about in line with them."
        else:
            text += f" {comparison['ticker']} {'beat' if gap > 0 else 'trailed'} that median by {abs(gap):.1f} points."
    return text


# ------------------------------------------------------------------ risk and fundamentals
TRADING_DAYS = 252


def _daily_returns(ticker: str) -> pd.Series:
    """Daily % returns for the last year, indexed by calendar date (no time zone)."""
    close = fetch_history(ticker, "2y")["Close"].dropna()
    idx = pd.DatetimeIndex(close.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    close = pd.Series(close.to_numpy(dtype=float), index=idx.normalize())
    return close.pct_change().dropna().tail(TRADING_DAYS)


def risk_stats(ticker: str) -> dict:
    """How bumpy the ride has been over the past year, in numbers a beginner can read.
    Everything here is arithmetic on price history; nothing is predicted."""
    t = ticker.upper()
    close = fetch_history(t, "2y")["Close"].dropna().tail(TRADING_DAYS + 1)
    rets = _daily_returns(t)
    if len(rets) < 60:
        raise ValueError("Not enough price history to describe the risk.")
    vol = float(rets.std() * np.sqrt(TRADING_DAYS) * 100)
    typical = float(rets.abs().mean() * 100)
    worst_date, worst = rets.idxmin(), float(rets.min() * 100)
    values = close.to_numpy(dtype=float)
    peak = np.maximum.accumulate(values)
    max_dd = float((values / peak - 1).min() * 100)
    from_high = float((values[-1] / values.max() - 1) * 100)

    market_vol = beta = None
    try:
        mrets = _daily_returns(MARKET_TICKER)
        market_vol = float(mrets.std() * np.sqrt(TRADING_DAYS) * 100)
        both = pd.concat([rets, mrets], axis=1, join="inner").dropna()
        if len(both) >= 60 and both.iloc[:, 1].var() > 0:
            beta = float(both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var())
    except Exception:
        pass

    # The label is about how much the price swings compared with the market. Beta (how closely it
    # follows the market) is shown separately, because a stock can swing a lot without following it.
    ratio = vol / market_vol if market_vol else None
    if ratio is None:
        label = "unknown"
    elif ratio >= 1.2:
        label = "more volatile than the market"
    elif ratio <= 0.8:
        label = "calmer than the market"
    else:
        label = "about as volatile as the market"

    lines = [f"Over the past year its price has swung about {vol:.0f}% a year" + (f" (the S&P 500: {market_vol:.0f}%)." if market_vol else ".")]
    lines.append(f"A typical day moves about {typical:.1f}%. The worst day was {worst:+.1f}% on {worst_date:%b %d, %Y}.")
    if from_high > -0.5:
        lines.append(f"It is at its highest price of the past year. Its biggest drop from a peak in that time was {abs(max_dd):.0f}%.")
    else:
        lines.append(f"It is {abs(from_high):.0f}% below its highest price of the past year. Its biggest drop from a peak in that time was {abs(max_dd):.0f}%.")
    if beta is not None:
        lines.append(f"Beta {beta:.2f}: when the S&P 500 moves 1%, this stock has tended to move about {beta:.1f}%.")
    return {
        "label": label,
        "volatility_pct": round(vol, 1),
        "market_volatility_pct": None if market_vol is None else round(market_vol, 1),
        "typical_day_pct": round(typical, 2),
        "worst_day": {"date": f"{worst_date:%Y-%m-%d}", "pct": round(worst, 2)},
        "max_drawdown_pct": round(max_dd, 1),
        "from_high_pct": round(from_high, 1),
        "beta": None if beta is None else round(beta, 2),
        "lines": lines,
    }


@st_cache(21600)
def get_fundamentals(ticker: str) -> dict:
    """Company basics from Yahoo. Any field Yahoo doesn't have is None."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    def num(key):
        v = info.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None

    price = num("currentPrice") or num("regularMarketPrice")
    rate = num("dividendRate")
    return {
        "market_cap": num("marketCap"),
        "pe": num("trailingPE"),
        "forward_pe": num("forwardPE"),
        "eps": num("trailingEps"),
        # worked out from the yearly dividend and the price, because Yahoo has changed how it reports yield
        "dividend_yield_pct": round(rate / price * 100, 2) if rate and price else None,
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
    }


def generate_ai_move_summary(api_key: str, ticker: str, explanation: dict) -> str:
    """Turns the already-computed heuristic facts (price move, volume note,
    market comparison, earnings proximity, headlines) into a short
    plain-English narrative via the Claude API. This is a small proof-of-
    concept for whether LLM-written analysis is worth building out further —
    it only synthesizes facts already gathered above, it doesn't research
    anything new. Raises on any API error so the caller can show a friendly
    message; imports `anthropic` lazily so the app still runs without the
    package installed if this feature is never used."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    pct = explanation["pct_change"]
    facts = [f"{ticker.upper()} is {'up' if pct >= 0 else 'down'} {abs(pct):.2f}% today ({explanation['magnitude']})."]
    if explanation["market_note"]:
        facts.append(explanation["market_note"])
    if explanation["volume_note"]:
        facts.append(explanation["volume_note"])
    if explanation["earnings_note"]:
        facts.append(explanation["earnings_note"])
    for n in explanation["headlines"]:
        facts.append(f'Headline: "{n["title"]}" ({n["publisher"]})')

    prompt = (
        "You are a plain-English markets explainer for a casual retail investor, not a "
        "financial advisor. Given ONLY the facts below about one stock's move today, write "
        "a 2-4 sentence explanation of what's likely going on. Be upfront about uncertainty "
        "— these facts are correlational, not proof of causation. Do not invent facts beyond "
        "what's listed. Do not give buy/sell advice.\n\n"
        f"Facts about {ticker.upper()}:\n- " + "\n- ".join(facts)
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ------------------------------------------------------------------ buy / hold / sell ideas
SUGGEST_DISCLAIMER = (
    "These are ideas from simple price-trend rules, not advice. They can't see news, earnings or your own "
    "situation, and the market can do the opposite. Use your own judgment."
)


def _rsi(close: pd.Series, n: int = 14):
    delta = close.diff().iloc[-(n + 1):]
    gains, losses = delta.clip(lower=0).mean(), (-delta.clip(upper=0)).mean()
    if not losses or losses <= 0:
        return None
    return float(100 - 100 / (1 + gains / losses))


@st_cache(900)
def suggest(ticker: str) -> dict:
    """A plain buy / hold / sell idea for one stock from price trend, momentum and stretch.
    Every point added or taken away comes with its reason, so the label can be checked.
    Raises ValueError when there isn't enough history."""
    t = ticker.upper()
    hist = add_smas(fetch_history(t, "2y"))
    close = hist["Close"].dropna()
    if len(close) < 210:
        raise ValueError("Not enough price history for an idea.")
    last = float(close.iloc[-1])
    sma50, sma200 = float(hist["SMA_50"].iloc[-1]), float(hist["SMA_200"].iloc[-1])
    score, good, bad, cautions = 0, [], [], []

    # Long-term trend: the 200-day average counts most.
    if last > sma200:
        score += 2; good.append(f"Price is above its 200-day average ({(last / sma200 - 1) * 100:+.0f}%), a sign of a healthy long-term uptrend.")
    else:
        score -= 2; bad.append(f"Price is below its 200-day average ({(last / sma200 - 1) * 100:+.0f}%), a sign the long-term trend is weak.")
    if sma50 > sma200:
        score += 1; good.append("The 50-day average is above the 200-day average.")
    else:
        score -= 1; bad.append("The 50-day average is below the 200-day average.")
    if last > sma50:
        score += 1; good.append("Price is above its 50-day average, so the recent trend is up.")
    else:
        score -= 1; bad.append("Price is below its 50-day average, so the recent trend is down.")

    # Momentum over about three months.
    ret3 = float(last / close.iloc[-64] - 1) * 100 if len(close) > 64 else 0.0
    if ret3 >= 10:
        score += 1; good.append(f"Up {ret3:.0f}% over the past three months.")
    elif ret3 <= -10:
        score -= 1; bad.append(f"Down {abs(ret3):.0f}% over the past three months.")

    # Stretch: a stock that has run too far, too fast often cools off; a heavy selloff sometimes bounces.
    rsi = _rsi(close)
    if rsi is not None:
        if rsi >= 75:
            score -= 1; cautions.append(f"RSI is {rsi:.0f}, which means it has risen very fast lately. Moves like that often cool off.")
        elif rsi <= 30:
            score += 1; cautions.append(f"RSI is {rsi:.0f}, which means it has fallen very fast lately. It can bounce, or keep falling; check why.")

    high = float(close.tail(252).max())
    if last >= high * 0.98:
        cautions.append("It is at the top of its one-year range, so there is less room before the old high.")
    elif last <= high * 0.7:
        cautions.append(f"It is {(1 - last / high) * 100:.0f}% below its one-year high.")

    try:
        r = risk_stats(t)
        if r["label"] == "more volatile than the market":
            cautions.append(f"Its price swings more than the market ({r['volatility_pct']:.0f}% a year), so expect bigger ups and downs.")
    except Exception:
        pass
    try:
        earn = get_next_earnings_date(t)
        if earn:
            days = (datetime.strptime(earn, "%Y-%m-%d").date() - datetime.now().date()).days
            if 0 <= days <= 7:
                cautions.append(f"Earnings are due {'today' if days == 0 else f'in {days} days'} ({earn}). Results can move the price a lot either way.")
    except Exception:
        pass

    if score >= 3:
        action = "buy"
    elif score <= -3:
        action = "sell"
    else:
        action = "hold"
    strength = "strong" if abs(score) >= 5 else ("moderate" if abs(score) >= 3 else "weak")
    return {
        "ticker": t, "action": action, "strength": strength, "score": score, "price": round(last, 2),
        "reasons": (good if score > 0 else bad if score < 0 else good + bad),
        "against": (bad if score > 0 else good if score < 0 else []),
        "cautions": cautions,
    }
