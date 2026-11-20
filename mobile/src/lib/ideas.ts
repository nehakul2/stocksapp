import { Idea } from "@/lib/api";

const LABEL: Record<Idea["action"], string> = { buy: "Consider buying", hold: "Hold", sell: "Consider selling" };

/** "Consider buying (strong)"; a hold has no strength to show. */
export function ideaText(i: Idea): string {
  return i.action === "hold" ? LABEL.hold : `${LABEL[i.action]} (${i.strength})`;
}
