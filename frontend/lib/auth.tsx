"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { API } from "@/lib/api";

const TOKEN_KEY = "auth.token";
export type User = { id: number; email: string };

type AuthState = {
  user: User | null;
  token: string | null;
  ready: boolean; // false until we've checked for a saved session
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => void;
};

const Ctx = createContext<AuthState | null>(null);

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new Error(`Can't reach the API at ${API}. Is it running?`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(body.detail ?? `Request failed (${res.status})`), { status: res.status });
  return body as T;
}

export const authHeader = (token: string) => ({ Authorization: `Bearer ${token}` });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(TOKEN_KEY); } catch { /* private mode */ }
    if (!saved) { setReady(true); return; }
    call<User>("/api/me", { headers: authHeader(saved) })
      .then((u) => { setUser(u); setToken(saved); })
      .catch((e) => {
        // Only forget the session if the server rejected it; keep it if the API was just unreachable.
        if (e.status === 401) { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } }
      })
      .finally(() => setReady(true));
  }, []);

  const finish = useCallback((r: { token: string; user: User }) => {
    try { localStorage.setItem(TOKEN_KEY, r.token); } catch { /* ignore */ }
    setToken(r.token);
    setUser(r.user);
  }, []);

  const post = (path: string, email: string, password: string) =>
    call<{ token: string; user: User }>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }).then(finish);

  const value = useMemo<AuthState>(() => ({
    user, token, ready,
    signIn: (e, p) => post("/api/auth/login", e, p),
    signUp: (e, p) => post("/api/auth/signup", e, p),
    signOut: () => {
      try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
      setToken(null); setUser(null);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [user, token, ready]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
