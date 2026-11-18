"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, SearchHit } from "@/lib/api";
import { useAlerts } from "@/lib/alerts";
import { useAuth } from "@/lib/auth";

type Pref = "system" | "light" | "dark";

function applyTheme(pref: Pref) {
  const dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export default function Header() {
  const router = useRouter();
  const { user, ready: authReady, signOut } = useAuth();
  const { check } = useAlerts();
  const firingCount = check?.firing.length ?? 0;
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [pref, setPref] = useState<Pref>("system");
  const [cb, setCb] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPref((localStorage.getItem("theme") as Pref) || "system");
    setCb(localStorage.getItem("cb") === "1");
  }, []);

  useEffect(() => {
    if (pref !== "system") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [pref]);

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    const id = setTimeout(() => {
      api.search(q.trim()).then((r) => { setHits(r.results); setOpen(true); }).catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const go = (symbol: string) => {
    setOpen(false); setQ(""); setHits([]);
    router.push(`/stock/${encodeURIComponent(symbol)}`);
  };

  const setTheme = (p: Pref) => { setPref(p); localStorage.setItem("theme", p); applyTheme(p); };
  const toggleCb = (v: boolean) => { setCb(v); localStorage.setItem("cb", v ? "1" : "0"); document.documentElement.dataset.cb = v ? "1" : "0"; };

  return (
    <header className="bar">
      <div className="wrap">
        <Link href="/" className="brand">Stock Insights</Link>
        <div className="search" ref={box}>
          <input
            aria-label="Search by company name or ticker"
            placeholder="Search a company or ticker"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && q.trim()) go(hits[0]?.symbol ?? q.trim().toUpperCase());
              if (e.key === "Escape") setOpen(false);
            }}
            onFocus={() => hits.length && setOpen(true)}
          />
          {open && hits.length > 0 && (
            <ul className="hits">
              {hits.map((h) => (
                <li key={h.symbol}>
                  <button onClick={() => go(h.symbol)}>
                    <span className="sym">{h.symbol}</span>
                    <span className="nm">{h.name}</span>
                    <span className="muted" style={{ marginLeft: "auto", fontSize: "0.8125rem" }}>{h.exchange}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="spacer" />
        {authReady && (user ? (
          <div className="acct">
            <Link href="/alerts" className="bell" aria-label={firingCount ? `Alerts, ${firingCount} firing` : "Alerts"}>
              Alerts{firingCount > 0 && <span className="badge">{firingCount}</span>}
            </Link>
            <span className="muted who" title={user.email}>{user.email}</span>
            <button className="linkish" onClick={() => { signOut(); router.push("/"); }}>Sign out</button>
          </div>
        ) : (
          <Link href="/login" className="signin">Sign in</Link>
        ))}
        <details className="display">
          <summary>Display</summary>
          <div className="panel">
            <fieldset>
              <legend>Theme</legend>
              {(["system", "light", "dark"] as Pref[]).map((p) => (
                <label key={p}>
                  <input type="radio" name="theme" checked={pref === p} onChange={() => setTheme(p)} />
                  {p[0].toUpperCase() + p.slice(1)}
                </label>
              ))}
            </fieldset>
            <label>
              <input type="checkbox" checked={cb} onChange={(e) => toggleCb(e.target.checked)} />
              Color-blind-friendly colors
            </label>
          </div>
        </details>
      </div>
    </header>
  );
}
