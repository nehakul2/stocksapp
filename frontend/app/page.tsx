"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, AttentionItem, OverviewRow, SMA_WINDOWS } from "@/lib/api";
import { arrow, dirOf, earningsLabel, fmtNum, fmtSigned, venue } from "@/lib/format";
import { useWatchlist } from "@/lib/watchlist";

const REFRESH_MS = 2 * 60 * 1000;

function dayChange(r: OverviewRow) {
  if (r.close == null || r.prev_close == null || r.prev_close === 0) return null;
  return ((r.close - r.prev_close) / r.prev_close) * 100;
}

export default function Home() {
  const { tickers, ready, remove } = useWatchlist();
  const [rows, setRows] = useState<OverviewRow[]>([]);
  const [attention, setAttention] = useState<AttentionItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    if (!tickers.length) { setRows([]); setAttention([]); setLoading(false); return; }
    try {
      const [o, a] = await Promise.all([api.overview(tickers), api.attention(tickers)]);
      // keep the user's watchlist order
      const byTicker = new Map(o.rows.map((r) => [r.ticker, r]));
      setRows(tickers.map((t) => byTicker.get(t.toUpperCase()) ?? o.rows.find((r) => r.ticker === t)).filter(Boolean) as OverviewRow[]);
      setAttention(a.items);
      setError("");
      setUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, [tickers]);

  useEffect(() => { if (ready) load(); }, [ready, load]);
  useEffect(() => {
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const changeFor = (t: string) => {
    const row = rows.find((r) => r.ticker === t);
    return row ? dayChange(row) : null;
  };

  return (
    <>
      <section aria-labelledby="brief-h">
        <h2 id="brief-h" style={{ fontFamily: "var(--serif)", fontSize: "2rem", letterSpacing: "-0.02em" }}>Worth a look today</h2>
        <p className="sub">
          {loading ? "Checking your watchlist…" : `${attention.length} of ${tickers.length} on your watchlist.`}
          {updated && <> Updated {updated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}. <button onClick={load} style={{ background: "none", border: 0, padding: 0, textDecoration: "underline", color: "var(--ink-2)" }}>Refresh</button></>}
        </p>
        {error && <p className="msg err" role="alert">{error}</p>}
        {!error && !loading && attention.length === 0 && (
          <p className="empty">Nothing unusual right now: no big moves, volume spikes, key-level crosses or earnings close by.</p>
        )}
        {attention.length > 0 && (
          <ul className="brief">
            {attention.slice(0, 8).map((a) => {
              const ch = changeFor(a.ticker);
              const d = dirOf(ch);
              return (
                <li key={a.ticker}>
                  <div className="who">
                    <Link href={`/stock/${encodeURIComponent(a.ticker)}`}>{a.ticker}</Link>
                    {ch !== null && <span className={`chg num ${d}`}>{arrow(d)} {fmtSigned(ch, 2, "%")}</span>}
                  </div>
                  <ul className="why">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="section" aria-labelledby="watch-h">
        <h2 id="watch-h">Watchlist</h2>
        <p className="sub">Open a row for the full story. Add stocks with the search box above.</p>
        {!tickers.length ? (
          <p className="empty">Your watchlist is empty. Search for a company above, open it, and choose Add to watchlist.</p>
        ) : (
          <div className="scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Ticker</th><th className="l">Exchange</th><th>Close</th><th>Day</th>
                  {SMA_WINDOWS.map((w) => <th key={w}>SMA {w}</th>)}
                  <th>Earnings</th><th aria-label="Remove" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  if (r.error) {
                    return (
                      <tr key={r.ticker}>
                        <td><Link className="tk" href={`/stock/${encodeURIComponent(r.ticker)}`}>{r.ticker}</Link></td>
                        <td colSpan={9} className="l err">Couldn&rsquo;t load this one. Check the symbol or try again in a minute.</td>
                        <td className="last"><button className="rm" aria-label={`Remove ${r.ticker}`} onClick={() => remove(r.ticker)}>{"✕"}</button></td>
                      </tr>
                    );
                  }
                  const ch = dayChange(r);
                  const d = dirOf(ch);
                  return (
                    <tr key={r.ticker}>
                      <td><Link className="tk" href={`/stock/${encodeURIComponent(r.ticker)}`}>{r.ticker}</Link></td>
                      <td className="l muted">{venue(r.ticker, r.exchange)}</td>
                      <td>{fmtNum(r.close)}</td>
                      <td className={d}>{arrow(d)} {fmtSigned(ch, 2, "%")}</td>
                      {SMA_WINDOWS.map((w) => <td key={w}>{fmtNum(r[`sma_${w}` as const])}</td>)}
                      <td>{earningsLabel(r.next_earnings)}</td>
                      <td className="last"><button className="rm" aria-label={`Remove ${r.ticker} from watchlist`} onClick={() => remove(r.ticker)}>{"✕"}</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
