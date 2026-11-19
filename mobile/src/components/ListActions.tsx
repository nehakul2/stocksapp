import { useState } from "react";
import { Modal, Pressable, Text, TextInput, View } from "react-native";
import { Button, ErrorText } from "@/components/ui";
import { useData } from "@/lib/data";
import { useTheme } from "@/lib/theme";

type Mode = "new" | "rename" | "delete" | null;

// New list, Rename and Delete for the watchlist you are looking at.
export default function ListActions() {
  const t = useTheme();
  const { lists, activeId, createList, renameList, deleteList } = useData();
  const [mode, setMode] = useState<Mode>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const active = lists.find((l) => l.id === activeId);
  if (!active) return null;

  function open(m: Exclude<Mode, null>) {
    setErr(""); setName(m === "rename" ? active!.name : ""); setMode(m);
  }

  async function submit() {
    setErr(""); setBusy(true);
    const clean = name.trim();
    const msg = mode === "new" ? await createList(clean) : mode === "rename" ? await renameList(active!.id, clean) : await deleteList(active!.id);
    setBusy(false);
    if (msg) setErr(msg); else setMode(null);
  }

  const asking = mode === "new" || mode === "rename";
  const title = mode === "new" ? "New watchlist" : mode === "rename" ? `Rename “${active.name}”` : `Delete “${active.name}”?`;

  return (
    <View style={{ marginBottom: 8 }}>
      <Text style={{ color: t.ink, fontSize: 18, fontWeight: "700" }} numberOfLines={1}>{active.name}</Text>
      <Text style={{ color: t.muted, marginBottom: 2 }}>{active.tickers.length} stock{active.tickers.length === 1 ? "" : "s"}</Text>
      <View style={{ flexDirection: "row", marginLeft: -16 }}>
        <Button kind="plain" title="New list" onPress={() => open("new")} />
        <Button kind="plain" title="Rename" onPress={() => open("rename")} />
        {lists.length > 1 && <Button kind="danger" title="Delete" onPress={() => open("delete")} />}
      </View>

      <Modal visible={mode !== null} transparent animationType="none" onRequestClose={() => setMode(null)}>
        <Pressable onPress={() => !busy && setMode(null)} style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: 24 }}>
          <Pressable onPress={() => undefined} style={{ backgroundColor: t.card, borderRadius: 14, padding: 18 }} accessibilityViewIsModal>
            <Text accessibilityRole="header" style={{ color: t.ink, fontSize: 18, fontWeight: "700", marginBottom: 10 }}>{title}</Text>
            {asking ? (
              <TextInput autoFocus value={name} onChangeText={setName} maxLength={40} placeholder="Name, for example Finance" placeholderTextColor={t.muted}
                accessibilityLabel="Watchlist name" onSubmitEditing={submit} returnKeyType="done"
                style={{ borderWidth: 1, borderColor: t.rule, backgroundColor: t.bg, color: t.ink, borderRadius: 10, padding: 12, fontSize: 16 }} />
            ) : (
              <Text style={{ color: t.ink2, lineHeight: 21 }}>This removes the list and any alerts on it. Your other lists are not touched.</Text>
            )}
            {err ? <ErrorText>{err}</ErrorText> : null}
            <View style={{ flexDirection: "row", justifyContent: "flex-end", marginTop: 14 }}>
              <Button kind="plain" title="Cancel" onPress={() => setMode(null)} disabled={busy} />
              <Button kind={mode === "delete" ? "danger" : "solid"} title={busy ? "Please wait…" : mode === "new" ? "Create" : mode === "rename" ? "Save" : "Delete list"}
                onPress={submit} disabled={busy || (asking && !name.trim())} style={{ marginLeft: 8 }} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
