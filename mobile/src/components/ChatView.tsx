import * as Speech from "expo-speech";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, Pressable, Switch, Text, TextInput, View } from "react-native";
import { Button, ErrorText } from "@/components/ui";
import { api, ChatAction, ChatTurn } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useData } from "@/lib/data";
import { useTheme } from "@/lib/theme";

type Msg = { role: "user" | "assistant"; content: string; actions?: ChatAction[] };

const STOCK_IDEAS = ["Why is it moving today?", "Is it near its 52-week low?", "How does it compare with similar companies?"];
const HOME_IDEAS = ["Which of my stocks needs a look today?", "Create a watchlist called Energy with XOM and CVX", "What do my watchlists have in common?"];

// Ask about a stock (when `ticker` is given) or about your watchlists, and ask for watchlist
// changes. The chat only proposes a change; nothing happens until you tap Confirm.
export default function ChatView({ ticker }: { ticker?: string }) {
  const t = useTheme();
  const { token } = useAuth();
  const { runAction } = useData();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [left, setLeft] = useState("");
  const [speak, setSpeak] = useState(false);
  const list = useRef<FlatList<Msg>>(null);

  useEffect(() => () => { Speech.stop(); }, []);

  const send = useCallback(async (q: string) => {
    const question = q.trim();
    if (!question || busy || !token) return;
    setErr(""); setBusy(true); setText("");
    Speech.stop();
    const history: ChatTurn[] = msgs.slice(-8).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: question }]);
    try {
      const r = await api.chat(token, question, history, ticker);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, actions: r.actions }]);
      setLeft(`${Math.max(0, r.usage.limit - r.usage.used)} of ${r.usage.limit} AI questions left today`);
      if (speak) Speech.speak(r.answer);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }, [busy, token, msgs, ticker, speak]);

  async function confirm(key: string, a: ChatAction) {
    setStatus((s) => ({ ...s, [key]: "working" }));
    const m = await runAction(a);
    setStatus((s) => ({ ...s, [key]: m ?? "done" }));
  }

  const ideas = ticker ? STOCK_IDEAS : HOME_IDEAS;

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}>
      <FlatList
        ref={list}
        data={msgs}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={{ padding: 16, paddingBottom: 8 }}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
        ListHeaderComponent={msgs.length === 0 ? (
          <View style={{ marginBottom: 8 }}>
            <Text style={{ color: t.ink2, marginBottom: 10 }}>{ticker ? `Ask about ${ticker}.` : "Ask about your watchlists, or ask me to change one."} Tip: tap the microphone on your keyboard to speak.</Text>
            {ideas.map((q) => (
              <Pressable key={q} onPress={() => send(q)} disabled={busy} accessibilityRole="button"
                style={{ backgroundColor: t.wash, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10, marginBottom: 8, alignSelf: "flex-start" }}>
                <Text style={{ color: t.ink2 }}>{q}</Text>
              </Pressable>
            ))}
          </View>
        ) : undefined}
        renderItem={({ item, index }) => item.role === "user" ? (
          <View style={{ alignSelf: "flex-end", maxWidth: "85%", backgroundColor: t.wash, padding: 10, borderRadius: 14, marginBottom: 12 }}>
            <Text style={{ color: t.ink }}>{item.content}</Text>
          </View>
        ) : (
          <View style={{ borderLeftWidth: 3, borderLeftColor: t.accent, paddingLeft: 12, marginBottom: 14 }}>
            <Text selectable style={{ color: t.ink, fontSize: 16, lineHeight: 23 }}>{item.content}</Text>
            {item.actions?.map((a, j) => {
              const key = `${index}-${j}`;
              const st = status[key] ?? "pending";
              return (
                <View key={key} style={{ marginTop: 10, borderWidth: 1, borderStyle: "dashed", borderColor: t.rule, borderRadius: 10, padding: 10 }}>
                  <Text style={{ color: t.ink, fontWeight: "600" }}>{a.label}</Text>
                  {st === "pending" && (
                    <View style={{ flexDirection: "row", marginTop: 6, marginLeft: -16 }}>
                      <Button title="Confirm" kind="plain" onPress={() => confirm(key, a)} />
                      <Button title="Dismiss" kind="plain" onPress={() => setStatus((s) => ({ ...s, [key]: "dismissed" }))} />
                    </View>
                  )}
                  {st === "working" && <Text style={{ color: t.muted, marginTop: 6 }}>Working…</Text>}
                  {st === "done" && <Text style={{ color: t.up, marginTop: 6, fontWeight: "600" }}>Done</Text>}
                  {st === "dismissed" && <Text style={{ color: t.muted, marginTop: 6 }}>Dismissed</Text>}
                  {!["pending", "working", "done", "dismissed"].includes(st) && <ErrorText>{st}</ErrorText>}
                </View>
              );
            })}
          </View>
        )}
        ListFooterComponent={busy ? <Text style={{ color: t.muted }}>Thinking…</Text> : undefined}
      />
      <View style={{ padding: 12, borderTopWidth: 1, borderTopColor: t.rule, backgroundColor: t.card }}>
        {err ? <ErrorText>{err}</ErrorText> : null}
        <View style={{ flexDirection: "row", alignItems: "flex-end" }}>
          <TextInput
            value={text} onChangeText={setText} multiline maxLength={400} editable={!busy}
            placeholder={ticker ? `Ask about ${ticker}` : "Ask about your watchlists"} placeholderTextColor={t.muted}
            accessibilityLabel="Your question"
            style={{ flex: 1, maxHeight: 110, borderWidth: 1, borderColor: t.rule, backgroundColor: t.bg, color: t.ink, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16 }}
          />
          <Button title="Ask" onPress={() => send(text)} disabled={busy || !text.trim()} style={{ marginLeft: 8 }} />
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", marginTop: 8 }}>
          <Switch value={speak} onValueChange={(v) => { setSpeak(v); if (!v) Speech.stop(); }} accessibilityLabel="Read answers aloud" />
          <Text style={{ color: t.ink2, marginLeft: 8, flex: 1 }}>Read answers aloud</Text>
          {msgs.length > 0 && <Button kind="plain" title="Clear" onPress={() => { setMsgs([]); setStatus({}); setErr(""); Speech.stop(); }} />}
        </View>
        <Text style={{ color: t.muted, fontSize: 12, marginTop: 4 }}>{left ? `${left}. ` : ""}Answers can be wrong. Not financial advice.</Text>
      </View>
    </KeyboardAvoidingView>
  );
}
