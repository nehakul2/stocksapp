import { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";
import { useTheme } from "@/lib/theme";

export function Button({ title, onPress, disabled, kind = "solid", style }: {
  title: string; onPress: () => void; disabled?: boolean; kind?: "solid" | "plain" | "danger"; style?: ViewStyle;
}) {
  const t = useTheme();
  const solid = kind === "solid";
  return (
    <Pressable
      accessibilityRole="button" disabled={disabled} onPress={onPress}
      style={({ pressed }) => [s.btn, solid && { backgroundColor: t.accent }, { opacity: disabled ? 0.45 : pressed ? 0.7 : 1 }, style]}
    >
      <Text style={{ color: solid ? t.accentInk : kind === "danger" ? t.down : t.accent, fontWeight: "600", fontSize: 15 }}>{title}</Text>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return <View style={[s.card, { backgroundColor: t.card, borderColor: t.rule }, style]}>{children}</View>;
}

export function Heading({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text accessibilityRole="header" style={{ color: t.ink, fontSize: 20, fontWeight: "700", marginTop: 22, marginBottom: 8 }}>{children}</Text>;
}

export function Tag({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "warn" }) {
  const t = useTheme();
  return (
    <View style={{ alignSelf: "flex-start", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2, backgroundColor: tone === "warn" ? t.warnBg : t.wash }}>
      <Text style={{ fontSize: 12, fontWeight: "600", color: tone === "warn" ? t.warn : t.ink2 }}>{children}</Text>
    </View>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text accessibilityRole="alert" style={{ color: t.down, marginVertical: 6 }}>{children}</Text>;
}

const s = StyleSheet.create({
  btn: { minHeight: 44, paddingHorizontal: 16, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 14 },
});
