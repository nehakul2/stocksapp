import { Stack, useLocalSearchParams } from "expo-router";
import ChatView from "@/components/ChatView";

// Chat about one stock, opened from the stock page.
export default function StockChat() {
  const { ticker } = useLocalSearchParams<{ ticker: string }>();
  const symbol = decodeURIComponent(String(ticker));
  return (
    <>
      <Stack.Screen options={{ title: `Ask about ${symbol}` }} />
      <ChatView ticker={symbol} />
    </>
  );
}
