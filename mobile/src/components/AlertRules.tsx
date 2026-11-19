import { useCallback, useEffect, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { Button, ErrorText, Tag } from "@/components/ui";
import { AlertRule, AlertType, api, SMA_WINDOWS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useData } from "@/lib/data";
import { fmtSince } from "@/lib/format";
import { useTheme } from "@/lib/theme";

const TYPES: { value: AlertType; label: string }[] = [
  { value: "price_above", label: "Price above" },
  { value: "price_below", label: "Price below" },
  { value: "sma_cross_above", label: "Crosses above average" },
  { value: "sma_cross_below", label: "Crosses below average" },
];

// Alerts for one stock on the watchlist you are looking at: add, turn off or on, remove.
export default function AlertRules({ ticker }: { ticker: string }) {
  const t = useTheme();
  const { token } = useAuth();
  const { lists, activeId, tickers, add, check, refreshAlerts } = useData();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [type, setType] = useState<AlertType>("price_above");
  const [value, setValue] = useState("");
  const [sma, setSma] = useState<number>(50);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const listName = lists.find((l) => l.id === activeId)?.name ?? "";
  const onList = tickers.includes(ticker);
  const isPrice = type.startsWith("price_");

  const load = useCallback(() => {
    if (!token || activeId == null || !onList) { setRules([]); return; }
    api.alerts(token, activeId).then((r) => setRules(r.alerts.filter((a) => a.ticker === ticker))).catch(() => setRules([]));
  }, [token, activeId, onList, ticker]);

  useEffect(load, [load]);

  if (!onList) {
    return (
      <View>
        <Text style={{ color: t.ink2, marginBottom: 8 }}>Alerts belong to a watchlist.</Text>
        <Button title={`Add ${ticker} to “${listName}”`} onPress={() => { add(ticker).catch((e) => setErr(e instanceof Error ? e.message : "Couldn't add it.")); }} />
        {err ? <ErrorText>{err}</ErrorText> : null}
      </View>
    );
  }

  const since = new Map((check?.firing ?? []).map((f) => [f.alert_id, f.since] as const));

  async function run(fn: () => Promise<unknown>) {
    setErr(""); setBusy(true);
    try { await fn(); } catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); load(); refreshAlerts(); }
  }

  const chip = (selected: boolean) => ({ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 16, marginRight: 8, marginBottom: 8, backgroundColor: selected ? t.accent : t.wash }) as const;

  return (
    <View>
      <Text style={{ color: t.ink2, marginBottom: 8 }}>On your “{listName}” watchlist.</Text>
      {rules.length === 0 ? <Text style={{ color: t.muted, marginBottom: 8 }}>No alerts on {ticker} yet.</Text> : rules.map((r) => (
        <View key={r.id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: t.rule }}>
          <Text style={{ color: r.paused ? t.muted : t.ink, fontSize: 16 }}>{r.label}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", marginTop: 6 }}>
            {r.paused ? <Tag>Off</Tag> : since.has(r.id) ? <Tag tone="warn">{`Firing${since.get(r.id) ? ` since ${fmtSince(since.get(r.id))}` : " now"}`}</Tag> : null}
            <View style={{ flex: 1 }} />
            <Button kind="plain" title={r.paused ? "Turn on" : "Turn off"} disabled={busy} onPress={() => run(() => api.pauseAlert(token!, r.id, !r.paused))} />
            <Button kind="danger" title="Remove" disabled={busy} onPress={() => run(() => api.deleteAlert(token!, r.id))} />
          </View>
        </View>
      ))}

      <Text style={{ color: t.ink, fontWeight: "600", marginTop: 16, marginBottom: 8 }}>Add an alert</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {TYPES.map((x) => (
          <Pressable key={x.value} onPress={() => setType(x.value)} style={chip(type === x.value)} accessibilityRole="button" accessibilityState={{ selected: type === x.value }}>
            <Text style={{ color: type === x.value ? t.accentInk : t.ink2, fontWeight: "600" }}>{x.label}</Text>
          </Pressable>
        ))}
      </View>
      {isPrice ? (
        <TextInput value={value} onChangeText={setValue} keyboardType="decimal-pad" placeholder="Price, for example 150" placeholderTextColor={t.muted} accessibilityLabel="Price level"
          style={{ borderWidth: 1, borderColor: t.rule, backgroundColor: t.card, color: t.ink, borderRadius: 10, padding: 12, fontSize: 16, marginBottom: 10 }} />
      ) : (
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {SMA_WINDOWS.map((w) => (
            <Pressable key={w} onPress={() => setSma(w)} style={chip(sma === w)} accessibilityRole="button" accessibilityState={{ selected: sma === w }}>
              <Text style={{ color: sma === w ? t.accentInk : t.ink2, fontWeight: "600" }}>{w}-day</Text>
            </Pressable>
          ))}
        </View>
      )}
      <Button title="Add alert" disabled={busy || (isPrice && !(Number(value) > 0))}
        onPress={() => run(async () => { await api.addAlert(token!, activeId!, ticker, type, isPrice ? Number(value) : sma); setValue(""); })} />
      {err ? <ErrorText>{err}</ErrorText> : null}
    </View>
  );
}
