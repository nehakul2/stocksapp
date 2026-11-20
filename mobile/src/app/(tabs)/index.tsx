import { Link } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, FlatList, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import ListActions from "@/components/ListActions";
import { Card, ErrorText } from "@/components/ui";
import { api, Idea, OverviewRow, SearchHit } from "@/lib/api";
import { useData } from "@/lib/data";
import { fmtNum, fmtSigned } from "@/lib/format";
import { ideaText } from "@/lib/ideas";
import { useTheme } from "@/lib/theme";

function dayChange(r: OverviewRow): number | null {
  if (r.close == null || !r.prev_close) return null;
  return ((r.close - r.prev_close) / r.prev_close) * 100;
}

export default function Watchlist() {
  const t = useTheme();
  const { lists, activeId, tickers, setActive, add, remove, check, reloadLists, refreshAlerts } = useData();
  const [rows, setRows] = useState<OverviewRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [ideas, setIdeas] = useState<Map<string, Idea>>(new Map());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (tickers.length === 0) { setRows([]); return; }
    setLoading(true); setErr("");
    try { setRows((await api.overview(tickers)).rows); }
    catch (e) { setErr(e instanceof Error ? e.message : "Couldn't load prices."); }
    finally { setLoading(false); }
  }, [tickers]);

  useEffect(() => { load(); }, [load]);

  // Buy / hold / sell ideas load separately, so a slow one never delays the prices.
  useEffect(() => {
    if (tickers.length === 0) { setIdeas(new Map()); return; }
    let cancelled = false;
    api.suggestions(tickers)
      .then((d) => { if (!cancelled) setIdeas(new Map(d.items.map((i) => [i.ticker, i] as const))); })
      .catch(() => { if (!cancelled) setIdeas(new Map()); });
    return () => { cancelled = true; };
  }, [tickers]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) { setHits([]); return; }
    timer.current = setTimeout(() => { api.search(q.trim()).then((r) => setHits(r.results.slice(0, 6))).catch(() => setHits([])); }, 300);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [q]);

  const firing = check?.firing.length ?? 0;
  const byTicker = new Map(rows.map((r) => [r.ticker, r] as const));

  return (
    <FlatList
      style={{ backgroundColor: t.bg }}
      contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
      data={tickers}
      keyExtractor={(x) => x}
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={loading} onRefresh={() => { reloadLists(); refreshAlerts(); load(); }} tintColor={t.accent} />}
      ListHeaderComponent={
        <View>
          <ListActions />
          {lists.length > 1 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
              {lists.map((l) => (
                <Pressable key={l.id} onPress={() => setActive(l.id)} accessibilityRole="button" accessibilityState={{ selected: l.id === activeId }}
                  style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, marginRight: 8, backgroundColor: l.id === activeId ? t.accent : t.wash }}>
                  <Text style={{ color: l.id === activeId ? t.accentInk : t.ink2, fontWeight: "600" }}>{l.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          )}
          {firing > 0 && (
            <Card style={{ backgroundColor: t.warnBg, marginBottom: 12 }}>
              <Text style={{ color: t.warn, fontWeight: "700" }}>{firing} alert{firing === 1 ? "" : "s"} firing</Text>
              <Text style={{ color: t.warn, marginTop: 2 }}>See the Alerts tab for details.</Text>
            </Card>
          )}
          <TextInput
            value={q} onChangeText={setQ} placeholder="Add a stock: name or ticker" placeholderTextColor={t.muted}
            autoCapitalize="none" autoCorrect={false} accessibilityLabel="Search for a stock to add"
            style={{ borderWidth: 1, borderColor: t.rule, backgroundColor: t.card, color: t.ink, borderRadius: 10, padding: 12, fontSize: 16 }}
          />
          {hits.map((h) => (
            <Pressable key={h.symbol} onPress={async () => { try { await add(h.symbol); setQ(""); setHits([]); } catch (e) { setErr(e instanceof Error ? e.message : "Couldn't add it."); } }}
              style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: t.rule }} accessibilityRole="button" accessibilityLabel={`Add ${h.symbol} ${h.name}`}>
              <Text style={{ color: t.ink, fontWeight: "600" }}>{h.symbol} <Text style={{ color: t.muted, fontWeight: "400" }}>{h.name}</Text></Text>
            </Pressable>
          ))}
          {err ? <ErrorText>{err}</ErrorText> : null}
          <View style={{ height: 12 }} />
        </View>
      }
      ListEmptyComponent={<Text style={{ color: t.ink2, textAlign: "center", marginTop: 24 }}>Nothing here yet. Search above to add your first stock.</Text>}
      renderItem={({ item }) => {
        const r = byTicker.get(item);
        const ch = r ? dayChange(r) : null;
        const color = ch == null || ch === 0 ? t.muted : ch > 0 ? t.up : t.down;
        return (
          <Link href={{ pathname: "/stock/[ticker]", params: { ticker: item } }} asChild>
            <Pressable
              onLongPress={() => Alert.alert(`Remove ${item}?`, "It will also remove any alerts you set on it in this watchlist.", [
                { text: "Cancel", style: "cancel" }, { text: "Remove", style: "destructive", onPress: () => { remove(item).catch(() => setErr("Couldn't remove it.")); } },
              ])}
              accessibilityHint="Opens the stock. Press and hold to remove it from this watchlist."
              style={{ flexDirection: "row", alignItems: "center", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: t.rule }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: t.ink, fontSize: 17, fontWeight: "700" }}>{item}</Text>
                {r?.error ? <Text style={{ color: t.down, fontSize: 12 }}>No data right now</Text> : null}
                {ideas.get(item) ? (
                  <Text style={{ fontSize: 12, fontWeight: "600", marginTop: 2, color: ideas.get(item)!.action === "buy" ? t.up : ideas.get(item)!.action === "sell" ? t.down : t.muted }}>
                    {ideaText(ideas.get(item)!)}
                  </Text>
                ) : null}
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={{ color: t.ink, fontSize: 17, fontVariant: ["tabular-nums"] }}>{r ? fmtNum(r.close) : "…"}</Text>
                <Text style={{ color, fontSize: 14, fontVariant: ["tabular-nums"] }}>{ch == null ? "—" : `${ch > 0 ? "▲" : ch < 0 ? "▼" : "–"} ${fmtSigned(ch, 2, "%")}`}</Text>
              </View>
            </Pressable>
          </Link>
        );
      }}
      ListFooterComponent={<Text style={{ color: t.muted, fontSize: 12, marginTop: 14, textAlign: "center" }}>{tickers.length > 0 ? "Pull down to refresh. Press and hold a stock to remove it.\nIdeas come from simple price-trend rules, not advice. Open a stock to see why." : ""}</Text>}
    />
  );
}
