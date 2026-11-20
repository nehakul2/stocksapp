"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import AlertsPanel from "@/components/AlertsPanel";
import PriceChart, { ChartType, SMA_VARS } from "@/components/PriceChart";
import { AiResult, AiUsage, api, Bar, Detail, Idea, Peers, RiskReply, SMA_WINDOWS } from "@/lib/api";
import { arrow, daysUntil, dirOf, earningsLabel, fmtDate, fmtNum, fmtSigned, venue, fmtBig } from "@/lib/format";
import { ideaText } from "@/lib/ideas";
import { useAuth } from "@/lib/auth";
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

  const today = new Date().toISOString().slice(0, 10);
  const threeMonthsAgo = new Date(Date.now() - 91 * 86400000).toISOString().slice(0, 10);
  const [csvFrom, setCsvFrom] = useState(threeMonthsAgo);
  const [csvTo, setCsvTo] = useState(today);
  const [peers, setPeers] = useState<Peers | null>(null);
  const [peersState, setPeersState] = useState<"loading" | "ok" | "none">("loading");
  const [riskData, setRiskData] = useState<RiskReply | null>(null);
  const [riskState, setRiskState] = useState<"loading" | "ok" | "none">("loading");
  const [idea, setIdea] = useState<Idea | null>(null);
  const [ideaState, setIdeaState] = useState<"loading" | "ok" | "none">("loading");
  const [ideaNote, setIdeaNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    setIdea(null); setIdeaState("loading");
    api.suggestions([ticker])
      .then((d) => { if (cancelled) return; setIdeaNote(d.disclaimer); if (d.items[0]) { setIdea(d.items[0]); setIdeaState("ok"); } else setIdeaState("none"); })
      .catch(() => { if (!cancelled) setIdeaState("none"); });
    return () => { cancelled = true; };
  }, [ticker]);

  const { token } = useAuth();
  const [ai, setAi] = useState<AiResult | null>(null);
  const [aiUsage, setAiUsage] = useState<AiUsage | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState("");

  useEffect(() => {
    if (!token) { setAiUsage(null); return; }
    api.aiUsage(token).then(setAiUsage).catch(() => setAiUsage(null));
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setAi(null); setAiErr("");
    Promise.all([api.detail(ticker, range), api.history(ticker, range)])
      .then(([d, h]) => { if (!cancelled) { setDetail(d); setBars(h.bars); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Something went wrong."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, range]);

  useEffect(() => {
    let cancelled = false;
    setPeers(null); setPeersState("loading");
    api.peers(ticker)
      .then((p) => { if (!cancelled) { setPeers(p); setPeersState(p.rows.some((r) => r.kind === "peer") ? "ok" : "none"); } })
      .catch(() => { if (!cancelled) setPeersState("none"); });
    return () => { cancelled = true; };
  }, [ticker]);

  useEffect(() => {
    let cancelled = false;
    setRiskData(null); setRiskState("loading");
    api.risk(ticker)
      .then((r) => { if (!cancelled) { setRiskData(r); setRiskState("ok"); } })
      .catch(() => { if (!cancelled) setRiskState("none"); });
    return () => { cancelled = true; };
  }, [ticker]);

  const symbol = detail?.summary.ticker ?? ticker.toUpperCase();
  const watching = tickers.includes(symbol) || tickers.includes(ticker.toUpperCase());

  const change = useMemo(() => {
    if (!detail?.previous_day) return null;
    return detail.summary.price - detail.previous_day.close;
  }, [detail]);

  async function explain() {
    if (!token) return;
    setAiBusy(true); setAiErr(""); setAi(null);
    try {
      const r = await api.aiSummary(ticker, token);
      setAi(r);
      setAiUsage((u) => ({ enabled: true, ...(u ?? {}), ...r.usage }));
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
          <span className={`pill ${d}`}>{arrow(d)} {fmtSigned(change)} ({fmtSigned(e.pct_change, 2, "%")}) today</span>
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

      <section className="section" aria-label="How it compares">
        <h2>How it compares</h2>
        {peersState === "loading" && <p className="skel">Finding similar companies&hellip;</p>}
        {peersState === "none" && <p className="fine">No similar companies found for this one, so there is nothing to compare it with.</p>}
        {peersState === "ok" && peers && (
          <>
            <p className="sub">{peers.industry ? `Same industry (${peers.industry}), plus the S&P 500.` : "Against similar companies and the S&P 500."}</p>
            <div className="scroll">
              <table className="ledger peers">
                <thead>
                  <tr><th className="l">Company</th><th>Price</th><th>Today</th><th>1 month</th></tr>
                </thead>
                <tbody>
                  {peers.rows.map((r) => {
                    const td = dirOf(r.day_pct), tm = dirOf(r.month_pct);
                    return (
                      <tr key={r.ticker} className={r.kind === "self" ? "me" : undefined}>
                        <td className="l">
                          {r.kind === "market" ? <b>S&amp;P 500</b> : <Link className="tk" href={`/stock/${encodeURIComponent(r.ticker)}`}>{r.ticker}</Link>}
                          {r.kind === "self" && <span className="tag">This stock</span>}
                          {r.kind === "peer" && r.name && <span className="muted pn">{r.name}</span>}
                        </td>
                        <td>{fmtNum(r.price)}</td>
                        <td><span className={`pill ${td}`}>{arrow(td)} {fmtSigned(r.day_pct, 2, "%")}</span></td>
                        <td><span className={`pill ${tm}`}>{arrow(tm)} {fmtSigned(r.month_pct, 2, "%")}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {peers.peer_median_day_pct != null && (
              <p className="fine">Similar companies&rsquo; median move today: {fmtSigned(peers.peer_median_day_pct, 2, "%")}. If this stock moved far more than that, the cause is probably specific to it.</p>
            )}
          </>
        )}
      </section>

      <section className="section" aria-label="Our take">
        <h2>Our take</h2>
        {ideaState === "loading" && <p className="skel">Reading the trend&hellip;</p>}
        {ideaState === "none" && <p className="fine">No idea for this one: not enough price history, or the data didn&rsquo;t load.</p>}
        {ideaState === "ok" && idea && (
          <div className="take">
            <p style={{ margin: 0 }}><span className={`tag idea-${idea.action}`}>{ideaText(idea)}</span></p>
            {idea.reasons.length > 0 && (
              <div>
                <h3>Why</h3>
                <ul className="why">{idea.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
            {idea.against.length > 0 && (
              <div>
                <h3>Pointing the other way</h3>
                <ul className="why">{idea.against.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
            {idea.cautions.length > 0 && (
              <div>
                <h3>Be careful about</h3>
                <ul className="why">{idea.cautions.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
          </div>
        )}
        <p className="fine">{ideaNote || "These are ideas from simple price-trend rules, not advice. Use your own judgment."}</p>
      </section>

      <section className="section" aria-label="Risk and basics">
        <h2>Risk and basics</h2>
        {riskState === "loading" && <p className="skel">Working out how bumpy the past year has been&hellip;</p>}
        {riskState === "none" && <p className="fine">Risk numbers aren&rsquo;t available for this one right now.</p>}
        {riskState === "ok" && riskData && (
          <div className="facts">
            {riskData.risk && (
              <div>
                <h3>Past year: {riskData.risk.label}</h3>
                {riskData.risk.lines.map((l, i) => <p key={i} className="fine" style={{ marginTop: i ? 8 : 0 }}>{l}</p>)}
              </div>
            )}
            {riskData.fundamentals && (
              <div>
                <h3>Company basics</h3>
                <dl className="rows">
                  <div><dt>Market value</dt><dd>{fmtBig(riskData.fundamentals.market_cap)}</dd></div>
                  <div><dt>Price to earnings</dt><dd>{riskData.fundamentals.pe != null ? fmtNum(riskData.fundamentals.pe, 1) : "—"}</dd></div>
                  <div><dt>Expected price to earnings</dt><dd>{riskData.fundamentals.forward_pe != null ? fmtNum(riskData.fundamentals.forward_pe, 1) : "—"}</dd></div>
                  <div><dt>Dividend yield</dt><dd>{riskData.fundamentals.dividend_yield_pct != null ? `${fmtNum(riskData.fundamentals.dividend_yield_pct, 2)}%` : "—"}</dd></div>
                  {riskData.fundamentals.sector && <div><dt>Sector</dt><dd>{riskData.fundamentals.sector}</dd></div>}
                </dl>
              </div>
            )}
          </div>
        )}
        <p className="fine">Based on the past year&rsquo;s prices. The past is not a promise about the future. Not financial advice.</p>
      </section>

      <section className="section" aria-label="Plain-English summary">
        <h2>In plain English</h2>
        <div className="ai">
          {!token ? (
            <p className="sub"><Link href="/login">Sign in</Link> to get a short AI explanation of this move and the headlines that matter.</p>
          ) : aiUsage && !aiUsage.enabled ? (
            <p className="sub">AI explanations aren&rsquo;t switched on for this site yet.</p>
          ) : (
            <>
              <p className="sub">
                Claude turns the notes above into a short explanation and picks the headlines that bear on today&rsquo;s move.
                {aiUsage && <> You&rsquo;ve used {aiUsage.used} of {aiUsage.limit} today.</>}
              </p>
              <div className="aiactions">
                <button className="go" disabled={aiBusy || (!!aiUsage && aiUsage.used >= aiUsage.limit)} onClick={explain}>
                  {aiBusy ? "Writing…" : "Explain this move"}
                </button>
                {(ai || aiErr) && !aiBusy && (
                  <button className="clear" onClick={() => { setAi(null); setAiErr(""); }}>Clear</button>
                )}
              </div>
            </>
          )}
          {aiErr && <p className="msg err" role="alert">{aiErr}</p>}
          {ai && (
            <>
              <p className="out">{ai.summary}</p>
              {ai.headlines.length > 0 && (
                <div className="related" style={{ marginTop: 12 }}>
                  <p className="sub" style={{ margin: "0 0 4px" }}>Headlines that bear on this move</p>
                  <ul>
                    {ai.headlines.map((n, i) => (
                      <li key={i}>
                        {n.link ? <a href={n.link} target="_blank" rel="noopener noreferrer">{n.title}</a> : n.title}
                        <span className="pub">{n.publisher}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="fine">AI-written from the notes above. It can be wrong, and it is not financial advice.</p>
            </>
          )}
        </div>
      </section>

      <section className="section" aria-label="Alerts">
        <h2>Alerts</h2>
        <AlertsPanel ticker={symbol} />
      </section>

      <section className="section" aria-label="Download price history">
        <h2>Download price history</h2>
        <p className="sub">Daily open, high, low and close for the dates you choose, as a spreadsheet file.</p>
        <div className="csvrow">
          <label>From <input type="date" value={csvFrom} max={csvTo} onChange={(e) => setCsvFrom(e.target.value)} /></label>
          <label>To <input type="date" value={csvTo} min={csvFrom} max={today} onChange={(e) => setCsvTo(e.target.value)} /></label>
          <a className="btnlink" href={csvFrom && csvTo && csvFrom <= csvTo ? api.exportUrl(symbol, csvFrom, csvTo) : undefined}
             aria-disabled={!(csvFrom && csvTo && csvFrom <= csvTo)}>Download CSV</a>
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
