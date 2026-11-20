"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Ideas } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ideaText } from "@/lib/ideas";
import { useWatchlist } from "@/lib/watchlist";

export default function Suggestions() {
  const { tickers, ready, activeId, lists } = useWatchlist();
  const { token } = useAuth();
  const [data, setData] = useState<Ideas | null>(null);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [sumErr, setSumErr] = useState("");

  const key = tickers.join(",");
  useEffect(() => {
    setSummary(""); setSumErr("");
    if (!ready || !tickers.length) { setData(null); setError(""); return; }
    let cancelled = false;
    setData(null); setError("");
    api.suggestions(tickers)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Something went wrong."); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, key]);

  async function summarise() {
    if (!token || activeId == null) return;
    setBusy(true); setSumErr("");
    try { setSummary((await api.suggestionSummary(token, activeId)).summary); }
    catch (e) { setSumErr(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }

  if (!ready || !tickers.length) return null;
  const listName = lists.find((l) => l.id === activeId)?.name ?? "this watchlist";

  return (
    <section className="section" aria-labelledby="ideas-h">
      <h2 id="ideas-h">Ideas for {listName}</h2>
      <p className="sub">Buy, hold or sell ideas from simple price-trend rules. Open a stock to see why.</p>
      {error && <p className="msg err" role="alert">{error}</p>}
      {!error && !data && <p className="skel">Reading the trends&hellip;</p>}
      {data && (
        <>
          <ul className="ideas">
            {data.items.map((i) => (
              <li key={i.ticker}>
                <Link className="tk" href={`/stock/${encodeURIComponent(i.ticker)}`}>{i.ticker}</Link>
                <span className={`tag idea-${i.action}`}>{ideaText(i)}</span>
                <span className="muted">{i.reasons[0] ?? ""}</span>
              </li>
            ))}
          </ul>
          {data.unavailable.length > 0 && <p className="fine">No idea for {data.unavailable.join(", ")}: not enough price history, or the data didn&rsquo;t load.</p>}
          <div className="ai">
            {token ? (
              <p className="fine" style={{ marginTop: 14 }}>
                <button className="go" onClick={summarise} disabled={busy}>{busy ? "Writing…" : "Summarise this watchlist"}</button>
                {" "}Uses one of your daily AI explanations.
              </p>
            ) : (
              <p className="fine"><Link href="/login">Sign in</Link> to get a short AI summary of this watchlist.</p>
            )}
            {summary && <p className="msg" style={{ fontFamily: "var(--serif)", fontSize: "1.0625rem", lineHeight: 1.55, maxWidth: "68ch" }}>{summary}</p>}
            {sumErr && <p className="msg err" role="alert">{sumErr}</p>}
          </div>
          <p className="fine">{data.disclaimer}</p>
        </>
      )}
    </section>
  );
}
