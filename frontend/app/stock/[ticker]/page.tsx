"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import PriceChart, { ChartType, SMA_VARS } from "@/components/PriceChart";
import { api, Bar, Detail, SMA_WINDOWS } from "@/lib/api";
import { arrow, daysUntil, dirOf, earningsLabel, fmtDate, fmtNum, fmtSigned, venue } from "@/lib/format";
import { useWatchlist } from "@/lib/watchlist";

const RANGES = ["1mo", "6mo", "1y", "5y"] as const;
const RANGE_LABEL: Record<string, string> = { "1mo": "1M", "6mo": "6M", "1y": "1Y", "5y": "5Y" };
const TYPES: ChartType[] = ["Candles", "Line", "Area"];

function heroText(d: Detail): string {
  const pct = d.explanation.pct_change;
  const name = d.summary.name || d.summary.ticker;
  if (pct === null) return name;
  if (Math.abs(pct) < 0.005) return `${name} was flat.`;

  const size = d.explanation.magnitude.replace(/^an? /, "a ").replace("small, unremarkable", "small");
  let tail = "";
  const days = daysUntil(d.next_earnings);
  if (days !== null && days >= -1 && days <= 2) {
    const when = earningsLabel(d.next_earnings);
    tail = when === fmtDate(d.next_earnings) ? `, with earnings on ${when}` : `, with earnings ${when.toLowerCase()}`;
  }
  return `${name} ${pct > 0 ? "rose" : "fell"} ${Math.abs(pct).toFixed(2)}% \u2014 ${size}${tail}.`;
}

export default function StockPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker);
  const { tickers, add, remove } = useWatchlist();

  const [range, setRange] = useState<(typeof RANGES)[number]>("6mo");
  const [type, setType] = useState<ChartType>("Candles");
  const [smaOn, setSmaOn] = useState<Record<number, boolean>>({ 5: false, 20: true, 50: true, 100: false, 200: false });

  const [detail, setDetail] = useState<Detail | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const [aiKey, setAiKey] = useState("");
  const [aiText, setAiText] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState("");

  useEffect(() => { setAiKey(localStorage.getItem("anthropic_key") ?? ""); }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setAiText("");
    Promise.all([api.detail(ticker, range), api.history(ticker, range)])
      .then(([d, h]) => { if (!cancelled) { setDetail(d); setBars(h.bars); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Something went wrong."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, range]);

  const symbol = detail?.summary.ticker ?? ticker.toUpperCase();
  const watching = tickers.includes(symbol) || tickers.includes(ticker.toUpperCase());

  const change = useMemo(() => {
    if (!detail?.previous_day) return null;
    return detail.summary.price - detail.previous_day.close;
  }, [detail]);

  async function explain() {
    setAiBusy(true); setAiErr(""); setAiText("");
    try {
      localStorage.setItem("anthropic_key", aiKey.trim());
      setAiText(await api.aiSummary(ticker, aiKey.trim()));
    } catch (e) {
      setAiErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setAiBusy(false);
    }
  }

  if (error) {
    return (
      <>
        <Link href="/" className="crumb">&larr; Watchlist</Link>
        <p className="msg err" role="alert">{error}</p>
        <p className="msg">Check the symbol, or try again in a minute. Yahoo Finance sometimes slows down requests.</p>
      </>
    );
  }
  if (loading && !detail) return <p className="skel">Loading {ticker.toUpperCase()}&hellip;</p>;
  if (!detail) return null;

  const s = detail.summary;
  const e = detail.explanation;
  const d = dirOf(e.pct_change);
  const notes = [e.market_note, e.volume_note, e.earnings_note].filter(Boolean);
  const hi = s.high_52wk, lo = s.low_52wk;
  const pos = hi != null && lo != null && hi > lo ? Math.min(100, Math.max(0, ((s.price - lo) / (hi - lo)) * 100)) : null;
  const afterHours = s.post_market_price != null ? { label: "After hours", price: s.post_market_price, pct: s.post_market_change_pct }
    : s.pre_market_price != null ? { label: "Pre-market", price: s.pre_market_price, pct: s.pre_market_change_pct } : null;

  return (
    <>
      <Link href="/" className="crumb">&larr; Watchlist</Link>

      <div className="id">
        <div className="nm"><b>{s.ticker}</b>{` · ${venue(s.ticker, s.exchange)}`}</div>
        <button
          className="watchbtn" aria-pressed={watching}
          onClick={() => (watching ? remove(symbol) : add(symbol))}
        >{watching ? "✓ On your watchlist" : "Add to watchlist"}</button>
      </div>

      <h1 className="hero">{heroText(detail)}</h1>

      <div className="priceline num">
        <span className="big">{fmtNum(s.price)} <span className="muted" style={{ fontSize: "1rem", fontWeight: 400 }}>{s.currency}</span></span>
        {change !== null && (
          <span className={d}>{arrow(d)} {fmtSigned(change)} ({fmtSigned(e.pct_change, 2, "%")}) today</span>
        )}
        {afterHours && (
          <span className="ah">
            {afterHours.label} {fmtNum(afterHours.price)}
            {afterHours.pct != null && <> <span className={dirOf(afterHours.pct)}>{arrow(dirOf(afterHours.pct))} {fmtSigned(afterHours.pct, 2, "%")}</span></>}
          </span>
        )}
      </div>

      <section className="section" aria-label="Price chart">
        <div className="controls">
          <div className="seg" role="group" aria-label="Chart type">
            {TYPES.map((t) => <button key={t} aria-pressed={type === t} onClick={() => setType(t)}>{t}</button>)}
          </div>
          <div className="seg" role="group" aria-label="Time range">
            {RANGES.map((r) => <button key={r} aria-pressed={range === r} onClick={() => setRange(r)}>{RANGE_LABEL[r]}</button>)}
          </div>
        </div>
        <div className="chips" role="group" aria-label="Moving averages" style={{ marginBottom: 14 }}>
          {SMA_WINDOWS.map((w) => (
            <button key={w} className="chip" aria-pressed={!!smaOn[w]} onClick={() => setSmaOn({ ...smaOn, [w]: !smaOn[w] })}>
              <span className="sw" style={{ background: `var(${SMA_VARS[w]})` }} />
              <span>SMA {w}</span>
              <span className="v">{fmtNum(detail.smas[String(w)])}</span>
            </button>
          ))}
        </div>
        {bars.length > 0 ? <PriceChart bars={bars} type={type} smas={smaOn} /> : <p className="skel">No chart data.</p>}
        <p className="chartnote">Hover the chart for exact values. Click an average above to show or hide it. A simple moving average is the average closing price over that many trading days.</p>
      </section>

      <details className="why section" open>
        <summary><h2>Why it moved</h2></summary>
        <div className="whybody">
          {notes.length > 0
            ? <ul className="notes">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            : <p className="fine">No unusual volume, earnings timing or market gap behind today&rsquo;s move. It looks like routine movement.</p>}
          {e.headlines.length > 0 && (
            <div className="related">
              <h3>Headlines that may be related. These are recent stories, not confirmed causes.</h3>
              <ul>
                {e.headlines.map((n, i) => (
                  <li key={i}>
                    {n.link ? <a href={n.link} target="_blank" rel="noopener noreferrer">{n.title}</a> : n.title}
                    <span className="pub">{n.publisher}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>

      <section className="section" aria-label="Key figures">
        <div className="facts">
          <div>
            <h3>52-week range</h3>
            {pos !== null && (
              <>
                <div className="range" aria-hidden><i style={{ left: `${pos}%` }} /></div>
                <div className="rangeLabels"><span>{fmtNum(lo)}</span><span>{fmtNum(hi)}</span></div>
              </>
            )}
            <dl className="rows" style={{ marginTop: 14 }}>
              <div><dt>Low</dt><dd>{fmtNum(lo)}</dd></div>
              <div><dt>High</dt><dd>{fmtNum(hi)}</dd></div>
              <div><dt>Next earnings</dt><dd>{detail.next_earnings ? `${earningsLabel(detail.next_earnings)}${earningsLabel(detail.next_earnings) === fmtDate(detail.next_earnings) ? "" : ` (${fmtDate(detail.next_earnings)})`}` : "—"}</dd></div>
            </dl>
          </div>

          {detail.previous_day && (
            <div>
              <h3>Previous trading day, {fmtDate(detail.previous_day.date)}</h3>
              <dl className="rows">
                <div><dt>Open</dt><dd>{fmtNum(detail.previous_day.open)}</dd></div>
                <div><dt>High</dt><dd>{fmtNum(detail.previous_day.high)}</dd></div>
                <div><dt>Low</dt><dd>{fmtNum(detail.previous_day.low)}</dd></div>
                <div><dt>Close</dt><dd>{fmtNum(detail.previous_day.close)}</dd></div>
              </dl>
            </div>
          )}

          {detail.trend && (
            <div>
              <h3>Recent trend: {detail.trend.direction}</h3>
              <dl className="rows">
                <div><dt>In 1 day</dt><dd>{fmtNum(detail.trend.estimates["1_day"])}</dd></div>
                <div><dt>In 7 days</dt><dd>{fmtNum(detail.trend.estimates["7_day"])}</dd></div>
                <div><dt>In 30 days</dt><dd>{fmtNum(detail.trend.estimates["30_day"])}</dd></div>
              </dl>
              <p className="fine">These extend the last 90 days&rsquo; price slope in a straight line. They are not forecasts and ignore news and earnings. Not financial advice.</p>
            </div>
          )}
        </div>
      </section>

      <section className="section" aria-label="Plain-English summary">
        <h2>In plain English</h2>
        <div className="ai">
          <p className="sub">Turns the notes above into a short summary using Claude. It runs only when you ask, with your own Anthropic key, which stays in this browser.</p>
          <p style={{ margin: "0 0 12px" }}>
            <input type="password" aria-label="Anthropic API key" placeholder="Anthropic API key" value={aiKey} onChange={(ev) => setAiKey(ev.target.value)} />
          </p>
          <button className="go" disabled={!aiKey.trim() || aiBusy} onClick={explain}>{aiBusy ? "Writing…" : "Explain this move"}</button>
          {aiErr && <p className="msg err" role="alert">{aiErr}</p>}
          {aiText && <p className="out">{aiText}</p>}
        </div>
      </section>

      {detail.news.length > 0 && (
        <section className="section" aria-label="News">
          <h2>Recent news</h2>
          <div className="related" style={{ marginTop: 8 }}>
            <ul>
              {detail.news.map((n, i) => (
                <li key={i}>
                  {n.link ? <a href={n.link} target="_blank" rel="noopener noreferrer">{n.title}</a> : n.title}
                  <span className="pub">{n.publisher}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
