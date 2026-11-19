import { Link } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, Switch, Text, View } from "react-native";
import { Button, Card, ErrorText, Heading, Tag } from "@/components/ui";
import { AlertEvent, api, Settings } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useData } from "@/lib/data";
import { fmtSince, fmtWhen } from "@/lib/format";
import { useTheme } from "@/lib/theme";

export default function AlertsTab() {
  const t = useTheme();
  const { token, user, signOut } = useAuth();
  const { check, refreshAlerts } = useData();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    api.settings(token).then(setSettings).catch(() => undefined);
    api.alertHistory(token).then((r) => setEvents(r.events)).catch(() => undefined);
    await refreshAlerts();
  }, [token, refreshAlerts]);

  useEffect(() => { load(); }, [load]);

  async function toggle(on: boolean) {
    if (!token) return;
    setErr(""); setMsg("");
    try { setSettings(await api.saveSettings(token, on)); } catch (e) { setErr(e instanceof Error ? e.message : "Couldn't save."); }
  }

  async function test() {
    if (!token) return;
    setErr(""); setMsg(""); setBusy(true);
    try { const r = await api.testEmail(token); setMsg(`Sent to ${r.sent_to}. Check your inbox and spam folder.`); }
    catch (e) { setErr(e instanceof Error ? e.message : "Couldn't send."); }
    finally { setBusy(false); }
  }

  const firing = check?.firing ?? [];

  return (
    <ScrollView style={{ backgroundColor: t.bg }} contentContainerStyle={{ padding: 16, paddingBottom: 48 }}
      refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={t.accent} />}>
      <Heading>Firing now</Heading>
      {firing.length === 0 ? <Text style={{ color: t.muted }}>Nothing is firing. Set alerts on a stock&apos;s page.</Text> : firing.map((f) => (
        <Link key={f.alert_id} href={{ pathname: "/stock/[ticker]", params: { ticker: f.ticker } }} asChild>
          <Card style={{ marginBottom: 8 }}>
            <Text style={{ color: t.ink, fontWeight: "700" }}>{f.ticker} <Text style={{ color: t.muted, fontWeight: "400" }}>· {f.watchlist}</Text></Text>
            <Text style={{ color: t.ink, marginTop: 4 }}>{f.message}</Text>
            {f.since ? <View style={{ marginTop: 6 }}><Tag tone="warn">{`Firing since ${fmtSince(f.since)}`}</Tag></View> : null}
          </Card>
        </Link>
      ))}
      {check && check.unavailable.length > 0 && <Text style={{ color: t.muted, marginTop: 6 }}>Couldn&apos;t check: {check.unavailable.join(", ")}.</Text>}

      <Heading>Email</Heading>
      {settings && !settings.email_configured ? <Text style={{ color: t.muted }}>Email alerts aren&apos;t set up on the server.</Text> : settings && (
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <Text style={{ flex: 1, color: t.ink, marginRight: 12 }}>Email me at {settings.email} when an alert starts firing</Text>
            <Switch value={settings.email_alerts} onValueChange={toggle} disabled={!settings.email_available} accessibilityLabel="Email alerts" />
          </View>
          {!settings.email_available && <Text style={{ color: t.muted, marginTop: 8 }}>Email isn&apos;t available for this address yet.</Text>}
          <Button kind="plain" title={busy ? "Sending…" : "Send me a test email"} disabled={busy || !settings.email_available} onPress={test} style={{ marginTop: 8, alignSelf: "flex-start" }} />
          {msg ? <Text style={{ color: t.up }}>{msg}</Text> : null}
          {err ? <ErrorText>{err}</ErrorText> : null}
        </Card>
      )}

      <Heading>History</Heading>
      {events.length === 0 ? <Text style={{ color: t.muted }}>Alerts that fire will be listed here.</Text> : events.map((e) => (
        <View key={e.id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: t.rule }}>
          <Text style={{ color: t.ink }}>{e.message}</Text>
          <Text style={{ color: t.muted, fontSize: 12 }}>{fmtWhen(e.at)} · {e.watchlist}</Text>
        </View>
      ))}
      {events.length > 0 && token && <Button kind="plain" title="Clear history" onPress={() => { api.clearAlertHistory(token).then(() => setEvents([])).catch(() => undefined); }} style={{ alignSelf: "flex-start", marginTop: 6 }} />}

      <Heading>Account</Heading>
      <Text style={{ color: t.ink2, marginBottom: 8 }}>{user?.email}</Text>
      <Button kind="danger" title="Sign out" onPress={signOut} style={{ alignSelf: "flex-start" }} />
    </ScrollView>
  );
}
