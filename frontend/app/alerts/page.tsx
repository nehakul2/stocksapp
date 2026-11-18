"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertEvent, api } from "@/lib/api";
import { useAlerts } from "@/lib/alerts";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";

export default function AlertsPage() {
  const { token, ready } = useAuth();
  const { check, loading, refresh } = useAlerts();
  const [events, setEvents] = useState<AlertEvent[]>([]);

  const loadHistory = useCallback(() => {
    if (!token) return;
    api.alertHistory(token).then((r) => setEvents(r.events)).catch(() => setEvents([]));
  }, [token]);

  useEffect(loadHistory, [loadHistory, check]);

  if (!ready) return null;
  if (!token) {
    return (
      <>
        <h1 className="hero" style={{ maxWidth: "none" }}>Alerts</h1>
        <p className="empty"><Link href="/login">Sign in</Link> to set alerts on your watchlists and see them here.</p>
      </>
    );
  }

  const firing = check?.firing ?? [];

  async function clear() {
    if (!token) return;
    await api.clearAlertHistory(token).catch(() => undefined);
    loadHistory();
  }

  return (
    <>
      <Link href="/" className="crumb">&larr; Watchlist</Link>
      <h1 className="hero" style={{ maxWidth: "none" }}>Alerts</h1>
      <p className="sub">
        Checked when you open the app and every few minutes while it is open.{" "}
        <button className="linkish" onClick={refresh} disabled={loading}>{loading ? "Checking…" : "Check now"}</button>
      </p>

      <section className="section" aria-label="Firing now">
        <h2>Firing now</h2>
        {check === null ? <p className="skel">Checking your alerts&hellip;</p>
          : check.checked === 0 ? <p className="empty">You have no alerts yet. Open a stock on your watchlist and add one under Alerts.</p>
          : firing.length === 0 ? <p className="empty">Nothing is firing right now. {check.checked} {check.checked === 1 ? "alert is" : "alerts are"} being watched.</p>
          : (
            <ul className="firing">
              {firing.map((f) => (
                <li key={f.alert_id}>
                  <Link className="tk" href={`/stock/${encodeURIComponent(f.ticker)}`}>{f.ticker}</Link>
                  <span>{f.message.replace(`${f.ticker}: `, "")}</span>
                  <span className="muted">{f.watchlist}</span>
                </li>
              ))}
            </ul>
          )}
        {check && check.unavailable.length > 0 && (
          <p className="fine">Couldn&rsquo;t check alerts for {check.unavailable.join(", ")} just now. Yahoo Finance may be slow; try again in a minute.</p>
        )}
      </section>

      <section className="section" aria-label="History">
        <h2>History</h2>
        {events.length === 0 ? <p className="empty">Alerts that fire will be listed here, one line per day.</p> : (
          <>
            <div className="scroll">
              <table className="ledger" style={{ minWidth: 520 }}>
                <thead><tr><th className="l">Date</th><th className="l">Stock</th><th className="l">What happened</th><th className="l">Watchlist</th></tr></thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id}>
                      <td className="l">{fmtDate(e.day)}</td>
                      <td className="l"><Link className="tk" href={`/stock/${encodeURIComponent(e.ticker)}`}>{e.ticker}</Link></td>
                      <td className="l" style={{ whiteSpace: "normal" }}>{e.message.replace(`${e.ticker}: `, "")}</td>
                      <td className="l muted">{e.watchlist}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="fine"><button className="linkish" onClick={clear}>Clear history</button></p>
          </>
        )}
      </section>
    </>
  );
}
