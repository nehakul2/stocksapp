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
  next_earnings: string; error?: string;
  sma_5?: number | null; sma_20?: number | null; sma_50?: number | null; sma_100?: number | null; sma_200?: number | null;
};
export type AttentionItem = { ticker: string; score: number; reasons: string[] };
export type SearchHit = { symbol: string; name: string; exchange: string; type: string };

export const SMA_WINDOWS = [5, 20, 50, 100, 200] as const;

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { cache: "no-store" });
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

const list = (t: string[]) => encodeURIComponent(t.join(","));
const sym = (t: string) => encodeURIComponent(t);

export const api = {
  search: (q: string) => get<{ results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}`),
  overview: (t: string[]) => get<{ rows: OverviewRow[] }>(`/api/overview?tickers=${list(t)}`),
  attention: (t: string[]) => get<{ items: AttentionItem[] }>(`/api/attention?tickers=${list(t)}`),
  detail: (t: string, range: string) => get<Detail>(`/api/stocks/${sym(t)}?range=${range}`),
  history: (t: string, range: string) => get<{ bars: Bar[] }>(`/api/stocks/${sym(t)}/history?range=${range}`),
  async aiSummary(t: string, key: string): Promise<string> {
    const res = await fetch(`${API}/api/stocks/${sym(t)}/ai-summary`, { method: "POST", headers: { "X-Anthropic-Key": key } });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail ?? `Request failed (${res.status})`);
    return body.summary as string;
  },
};
