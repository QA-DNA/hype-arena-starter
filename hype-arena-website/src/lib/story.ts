import { generateClaims, TYPES, writeValue, type ClaimType } from "@/lib/claims";
import { rows } from "@/lib/hooly";
import { tree } from "@/lib/tree";

/* Data for the "How it works" story page: real examples picked from the real generator. */

export const KIND: Record<ClaimType, { icon: string; ask: string }> = {
  fact: { icon: "fact", ask: "What is it now?" },
  compare: { icon: "compare", ask: "Which is bigger?" },
  change: { icon: "change", ask: "What changed?" },
  at_event: { icon: "at_event", ask: "What was it at the event?" },
  relation: { icon: "relation", ask: "Who is connected?" },
};

export const GATES = ["Enough proof?", "Is it new?", "Already said it?", "Follows the wording rules?"] as const;

/** Which gate a rejection reason fails at (0..3). */
export function gateOf(reason: string): number {
  if (reason.startsWith("confidence")) return 0;
  if (reason === "copies a practice row") return 1;
  if (reason === "duplicate") return 2;
  return 3;
}

/** Turn a raw reason into words a 10-year-old understands. */
export function kidReason(reason: string): string {
  if (reason.startsWith("confidence")) return "Not enough notes agree, so we can't be sure it's true.";
  if (reason === "copies a practice row") return "This is already in the notes, so it isn't new.";
  if (reason === "duplicate") return "We already said this one.";
  const word = reason.match(/word “(.+)”/);
  if (word) return `Uses the word “${word[1]}”, which isn't allowed.`;
  if (reason.startsWith("names another entity")) return "Mentions something extra that could confuse the judge.";
  if (reason.includes("number")) return "Has an extra number that could confuse the judge.";
  if (reason.includes("negation")) return "Says “not”, which isn't allowed.";
  if (reason.includes("sentence")) return "It's more than one sentence.";
  if (reason.includes("not written")) return "The answer isn't written the way the rules want.";
  return "Breaks a wording rule.";
}

export type Example = { type: ClaimType; text: string; confidence: number; ok: boolean; gate: number; why: string };

export function buildStory() {
  const r = generateClaims();
  const accepted: Example[] = TYPES.map((t) => {
    const c = r.claims.find((x) => x.type === t && (t !== "fact" || x.text.includes("Hooly AI Pro"))) ?? r.claims.find((x) => x.type === t)!;
    return { type: t, text: c.text, confidence: c.confidence, ok: true, gate: 4, why: "Passed every check." };
  });
  const seenWhy = new Set<string>();
  const rejected: Example[] = [];
  for (const x of r.rejected) {
    const why = kidReason(x.reason);
    if (seenWhy.has(why) || x.text.length > 140) continue;
    seenWhy.add(why);
    const m = x.reason.match(/confidence ([\d.]+)/);
    rejected.push({ type: x.type, text: x.text, confidence: m ? Number(m[1]) : 0.8, ok: false, gate: gateOf(x.reason), why });
    if (rejected.length === 5) break;
  }
  const notes = rows.filter((_, i) => i % 79 === 0).slice(0, 24).map((x) => ({ id: x.id, text: x.text, label: x.label }));
  const price = tree.get("Hooly AI Pro")?.get("price");
  const leaves = (price?.segments ?? []).filter((s) => s.slot === "money:EUR:month").map((s) => ({ value: writeValue(s.raw) ?? s.value, from: s.from, proof: s.obs.length }));
  const counts = { true: rows.filter((x) => x.label === "true").length, false: rows.filter((x) => x.label === "false").length, unsure: rows.filter((x) => x.label === "unsure").length };
  const perType = Object.fromEntries(TYPES.map((t) => [t, r.claims.filter((c) => c.type === t).length])) as Record<ClaimType, number>;
  return { accepted, rejected, notes, leaves, counts, perType, total: r.claims.length, tried: r.rejected.length + r.claims.length, claims: r.claims };
}
