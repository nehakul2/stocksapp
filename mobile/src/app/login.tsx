import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Button, ErrorText } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

export default function Login() {
  const t = useTheme();
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(""); setBusy(true);
    try { await (mode === "in" ? signIn : signUp)(email.trim(), password); }
    catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }

  const input = { borderWidth: 1, borderColor: t.rule, backgroundColor: t.card, color: t.ink, borderRadius: 10, padding: 12, fontSize: 16, marginBottom: 12 } as const;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 72 }} keyboardShouldPersistTaps="handled">
          <Text style={{ color: t.ink, fontSize: 32, fontWeight: "800", letterSpacing: -0.5 }}>Stock Insights</Text>
          <Text style={{ color: t.ink2, fontSize: 16, marginTop: 6, marginBottom: 32 }}>Why your stocks moved, in plain English.</Text>
          <TextInput style={input} placeholder="Email" placeholderTextColor={t.muted} autoCapitalize="none" autoComplete="email" keyboardType="email-address" textContentType="emailAddress" value={email} onChangeText={setEmail} />
          <TextInput style={input} placeholder="Password" placeholderTextColor={t.muted} secureTextEntry autoCapitalize="none" textContentType={mode === "in" ? "password" : "newPassword"} value={password} onChangeText={setPassword} onSubmitEditing={submit} />
          {err ? <ErrorText>{err}</ErrorText> : null}
          <Button title={busy ? "Please wait…" : mode === "in" ? "Sign in" : "Create account"} onPress={submit} disabled={busy || !email || !password} />
          <Button kind="plain" title={mode === "in" ? "New here? Create an account" : "Have an account? Sign in"} onPress={() => { setMode(mode === "in" ? "up" : "in"); setErr(""); }} style={{ marginTop: 8 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
