const MINUS = "−";

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtSigned(n: number | null | undefined, digits = 2, suffix = ""): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const abs = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${n > 0 ? "+" : n < 0 ? MINUS : ""}${abs}${suffix}`;
}

export type Dir = "up" | "down" | "flat";
export const dirOf = (n: number | null | undefined): Dir => (!n ? "flat" : n > 0 ? "up" : "down");
export const arrow = (d: Dir) => (d === "up" ? "▲" : d === "down" ? "▼" : "–");

export function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function daysUntil(iso: string): number | null {
  if (!iso) return null;
  const target = new Date(`${iso}T00:00:00`);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

export function earningsLabel(iso: string): string {
  const d = daysUntil(iso);
  if (d === null) return "—";
  if (d === 0) return "Today";
  if (d === 1) return "Tomorrow";
  if (d === -1) return "Yesterday";
  return fmtDate(iso);
}

// Yahoo's raw exchange codes for indexes and futures ("SNP", "GIDS") mean nothing to most people.
export function venue(ticker: string, exchange: string): string {
  if (ticker.startsWith("^")) return "Index";
  if (ticker.endsWith("=F")) return "Futures";
  return exchange || "\u2014";
}

// "Nov 18, 2:31 PM" in the viewer's own time zone. Empty if the timestamp is missing or invalid.
export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// "2:31 PM" if it was today, otherwise "Nov 17, 2:31 PM".
export function fmtSince(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString() ? time : fmtWhen(iso);
}
