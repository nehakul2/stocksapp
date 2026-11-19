import { Tabs } from "expo-router";
import { ColorValue, Text } from "react-native";
import { useData } from "@/lib/data";
import { useTheme } from "@/lib/theme";

const Glyph = ({ c, color }: { c: string; color: ColorValue }) => <Text style={{ color, fontSize: 20 }}>{c}</Text>;

export default function TabsLayout() {
  const t = useTheme();
  const { check } = useData();
  const firing = check?.firing.length ?? 0;
  return (
    <Tabs screenOptions={{
      tabBarActiveTintColor: t.accent, tabBarInactiveTintColor: t.muted,
      tabBarStyle: { backgroundColor: t.card, borderTopColor: t.rule },
      headerStyle: { backgroundColor: t.bg }, headerTitleStyle: { color: t.ink }, headerShadowVisible: false,
    }}>
      <Tabs.Screen name="index" options={{ title: "Watchlist", tabBarIcon: ({ color }) => <Glyph c="★" color={color} /> }} />
      <Tabs.Screen name="alerts" options={{ title: "Alerts", tabBarBadge: firing > 0 ? firing : undefined, tabBarIcon: ({ color }) => <Glyph c="🔔︎" color={color} /> }} />
    </Tabs>
  );
}
