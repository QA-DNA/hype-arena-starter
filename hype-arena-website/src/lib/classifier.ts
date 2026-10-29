import { lexicon, rows, buildTimeline, trueChanges } from "@/lib/hooly";

/* Browser port of the pure building blocks of label_rows.py, so the
   classifier page can show the algorithm working on a real row. */

const MONTHS: Record<string, number> = Object.fromEntries(
  "january february march april may june july august september october november december".split(" ").flatMap((m, i) => [
    [m, i + 1],
    [m.slice(0, 3), i + 1],
  ]),
);
const NEG = /\b(not|no|never|without|n't|isn't|doesn't|don't|lacks?|missing|none|off|disabled|unavailable)\b|n't/i;
const SCALE: Record<string, number> = { thousand: 1e3, k: 1e3, million: 1e6, m: 1e6, mn: 1e6, billion: 1e9, bn: 1e9, b: 1e9, trillion: 1e12 };

function normNum(x: number): string {
  return Math.abs(x - Math.round(x)) < 1e-9 ? String(Math.round(x)) : String(Number(x.toPrecision(6)));
}

/** Block 1 — subject finder: longest lexicon name/alias wins, no overlaps. */
export function findSubjects(text: string): string[] {
  const t = text.toLowerCase();
  const alias: [string, string][] = [];
  for (const s of lexicon.subjects) for (const n of [s.name, ...s.aliases]) alias.push([n.toLowerCase(), s.name]);
  alias.sort((a, b) => b[0].length - a[0].length);
  const taken = new Array<boolean>(t.length).fill(false);
  const found: [number, string][] = [];
  for (const [a, name] of alias) {
    const re = new RegExp(`(?<![\\w])${a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w])`, "g");
    for (const m of t.matchAll(re)) {
      const i = m.index;
      if (taken.slice(i, i + a.length).some(Boolean)) continue;
      for (let j = i; j < i + a.length; j++) taken[j] = true;
      found.push([i, name]);
    }
  }
  return found.sort((a, b) => a[0] - b[0]).map(([, n]) => n);
}

/** Block 3 — value extractor: every value token a sentence holds. */
export function textTokens(text: string): Set<string> {
  const t = text.replace(/\u00a0/g, " ");
  const toks = new Set<string>();
  for (const m of t.matchAll(/\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b/g)) {
    const mo = MONTHS[m[2]!.toLowerCase()];
    if (mo) toks.add(`date:${m[3]}-${String(mo).padStart(2, "0")}-${m[1]!.padStart(2, "0")}`);
  }
  for (const m of t.matchAll(/\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b/g)) {
    const mo = MONTHS[m[1]!.toLowerCase()];
    if (mo) toks.add(`date:${m[3]}-${String(mo).padStart(2, "0")}-${m[2]!.padStart(2, "0")}`);
  }
  for (const m of t.matchAll(/\b([A-Za-z]{3,9})\s+(\d{4})\b/g)) {
    const mo = MONTHS[m[1]!.toLowerCase()];
    if (mo) toks.add(`date:${m[2]}-${String(mo).padStart(2, "0")}`);
  }
  for (const m of t.matchAll(/\b(\d{4})-(\d{2})-(\d{2})\b/g)) toks.add(`date:${m[1]}-${m[2]}-${m[3]}`);
  for (const m of t.matchAll(/\b(19\d\d|20\d\d)\b/g)) toks.add(`date:${m[1]}`);
  for (const m of t.matchAll(/\b[vV]?(\d+(?:\.\d+)+)\b/g)) toks.add(`ver:${m[1]}`);
  for (const m of t.matchAll(/(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|trillion|bn|mn|k|m|b)?\b/gi)) {
    let v = Number(m[1]!.replace(/,/g, ""));
    if (Number.isNaN(v)) continue;
    const sc = m[2]?.toLowerCase();
    if (sc) v *= SCALE[sc]!;
    toks.add(`num:${normNum(v)}`);
    if (sc === "m" || sc === "b") toks.add(`num:${normNum(Number(m[1]!.replace(/,/g, "")))}`);
  }
  toks.add(NEG.test(t) ? "bool:false" : "bool:true");
  return toks;
}

/** The same normalisation the script applies to a parsed fact value. */
export function valueToken(v: { kind: string; value: unknown }): string {
  const k = v.kind;
  if (["quantity", "money", "percent", "duration"].includes(k)) return `num:${normNum(Number(v.value))}`;
  if (k === "date") return `date:${v.value}`;
  if (k === "version") return `ver:${v.value}`;
  if (k === "boolean") return `bool:${String(Boolean(v.value)).toLowerCase()}`;
  if (k === "name") return `name:${String(v.value).toLowerCase()}`;
  return `${k}:${v.value}`;
}

/* ---- worked example: one real practice row walked through every block ---- */

export const EXAMPLE_ID = "p-1713";

export function buildExample() {
  const row = rows.find((r) => r.id === EXAMPLE_ID)!;
  const subjects = findSubjects(row.text);
  const tokens = [...textTokens(row.text)].sort();
  const fact = row.form[0]!;
  const tl = buildTimeline(rows, fact.subject, fact.attribute);
  const steps = trueChanges(tl).map((p) => ({ date: p.date, token: valueToken(factValueOf(p.rowId, fact.attribute)) }));
  const want = valueToken(fact.value);
  const curMatch = tokens.includes(want);
  const trueToks = new Set(tl.filter((p) => p.label === "true").map((p) => valueToken(factValueOf(p.rowId, fact.attribute))));
  const lies = new Set(tl.filter((p) => p.label === "false").map((p) => valueToken(factValueOf(p.rowId, fact.attribute))).filter((t) => !trueToks.has(t)));
  const lieMatch = [...lies].some((t) => tokens.includes(t));
  return { row, subjects, tokens, steps, want, curMatch, lieMatch, negated: tokens.includes("bool:false") };
}

function factValueOf(rowId: string, attribute: string) {
  const r = rows.find((x) => x.id === rowId)!;
  return r.form.find((f) => f.attribute === attribute)!.value;
}

/* ---- the six building blocks, in plain words ---- */

export type Block = { id: string; name: string; short: string; does: string; input: string; output: string; details: string[]; live?: string };

export const PIPELINE: Block[] = [
  {
    id: "subject",
    name: "1 · Subject finder",
    short: "Who is the sentence about?",
    does: "Works out which Hooly thing the sentence talks about. It looks for the longest lexicon name or alias in the text. If the sentence names nothing, it reuses the subject of earlier sentences from the same day.",
    input: "raw sentence",
    output: "canonical subject, e.g. “Hooly AI Pro”",
    details: ["Longest alias wins, so “Hooly AI” is not stolen from inside “Hooly AI Pro”.", "Pronouns like “it” or “he” inherit the running subject of the page."],
    live: "subjects",
  },
  {
    id: "router",
    name: "2 · Fact router",
    short: "Which fact slot does it touch?",
    does: "Decides which fact slot the sentence is about — which subject and which attribute, like price or team size. A small machine-learning model (word and letter patterns + a linear classifier) is trained on the practice rows, whose true slots are known.",
    input: "sentence + subject hints",
    output: "subject‖attribute + how sure the router is",
    details: ["Trained only on the practice forms, never on the rows it must label.", "Also returns the runner-up slot, so the judge can see how close the call was."],
  },
  {
    id: "extractor",
    name: "3 · Value extractor",
    short: "What values does it mention?",
    does: "Pulls every value out of the sentence as normalised tokens: numbers (with thousand/million scales), dates in any format, version numbers, names, and whether the sentence is negated.",
    input: "raw sentence",
    output: "tokens like num:59, date:2026-04-03, bool:true",
    details: ["All date spellings become one form: “12 January 2026”, “January 12, 2026” and “2026-01-12” are the same token.", "“not”, “never”, “without” flip the boolean token to bool:false."],
    live: "tokens",
  },
  {
    id: "kb",
    name: "4 · Knowledge base",
    short: "What was true on that date?",
    does: "The memory of Hooly's world. From the rows labelled true it builds a dated timeline of values for every subject+attribute. Values seen only in false rows are kept separately as known lies.",
    input: "labelled practice rows",
    output: "per fact: current value, past values, future values, known lies",
    details: ["The timeline answers: what was the value on this date? What was it before? What comes next?", "A value that appears only in false rows becomes a known lie and can never become true."],
    live: "kb",
  },
  {
    id: "features",
    name: "5 · Evidence features",
    short: "Does the text match the truth?",
    does: "Compares the sentence against the knowledge base and turns the comparison into yes/no measurements: does the text hold the value valid on its date? an old value? a future value? a known lie? What do the other sentences about the same fact say?",
    input: "tokens + knowledge base + router guess",
    output: "about 30 measurements (features) per row",
    details: ["Key features: cur_match, past_match, fut_match, lie_match, mismatch, bool_conflict.", "Voting: unlabelled sentences about the same fact also cast a vote on which value they support.", "Hedge words like “about”, “soon”, “reportedly” are measured too."],
    live: "features",
  },
  {
    id: "judge",
    name: "6 · Judge",
    short: "True, false or unsure?",
    does: "A gradient-boosted forest of decision trees reads the measurements and votes true, false or unsure, with a probability for each. The confidence reported is the winning share between true and false, rescaled to the allowed 0.5–1.0 range.",
    input: "feature vector",
    output: "label + confidence",
    details: ["Trained on out-of-fold features, so it never judges a row whose evidence it has already seen.", "unsure rows report no confidence, as the rules require."],
  },
];
