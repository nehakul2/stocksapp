import { useColorScheme } from "react-native";

const light = {
  bg: "#f6f6f1", card: "#ffffff", ink: "#1f2430", ink2: "#4a5262", muted: "#7a8191", rule: "#e2e2da",
  accent: "#2b4a7a", accentInk: "#ffffff", up: "#1f7a4d", down: "#b3372f", warn: "#8a5a14", warnBg: "#f2e4c8", wash: "#eeeee6",
};
const dark: typeof light = {
  bg: "#14171d", card: "#1d2129", ink: "#eceef2", ink2: "#b8bdc9", muted: "#8a91a1", rule: "#2c313c",
  accent: "#8fb0e6", accentInk: "#14171d", up: "#5ec58f", down: "#ef7d74", warn: "#e6b866", warnBg: "#3a2f18", wash: "#242932",
};

export type Theme = typeof light;
export const useTheme = (): Theme => (useColorScheme() === "dark" ? dark : light);
