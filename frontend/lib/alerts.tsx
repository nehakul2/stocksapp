"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertCheck, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const EVERY_MS = 5 * 60 * 1000;

type AlertsState = {
  check: AlertCheck | null;   // null until the first check, or when signed out
  loading: boolean;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AlertsState | null>(null);

// Checks all of your alerts when you open the app and every few minutes after that.
export function AlertsProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [check, setCheck] = useState<AlertCheck | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) { setCheck(null); return; }
    setLoading(true);
    try { setCheck(await api.checkAlerts(token)); } catch { /* keep the last result */ } finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    refresh();
    if (!token) return;
    const id = setInterval(refresh, EVERY_MS);
    return () => clearInterval(id);
  }, [token, refresh]);

  const value = useMemo(() => ({ check, loading, refresh }), [check, loading, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAlerts(): AlertsState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAlerts must be used inside AlertsProvider");
  return v;
}
