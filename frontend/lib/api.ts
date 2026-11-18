export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";

export type Summary = {
  name: string; ticker: string; price: number; currency: string; exchange: string;
  high_52wk: number | null; low_52wk: number | null; market_state: string;
  pre_market_price: number | null; pre_market_change_pct: number | null;
  post_market_price: number | null; post_market_change_pct: number | null;
};
export type NewsItem = { title: string; publisher: string; link: string | null };
export type Explanation = {
  pct_change: number | null; magnitude: string; volume_note: string;
  market_note: string; earnings_note: string; headlines: NewsItem[];
};
export type Detail = {
  summary: Summary;
  smas: Record<string, number | null>;
  previous_day: { date: string; open: number; high: number; low: number; close: number } | null;
  trend: { direction: string; estimates: Record<string, number>; disclaimer: string } | null;
  explanation: Explanation;
  news: NewsItem[];
  next_earnings: string;
};
export type Bar = {
  date: string; open: number; high: number; low: number; close: number; volume: number | null;
  sma_5: number | null; sma_20: number | null; sma_50: number | null; sma_100: number | null; sma_200: number | null;
};
export type OverviewRow = {
  ticker: string; exchange: string; date: string | null; close: number | null; prev_close: number | null;
  next_earnings: string; spark?: number[]; error?: string;
  sma_5?: number | null; sma_20?: number | null; sma_50?: number | null; sma_100?: number | null; sma_200?: number | null;
};
export type AttentionItem = { ticker: string; score: number; reasons: string[] };
export type SearchHit = { symbol: string; name: string; exchange: string; type: string };

export type AiUsage = { used: number; limit: number; enabled: boolean };
export type AiResult = { ticker: string; summary: string; headlines: NewsItem[]; usage: { used: number; limit: number } };

export type PeerRow = {
  ticker: string; name: string; kind: "self" | "peer" | "market";
  price: number | null; day_pct: number | null; month_pct: number | null;
};
export type Peers = {
  ticker: string; sector: string; industry: string; rows: PeerRow[];
  peer_median_day_pct: number | null; peer_median_month_pct: number | null;
};

export type WatchlistDto = { id: number; name: string; tickers: string[] };
export type AlertType = "price_above" | "price_below" | "sma_cross_above" | "sma_cross_below";
export type AlertRule = { id: number; watchlist_id: number; ticker: string; type: AlertType; value: number; label: string };
export type Firing = { alert_id: number; watchlist_id: number; watchlist: string; ticker: string; type: AlertType; message: string };
export type AlertCheck = { firing: Firing[]; unavailable: string[]; checked: number };
export type AlertEvent = { id: number; day: string; watchlist: string; ticker: string; message: string };

export type Settings = { email: string; email_alerts: boolean; email_configured: boolean; email_available: boolean };

export type ChatAction = {
  type: "create_list" | "add_to_list" | "remove_from_list" | "rename_list";
  label: string; list?: string; list_id?: number; name?: string; new_name?: string; tickers?: string[];
};
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ChatReply = { answer: string; actions: ChatAction[]; usage: { used: number; limit: number } };

export const SMA_WINDOWS = [5, 20, 50, 100, 200] as const;

async function get<T>(path: string, token?: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { cache: "no-store", headers: token ? { Authorization: `Bearer ${token}` } : undefined });
  } catch {
    throw new Error(`Can't reach the API at ${API}. Is it running?`);
  }
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail ?? ""; } catch { /* ignore */ }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function authed<T>(path: string, token: string, method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method, cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(`Can't reach the API at ${API}. Is it running?`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail ?? `Request failed (${res.status})`), { status: res.status });
  return data as T;
}

const list = (t: string[]) => encodeURIComponent(t.join(","));
const sym = (t: string) => encodeURIComponent(t);

export const api = {
  search: (q: string) => get<{ results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  overview: (t: string[]) => get<{ rows: OverviewRow[] }>(`/api/overview?tickers=${list(t)}`),
  attention: (t: string[]) => get<{ items: AttentionItem[] }>(`/api/attention?tickers=${list(t)}`),
  detail: (t: string, range: string) => get<Detail>(`/api/stocks/${sym(t)}?range=${range}`),
  history: (t: string, range: string) => get<{ bars: Bar[] }>(`/api/stocks/${sym(t)}/history?range=${range}`),
  peers: (t: string) => get<Peers>(`/api/stocks/${sym(t)}/peers`),
  watchlists: (token: string) => authed<{ watchlists: WatchlistDto[] }>("/api/watchlists", token),
  createWatchlist: (token: string, name: string) => authed<WatchlistDto>("/api/watchlists", token, "POST", { name }),
  renameWatchlist: (token: string, id: number, name: string) => authed<WatchlistDto>(`/api/watchlists/${id}`, token, "PATCH", { name }),
  deleteWatchlist: (token: string, id: number) => authed<{ watchlists: WatchlistDto[] }>(`/api/watchlists/${id}`, token, "DELETE"),
  saveTickers: (token: string, id: number, tickers: string[]) => authed<{ tickers: string[] }>(`/api/watchlists/${id}/tickers`, token, "PUT", { tickers }),
  alerts: (token: string, id: number) => authed<{ alerts: AlertRule[] }>(`/api/watchlists/${id}/alerts`, token),
  addAlert: (token: string, id: number, ticker: string, type: AlertType, value: number) =>
    authed<AlertRule>(`/api/watchlists/${id}/alerts`, token, "POST", { ticker, type, value }),
  deleteAlert: (token: string, alertId: number) => authed<{ ok: boolean }>(`/api/alerts/${alertId}`, token, "DELETE"),
  checkAlerts: (token: string) => authed<AlertCheck>("/api/alerts/check", token, "POST"),
  alertHistory: (token: string) => authed<{ events: AlertEvent[] }>("/api/alerts/history", token),
  settings: (token: string) => authed<Settings>("/api/settings", token),
  saveSettings: (token: string, email_alerts: boolean) => authed<Settings>("/api/settings", token, "PUT", { email_alerts }),
  chat: (token: string, question: string, history: ChatTurn[], ticker?: string) =>
    authed<ChatReply>("/api/chat", token, "POST", { question, history, ticker: ticker ?? null }),
  clearAlertHistory: (token: string) => authed<{ ok: boolean }>("/api/alerts/history", token, "DELETE"),
  exportUrl: (t: string, start: string, end: string) => `${API}/api/stocks/${sym(t)}/export.csv?start=${start}&end=${end}`,
  aiUsage: (token: string) => get<AiUsage>("/api/ai/usage", token),
  async aiSummary(t: string, token: string): Promise<AiResult> {
    let res: Response;
    try {
      res = await fetch(`${API}/api/stocks/${sym(t)}/ai-summary`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    } catch {
      throw new Error(`Can't reach the API at ${API}. Is it running?`);
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(body.detail ?? `Request failed (${res.status})`), { status: res.status });
    return body as AiResult;
  },
};
