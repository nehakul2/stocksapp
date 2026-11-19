import * as SecureStore from "expo-secure-store";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { API, authed } from "@/lib/api";

const TOKEN_KEY = "auth.token";
export type User = { id: number; email: string };

type AuthState = {
  user: User | null;
  token: string | null;
  ready: boolean; // false until the saved session has been checked
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => void;
};

const Ctx = createContext<AuthState | null>(null);

async function post(path: string, email: string, password: string): Promise<{ token: string; user: User }> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  } catch {
    throw new Error("Can't reach the server. Check your connection and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `Request failed (${res.status})`);
  return body;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      let saved: string | null = null;
      try { saved = await SecureStore.getItemAsync(TOKEN_KEY); } catch { /* unavailable */ }
      if (!saved) { setReady(true); return; }
      try {
        const u = await authed<User>("/api/me", saved);
        setUser(u); setToken(saved);
      } catch (e) {
        // Only forget the session if the server rejected it; keep it if we were just offline.
        if ((e as { status?: number }).status === 401) await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
      }
      setReady(true);
    })();
  }, []);

  const finish = useCallback(async (r: { token: string; user: User }) => {
    await SecureStore.setItemAsync(TOKEN_KEY, r.token).catch(() => undefined);
    setToken(r.token); setUser(r.user);
  }, []);

  const value = useMemo<AuthState>(() => ({
    user, token, ready,
    signIn: async (e, p) => finish(await post("/api/auth/login", e, p)),
    signUp: async (e, p) => finish(await post("/api/auth/signup", e, p)),
    signOut: () => {
      SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
      setToken(null); setUser(null);
    },
  }), [user, token, ready, finish]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
