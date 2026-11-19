import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, View } from "react-native";
import { AuthProvider, useAuth } from "@/lib/auth";
import { DataProvider } from "@/lib/data";
import { useTheme } from "@/lib/theme";

function Routes() {
  const { token, ready } = useAuth();
  const t = useTheme();
  if (!ready) {
    return <View style={{ flex: 1, backgroundColor: t.bg, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={t.accent} /></View>;
  }
  return (
    <Stack screenOptions={{ headerStyle: { backgroundColor: t.bg }, headerTintColor: t.accent, headerTitleStyle: { color: t.ink }, contentStyle: { backgroundColor: t.bg }, headerShadowVisible: false }}>
      <Stack.Protected guard={!!token}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="stock/[ticker]" options={{ title: "", headerBackTitle: "Back" }} />
      </Stack.Protected>
      <Stack.Protected guard={!token}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <DataProvider>
        <StatusBar style="auto" />
        <Routes />
      </DataProvider>
    </AuthProvider>
  );
}
