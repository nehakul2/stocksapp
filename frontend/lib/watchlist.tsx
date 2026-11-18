"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, WatchlistDto } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const KEY = "watchlist.v1";
const ACTIVE_KEY = "watchlist.active";
const DEFAULT = ["^GSPC", "^DJI", "^IXIC"];

const readLocal = (): string[] | null => {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
};
const writeLocal = (t: string[]) => { try { localStorage.setItem(KEY, JSON.stringify(t)); } catch { /* ignore */ } };
const readActive = (): number | null => {
  try { const v = localStorage.getItem(ACTIVE_KEY); return v ? Number(v) : null; } catch { return null; }
};
const writeActive = (id: number) => { try { localStorage.setItem(ACTIVE_KEY, String(id)); } catch { /* ignore */ } };

type WatchlistState = {
  tickers: string[];            // tickers of the active watchlist
  lists: WatchlistDto[];        // all watchlists (one, unnamed, when signed out)
  activeId: number | null;
  signedIn: boolean;
  ready: boolean;
  add: (t: string) => void;
  remove: (t: string) => void;
  setActive: (id: number) => void;
  // These return an error message to show, or null on success.
  createList: (name: string) => Promise<string | null>;
  renameList: (id: number, name: string) => Promise<string | null>;
  deleteList: (id: number) => Promise<string | null>;
};

const Ctx = createContext<WatchlistState | null>(null);

// Signed in: watchlists live in your account (any device), and you can keep several.
// Signed out: one list stays in this browser. A new account starts with the default
// list; nothing is copied over from the browser, so shared computers don't leak lists.
export function WatchlistProvider({ children }: { children: React.ReactNode }) {
  const { token, ready: authReady } = useAuth();
  const [lists, setLists] = useState<WatchlistDto[]>([{ id: 0, name: "Watchlist", tickers: DEFAULT }]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;

  useEffect(() => {
    if (!authReady) return;
    let cancelled = false;
    (async () => {
      if (!token) {
        if (!cancelled) { setLists([{ id: 0, name: "Watchlist", tickers: readLocal() ?? DEFAULT }]); setActiveId(0); setReady(true); }
        return;
      }
      try {
        let { watchlists } = await api.watchlists(token);
        if (cancelled) return;
        if (watchlists.length === 1 && watchlists[0].tickers.length === 0) {
          // brand-new account: start with the default list
          await api.saveTickers(token, watchlists[0].id, DEFAULT);
          watchlists = [{ ...watchlists[0], tickers: DEFAULT }];
        }
        const saved = readActive();
        setLists(watchlists);
        setActiveId(watchlists.some((w) => w.id === saved) ? saved : watchlists[0].id);
      } catch {
        if (!cancelled) { setLists([{ id: 0, name: "Watchlist", tickers: readLocal() ?? DEFAULT }]); setActiveId(0); }
      }
      if (!cancelled) setReady(true);
    })();
    return () => { cancelled = true; };
  }, [token, authReady]);

  const active = lists.find((w) => w.id === activeId) ?? lists[0];
  const tickers = active.tickers;

  const saveTickers = useCallback((next: string[]) => {
    const id = active.id;
    setLists((ls) => ls.map((w) => (w.id === id ? { ...w, tickers: next } : w)));
    const t = tokenRef.current;
    if (t && id !== 0) api.saveTickers(t, id, next).catch(() => { /* next change retries */ });
    else writeLocal(next);
  }, [active.id]);

  const add = useCallback((t: string) => saveTickers(tickers.includes(t) ? tickers : [...tickers, t]), [tickers, saveTickers]);
  const remove = useCallback((t: string) => saveTickers(tickers.filter((x) => x !== t)), [tickers, saveTickers]);

  const setActive = useCallback((id: number) => { setActiveId(id); writeActive(id); }, []);

  const createList = useCallback(async (name: string) => {
    const t = tokenRef.current;
    if (!t) return "Sign in to keep more than one watchlist.";
    try {
      const wl = await api.createWatchlist(t, name);
      setLists((ls) => [...ls, wl]);
      setActive(wl.id);
      return null;
    } catch (e) { return e instanceof Error ? e.message : "Something went wrong."; }
  }, [setActive]);

  const renameList = useCallback(async (id: number, name: string) => {
    const t = tokenRef.current;
    if (!t) return "Sign in to rename watchlists.";
    try {
      const wl = await api.renameWatchlist(t, id, name);
      setLists((ls) => ls.map((w) => (w.id === id ? { ...w, name: wl.name } : w)));
      return null;
    } catch (e) { return e instanceof Error ? e.message : "Something went wrong."; }
  }, []);

  const deleteList = useCallback(async (id: number) => {
    const t = tokenRef.current;
    if (!t) return "Sign in to manage watchlists.";
    try {
      const r = await api.deleteWatchlist(t, id);
      setLists(r.watchlists);
      if (activeId === id) setActive(r.watchlists[0].id);
      return null;
    } catch (e) { return e instanceof Error ? e.message : "Something went wrong."; }
  }, [activeId, setActive]);

  const value = useMemo<WatchlistState>(() => ({
    tickers, lists, activeId: active.id, signedIn: !!token && active.id !== 0, ready,
    add, remove, setActive, createList, renameList, deleteList,
  }), [tickers, lists, active.id, token, ready, add, remove, setActive, createList, renameList, deleteList]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWatchlist(): WatchlistState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWatchlist must be used inside WatchlistProvider");
  return v;
}
