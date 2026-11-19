import { Stack, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, Text, View } from "react-native";
import AlertRules from "@/components/AlertRules";
import { Button, Card, ErrorText, Heading } from "@/components/ui";
import { AiResult, AiUsage, api, Detail, Peers } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { earningsLabel, fmtNum, fmtSigned } from "@/lib/format";
import { useTheme } from "@/lib/theme";

export default function StockScreen() {
  const t = useTheme();
  const { token } = useAuth();
  const { ticker: raw } = useLocalSearchParams<{ ticker: string }>();
  const ticker = decodeURIComponent(String(raw));
  const [detail, setDetail] = useState<Detail | null>(null);
  const [peers, setPeers] = useState<Peers | null>(null);
  const [ai, setAi] = useState<AiResult | null>(null);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [err, setErr] = useState("");
  const [aiErr, setAiErr] = useState("");
  const [aiBusy, setAiBusy] = useState(false);

  const load = useCallback(async () => {
    setErr("");
    try { setDetail(await api.detail(ticker, "6mo")); }
    catch (e) { setErr(e instanceof Error ? e.message : "Couldn't load this stock."); }
    api.peers(ticker).then(setPeers).catch(() => setPeers(null));
  }, [ticker]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (token) api.aiUsage(token).then(setUsage).catch(() => undefined); }, [token]);

  async function explain() {
    if (!token) return;
    setAiErr(""); setAiBusy(true);
    try { const r = await api.aiSummary(ticker, token); setAi(r); setUsage({ ...(usage ?? { enabled: true, limit: r.usage.limit, used: 0 }), used: r.usage.used, limit: r.usage.limit }); }
    catch (e) { setAiErr(e instanceof Error ? e.message : "Couldn't get an explanation."); }
    finally { setAiBusy(false); }
  }

  if (!detail) {
    return (
      <View style={{ flex: 1, backgroundColor: t.bg, alignItems: "center", justifyContent: "center", padding: 24 }}>
        <Stack.Screen options={{ title: ticker }} />
        {err ? <><ErrorText>{err}</ErrorText><Button kind="plain" title="Try again" onPress={load} /></> : <ActivityIndicator color={t.accent} />}
      </View>
    );
  }

  const s = detail.summary;
  const ex = detail.explanation;
  const pct = ex.pct_change;
  const color = !pct ? t.muted : pct > 0 ? t.up : t.down;
  const notes = [ex.market_note, ex.volume_note, ex.earnings_note].filter(Boolean);
  const canExplain = pct != null && pct !== 0;

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
      <Stack.Screen options={{ title: s.ticker }} />
      <Text style={{ color: t.ink2, fontSize: 15 }}>{s.name}</Text>
      <View style={{ flexDirection: "row", alignItems: "baseline", marginTop: 4 }}>
        <Text style={{ color: t.ink, fontSize: 36, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{fmtNum(s.price)}</Text>
        <Text style={{ color: t.muted, marginLeft: 6 }}>{s.currency}</Text>
        <Text style={{ color, fontSize: 18, fontWeight: "600", marginLeft: 12 }}>{pct == null ? "" : `${pct > 0 ? "▲" : pct < 0 ? "▼" : "–"} ${fmtSigned(pct, 2, "%")}`}</Text>
      </View>
      <Text style={{ color: t.muted, marginTop: 4 }}>52-week range {fmtNum(s.low_52wk)} to {fmtNum(s.high_52wk)} · Next earnings {earningsLabel(detail.next_earnings)}</Text>

      <Heading>Why it moved</Heading>
      {notes.length > 0 ? <Card>{notes.map((n, i) => <Text key={i} style={{ color: t.ink, lineHeight: 21, marginTop: i ? 8 : 0 }}>{n}</Text>)}</Card> : <Text style={{ color: t.muted }}>No big move today.</Text>}
      {canExplain && (
        <View style={{ marginTop: 12 }}>
          <Button title={aiBusy ? "Thinking…" : ai ? "Explain again" : "Explain this move"} disabled={aiBusy} onPress={explain} />
          {usage && <Text style={{ color: t.muted, fontSize: 12, marginTop: 6 }}>{usage.used} of {usage.limit} explanations used today</Text>}
          {aiErr ? <ErrorText>{aiErr}</ErrorText> : null}
          {ai && (
            <Card style={{ marginTop: 12 }}>
              <Text style={{ color: t.ink, lineHeight: 22 }}>{ai.summary}</Text>
              {ai.headlines.map((h, i) => (
                <Pressable key={i} onPress={() => h.link && Linking.openURL(h.link)} accessibilityRole="link" style={{ marginTop: 10 }}>
                  <Text style={{ color: t.accent, textDecorationLine: "underline" }}>{h.title}</Text>
                  <Text style={{ color: t.muted, fontSize: 12 }}>{h.publisher}</Text>
                </Pressable>
              ))}
              <Text style={{ color: t.muted, fontSize: 12, marginTop: 10 }}>AI-written from the facts above and recent headlines. Not financial advice.</Text>
            </Card>
          )}
        </View>
      )}

      {peers && peers.rows.length > 1 && (
        <>
          <Heading>How it compares</Heading>
          <Card>
            <View style={{ flexDirection: "row", paddingBottom: 6 }}>
              <Text style={{ flex: 1, color: t.muted, fontSize: 12 }}>Company</Text>
              <Text style={{ width: 70, textAlign: "right", color: t.muted, fontSize: 12 }}>Today</Text>
              <Text style={{ width: 70, textAlign: "right", color: t.muted, fontSize: 12 }}>30 days</Text>
            </View>
            {peers.rows.map((r) => (
              <View key={r.ticker} style={{ flexDirection: "row", paddingVertical: 6, borderTopWidth: 1, borderTopColor: t.rule }}>
                <Text style={{ flex: 1, color: t.ink, fontWeight: r.kind === "self" ? "700" : "400" }} numberOfLines={1}>{r.ticker}</Text>
                <Text style={{ width: 70, textAlign: "right", color: !r.day_pct ? t.muted : r.day_pct > 0 ? t.up : t.down, fontVariant: ["tabular-nums"] }}>{fmtSigned(r.day_pct, 1, "%")}</Text>
                <Text style={{ width: 70, textAlign: "right", color: !r.month_pct ? t.muted : r.month_pct > 0 ? t.up : t.down, fontVariant: ["tabular-nums"] }}>{fmtSigned(r.month_pct, 1, "%")}</Text>
              </View>
            ))}
          </Card>
        </>
      )}

      <Heading>Moving averages</Heading>
      <Card>
        {Object.entries(detail.smas).map(([k, v], i) => (
          <View key={k} style={{ flexDirection: "row", paddingVertical: 4 }}>
            <Text style={{ flex: 1, color: t.ink2 }}>{k.replace("sma_", "")}-day</Text>
            <Text style={{ color: t.ink, fontVariant: ["tabular-nums"] }}>{fmtNum(v)}</Text>
          </View>
        ))}
      </Card>

      <Heading>Alerts</Heading>
      <AlertRules ticker={s.ticker} />

      {detail.news.length > 0 && (
        <>
          <Heading>Recent headlines</Heading>
          {detail.news.slice(0, 6).map((n, i) => (
            <Pressable key={i} onPress={() => n.link && Linking.openURL(n.link)} accessibilityRole="link" style={{ paddingVertical: 8 }}>
              <Text style={{ color: t.ink }}>{n.title}</Text>
              <Text style={{ color: t.muted, fontSize: 12 }}>{n.publisher}</Text>
            </Pressable>
          ))}
        </>
      )}
    </ScrollView>
  );
}
