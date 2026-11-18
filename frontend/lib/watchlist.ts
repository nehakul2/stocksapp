"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API } from "@/lib/api";
import { authHeader, useAuth } from "@/lib/auth";

const KEY = "watchlist.v1";
const DEFAULT = ["^GSPC", "^DJI", "^IXIC"];

const readLocal = (): string[] | null => {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
};
const writeLocal = (t: string[]) => { try { localStorage.setItem(KEY, JSON.stringify(t)); } catch { /* ignore */ } };

async function fetchServer(token: string): Promise<string[]> {
  const res = await fetch(`${API}/api/watchlist`, { headers: authHeader(token), cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()).tickers;
}
async function saveServer(token: string, tickers: string[]): Promise<void> {
  await fetch(`${API}/api/watchlist`, {
    method: "PUT",
    headers: { ...authHeader(token), "Content-Type": "application/json" },
    body: JSON.stringify({ tickers }),
  });
}

// Signed in: the watchlist lives in your account (works on any device).
// Signed out: it stays in this browser, as before. The first time you sign in with an
// empty account, the list from this browser is copied into it.
export function useWatchlist() {
  const { token, ready: authReady } = useAuth();
  const [tickers, setTickers] = useState<string[]>(DEFAULT);
  const [ready, setReady] = useState(false);
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;

  useEffect(() => {
    if (!authReady) return;
    let cancelled = false;
    (async () => {
      if (!token) {
        if (!cancelled) { setTickers(readLocal() ?? DEFAULT); setReady(true); }
        return;
      }
      try {
        const server = await fetchServer(token);
        if (cancelled) return;
        if (server.length === 0) {
          const local = readLocal() ?? DEFAULT; // first sign-in: bring this browser's list along
          setTickers(local);
          await saveServer(token, local);
        } else {
          setTickers(server);
        }
      } catch {
        if (!cancelled) setTickers(readLocal() ?? DEFAULT);
      }
      if (!cancelled) setReady(true);
    })();
    return () => { cancelled = true; };
  }, [token, authReady]);

  const save = useCallback((next: string[]) => {
    setTickers(next);
    const t = tokenRef.current;
    if (t) saveServer(t, next).catch(() => { /* next change retries */ });
    else writeLocal(next);
  }, []);

  const add = useCallback((t: string) => save(tickers.includes(t) ? tickers : [...tickers, t]), [tickers, save]);
  const remove = useCallback((t: string) => save(tickers.filter((x) => x !== t)), [tickers, save]);

  return { tickers, ready, add, remove };
}
