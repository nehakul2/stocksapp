import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertCheck, api, WatchlistDto } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const EVERY_MS = 5 * 60 * 1000;

type DataState = {
  lists: WatchlistDto[];
  activeId: number | null;
  tickers: string[];
  setActive: (id: number) => void;
  add: (ticker: string) => Promise<void>;
  remove: (ticker: string) => Promise<void>;
  reloadLists: () => Promise<void>;
  check: AlertCheck | null;
  refreshAlerts: () => Promise<void>;
};

const Ctx = createContext<DataState | null>(null);

// Your watchlists and the alert check, shared by every screen. Alerts are re-checked when the
// app opens and every few minutes while it is open.
export function DataProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [lists, setLists] = useState<WatchlistDto[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [check, setCheck] = useState<AlertCheck | null>(null);

  const reloadLists = useCallback(async () => {
    if (!token) { setLists([]); setActiveId(null); return; }
    try {
      const r = await api.watchlists(token);
      setLists(r.watchlists);
      setActiveId((cur) => (cur != null && r.watchlists.some((l) => l.id === cur) ? cur : r.watchlists[0]?.id ?? null));
    } catch { /* keep what we have */ }
  }, [token]);

  const refreshAlerts = useCallback(async () => {
    if (!token) { setCheck(null); return; }
    try { setCheck(await api.checkAlerts(token)); } catch { /* keep the last result */ }
  }, [token]);

  useEffect(() => { reloadLists(); }, [reloadLists]);
  useEffect(() => {
    refreshAlerts();
    if (!token) return;
    const id = setInterval(refreshAlerts, EVERY_MS);
    return () => clearInterval(id);
  }, [token, refreshAlerts]);

  const tickers = useMemo(() => lists.find((l) => l.id === activeId)?.tickers ?? [], [lists, activeId]);

  const save = useCallback(async (next: string[]) => {
    if (!token || activeId == null) return;
    const saved = await api.saveTickers(token, activeId, next);
    setLists((ls) => ls.map((l) => (l.id === activeId ? { ...l, tickers: saved.tickers } : l)));
  }, [token, activeId]);

  const value = useMemo<DataState>(() => ({
    lists, activeId, tickers, check, reloadLists, refreshAlerts,
    setActive: setActiveId,
    add: async (t) => { const s = t.trim().toUpperCase(); if (s && !tickers.includes(s)) await save([...tickers, s]); },
    remove: async (t) => { await save(tickers.filter((x) => x !== t)); await refreshAlerts(); },
  }), [lists, activeId, tickers, check, reloadLists, refreshAlerts, save]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData must be used inside DataProvider");
  return v;
}
