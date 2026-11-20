import { Idea } from "@/lib/api";

export const IDEA_LABEL: Record<Idea["action"], string> = {
  buy: "Consider buying",
  hold: "Hold",
  sell: "Consider selling",
};

/** "Consider buying (strong)"; a hold has no strength to show. */
export function ideaText(i: Idea): string {
  return i.action === "hold" ? IDEA_LABEL.hold : `${IDEA_LABEL[i.action]} (${i.strength})`;
}
