"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertRule, AlertType, api, SMA_WINDOWS } from "@/lib/api";
import { useAlerts } from "@/lib/alerts";
import { useAuth } from "@/lib/auth";
import { useWatchlist } from "@/lib/watchlist";

const TYPES: { value: AlertType; label: string }[] = [
  { value: "price_above", label: "Price goes above" },
  { value: "price_below", label: "Price goes below" },
  { value: "sma_cross_above", label: "Price crosses above the average" },
  { value: "sma_cross_below", label: "Price crosses below the average" },
];

// Alerts for one stock on the watchlist you are looking at. In-app only for now:
// they show in the bell at the top and on the Alerts page.
export default function AlertsPanel({ ticker }: { ticker: string }) {
  const { token } = useAuth();
  const { lists, activeId, tickers, add, signedIn } = useWatchlist();
  const { check, refresh } = useAlerts();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [type, setType] = useState<AlertType>("price_above");
  const [value, setValue] = useState("");
  const [sma, setSma] = useState<number>(50);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const listName = lists.find((l) => l.id === activeId)?.name ?? "";
  const onList = tickers.includes(ticker);
  const isPrice = type.startsWith("price_");

  const load = useCallback(() => {
    if (!token || !signedIn || activeId == null || !onList) { setRules([]); return; }
    api.alerts(token, activeId).then((r) => setRules(r.alerts.filter((a) => a.ticker === ticker))).catch(() => setRules([]));
  }, [token, signedIn, activeId, onList, ticker]);

  useEffect(load, [load]);

  if (!token || !signedIn) {
    return <p className="fine"><Link href="/login">Sign in</Link> to set alerts. They tell you when a price passes a level or crosses a moving average.</p>;
  }
  if (!onList) {
    return (
      <p className="fine">
        Alerts belong to a watchlist. <button className="linkish" onClick={() => add(ticker)}>Add {ticker} to &ldquo;{listName}&rdquo;</button> to set one.
      </p>
    );
  }

  const firingIds = new Set((check?.firing ?? []).map((f) => f.alert_id));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!token || activeId == null) return;
    setErr(""); setBusy(true);
    try {
      await api.addAlert(token, activeId, ticker, type, isPrice ? Number(value) : sma);
      setValue("");
      load(); refresh();
    } catch (x) { setErr(x instanceof Error ? x.message : "Something went wrong."); } finally { setBusy(false); }
  }

  async function remove(id: number) {
    if (!token) return;
    await api.deleteAlert(token, id).catch(() => undefined);
    load(); refresh();
  }

  return (
    <div className="alertpanel">
      <p className="sub">On your &ldquo;{listName}&rdquo; watchlist. Alerts show in the bell at the top of the page and on the <Link href="/alerts">Alerts page</Link>.</p>
      {rules.length === 0 ? <p className="fine" style={{ marginTop: 0 }}>No alerts on {ticker} yet.</p> : (
        <ul className="rules">
          {rules.map((r) => (
            <li key={r.id}>
              <span>{r.label}{firingIds.has(r.id) && <span className="tag warn" style={{ marginLeft: 10, marginTop: 0 }}>Firing now</span>}</span>
              <button className="rm" aria-label={`Remove alert: ${r.label}`} onClick={() => remove(r.id)}>{"✕"}</button>
            </li>
          ))}
        </ul>
      )}
      <form className="alertform" onSubmit={submit}>
        <select aria-label="Alert type" value={type} onChange={(e) => setType(e.target.value as AlertType)}>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        {isPrice ? (
          <input aria-label="Price level" inputMode="decimal" placeholder="Price, for example 150" value={value}
            onChange={(e) => setValue(e.target.value)} />
        ) : (
          <select aria-label="Moving average" value={sma} onChange={(e) => setSma(Number(e.target.value))}>
            {SMA_WINDOWS.map((w) => <option key={w} value={w}>{w}-day average</option>)}
          </select>
        )}
        <button type="submit" className="go" disabled={busy || (isPrice && !(Number(value) > 0))}>Add alert</button>
      </form>
      {err && <p className="msg err" role="alert">{err}</p>}
    </div>
  );
}
