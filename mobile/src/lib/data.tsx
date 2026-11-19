import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertCheck, api, ChatAction, WatchlistDto } from "@/lib/api";
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
  // These return an error message to show, or null on success.
  createList: (name: string) => Promise<string | null>;
  renameList: (id: number, name: string) => Promise<string | null>;
  deleteList: (id: number) => Promise<string | null>;
  // Carries out one change the chat proposed and the person confirmed.
  runAction: (a: ChatAction) => Promise<string | null>;
};

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

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
    createList: async (name) => {
      if (!token) return "Sign in first.";
      try { const wl = await api.createWatchlist(token, name); setLists((ls) => [...ls, wl]); setActiveId(wl.id); return null; }
      catch (e) { return msg(e); }
    },
    renameList: async (id, name) => {
      if (!token) return "Sign in first.";
      try { const wl = await api.renameWatchlist(token, id, name); setLists((ls) => ls.map((l) => (l.id === id ? { ...l, name: wl.name } : l))); return null; }
      catch (e) { return msg(e); }
    },
    runAction: async (a) => {
      if (!token) return "Sign in first.";
      try {
        if (a.type === "create_list") {
          const wl = await api.createWatchlist(token, a.name ?? "");
          let tk: string[] = [];
          if (a.tickers?.length) tk = (await api.saveTickers(token, wl.id, a.tickers)).tickers;
          setLists((ls) => [...ls, { ...wl, tickers: tk }]);
          return null;
        }
        const target = lists.find((l) => l.id === a.list_id);
        if (!target) return "That watchlist no longer exists.";
        if (a.type === "rename_list") {
          const wl = await api.renameWatchlist(token, target.id, a.new_name ?? "");
          setLists((ls) => ls.map((l) => (l.id === target.id ? { ...l, name: wl.name } : l)));
          return null;
        }
        const wanted = a.tickers ?? [];
        const next = a.type === "add_to_list"
          ? [...target.tickers, ...wanted.filter((x) => !target.tickers.includes(x))]
          : target.tickers.filter((x) => !wanted.includes(x));
        const saved = await api.saveTickers(token, target.id, next);
        setLists((ls) => ls.map((l) => (l.id === target.id ? { ...l, tickers: saved.tickers } : l)));
        if (a.type === "remove_from_list") refreshAlerts();
        return null;
      } catch (e) { return msg(e); }
    },
    deleteList: async (id) => {
      if (!token) return "Sign in first.";
      try {
        const r = await api.deleteWatchlist(token, id);
        setLists(r.watchlists);
        setActiveId((cur) => (cur === id ? r.watchlists[0]?.id ?? null : cur));
        refreshAlerts();
        return null;
      } catch (e) { return msg(e); }
    },
    add: async (t) => { const s = t.trim().toUpperCase(); if (s && !tickers.includes(s)) await save([...tickers, s]); },
    remove: async (t) => { await save(tickers.filter((x) => x !== t)); await refreshAlerts(); },
  }), [lists, activeId, tickers, check, reloadLists, refreshAlerts, save, token, lists]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData must be used inside DataProvider");
  return v;
}
