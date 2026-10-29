import { lexicon, resolveSubject, rows, type Fact } from "@/lib/hooly";
import { slotOf, tree, type AttrNode, type Segment } from "@/lib/tree";

/* Claim generator: builds true, new claims from the fact tree, following the
   starter's contracts (claim-forms.md, value-forms.md, entry.schema.json). */

export const AS_OF = "2026-10-29";
export type ClaimType = "fact" | "compare" | "change" | "at_event" | "relation";
type V = Fact["value"];
export type Claim = { id: string; type: ClaimType; text: string; form: Record<string, unknown>; label: "true"; confidence: number };
export type Rejected = { type: ClaimType; text: string; reason: string };

/* ---------- value-forms.md writers ---------- */
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SYMBOL: Record<string, string> = { EUR: "€", USD: "$", GBP: "£" };
const UNIT_SYMBOLS = new Set(["B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh", "Hz", "kHz", "MHz", "GHz", "mW", "W", "kW"]);
const DUR: Record<string, [string, string]> = { ms: ["ms", "ms"], s: ["second", "seconds"], min: ["minute", "minutes"], h: ["hour", "hours"], day: ["day", "days"], week: ["week", "weeks"], month: ["month", "months"], year: ["year", "years"] };

function num(n: number): string | null {
  const s = n.toLocaleString("en-US", { maximumFractionDigits: 6 });
  return /\.\d{3}$/.test(s) ? null : s; // "1.500" is ambiguous to the referee
}
function plural(noun: string, n: number) {
  if (n === 1) return noun;
  if (noun === "person") return "people";
  if (/[^aeiou]y$/.test(noun)) return noun.slice(0, -1) + "ies";
  if (/(s|x|ch|sh)$/.test(noun)) return noun + "es";
  return noun + "s";
}

export function writeValue(v: V): string | null {
  const n = typeof v.value === "number" ? v.value : NaN;
  switch (v.kind) {
    case "money": {
      const a = num(n); if (a === null || n < 0) return null;
      const c = String(v["currency"]);
      const price = SYMBOL[c] ? `${SYMBOL[c]}${a}` : `${c} ${a}`;
      return v["per"] ? `${price} per ${v["per"]}` : price;
    }
    case "quantity": {
      const a = num(n); if (a === null || !v.unit) return null;
      return UNIT_SYMBOLS.has(v.unit) ? `${a} ${v.unit}` : `${a} ${plural(v.unit, n)}`;
    }
    case "duration": {
      const a = num(n), u = DUR[v.unit ?? ""]; if (a === null || !u) return null;
      return `${a} ${n === 1 ? u[0] : u[1]}`;
    }
    case "percent": { const a = num(n); return a === null ? null : `${a}%`; }
    case "version": return /^\d+(\.\d+)*$/.test(String(v.value)) ? `version ${v.value}` : null;
    case "date": {
      const m = String(v.value).match(/^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/);
      if (!m) return null;
      if (m[3]) return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
      if (m[2]) return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
      return m[1]!;
    }
    case "name": return String(v.value).trim() || null;
    default: return null;
  }
}

const ACRONYM = new Set(["ceo", "cto", "cfo", "coo", "soc2", "soc", "api", "ai", "gdpr", "nps"]);
export const attrWords = (a: string) => a.split("_").map((w) => (ACRONYM.has(w) ? w.toUpperCase() : w)).join(" ");

/* ---------- referee-style validator ---------- */
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const NAMES = lexicon.subjects.flatMap((s) => [s.name, ...s.aliases].map((n) => ({ n, s: s.name }))).sort((a, b) => b.n.length - a.n.length);
const NAME_RE = new RegExp(`(?<![A-Za-z0-9])(${NAMES.map((x) => esc(x.n)).join("|")})(?![A-Za-z0-9])`, "gi");
const REFUSED = [...MONTHS, "spring", "summer", "autumn", "winter", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
  "ago", "yesterday", "tomorrow", "once", "formerly", "previously", "originally", "initially", "recently", "lately", "soon", "eventually", "then", "before", "after", "since", "until", "till", "earlier", "later", "used to", "last week", "last month", "last quarter", "last year", "next week", "next month", "next quarter", "next year", "in the past", "in the future", "at the time", "at that time", "today", "now", "currently", "still"];
const NEGATION = /\b(not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n't\b/i;
const NUMBER_WORDS = /\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|dozen|single|double|half)\b/i;
const APPROX = /\b(about|around|approximately|approx|roughly|nearly|almost|circa|some|over|under|at least|at most|up to|more than|less than)\b|~|≈|±/i;
const wordRe = (w: string) => new RegExp(`(?<![A-Za-z])${esc(w)}(?![A-Za-z])`, "i");

/** Names of entities in a text (longest match wins, so "Hooly AI Pro" is not "Hooly"). */
export function namesIn(text: string): string[] {
  return [...text.matchAll(NAME_RE)].map((m) => resolveSubject(m[1]!) ?? m[1]!);
}

type Check = { required: string[]; values: string[]; allowNo?: boolean; eventPhrase?: string; compare?: boolean; opPhrase?: string };
export function validateText(text: string, c: Check): string | null {
  if (text.length > 300) return "longer than 300 characters";
  if (/[.!?]\s/.test(text.trim().slice(0, -1))) return "more than one sentence";
  const found = namesIn(text);
  for (const r of c.required) if (!found.includes(r)) return `does not name ${r}`;
  const extra = found.filter((f) => !c.required.includes(f));
  if (extra.length) return `names another entity: ${extra[0]}`;
  let rest = text;
  for (const v of c.values) {
    if (!rest.includes(v)) return `value “${v}” not written`;
    rest = rest.replace(v, " ");
  }
  if (c.eventPhrase) { if (!rest.includes(c.eventPhrase)) return "no event phrase"; rest = rest.replace(c.eventPhrase, " "); }
  rest = rest.replace(NAME_RE, " ");
  if (c.opPhrase) rest = rest.replace(c.opPhrase, " ");
  if (/\d/.test(rest)) return "holds another number or date";
  if (NUMBER_WORDS.test(rest)) return "holds a number word";
  if (APPROX.test(rest)) return "holds a comparison or approximation word";
  const bad = REFUSED.find((w) => wordRe(w).test(rest));
  if (bad) return `holds the date/time word “${bad}”`;
  if (NEGATION.test(rest) && !(c.allowNo && /: no\.$/.test(text))) return "holds a negation";
  return null;
}

const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const practiceTexts = new Set(rows.map((r) => norm(r.text)));
export const isNew = (text: string) => !practiceTexts.has(norm(text));

/* ---------- reading the tree safely ---------- */
type Slot = { subject: string; attribute: string; slot: string; segs: Segment[]; node: AttrNode; unsure: number; hype: number; stable: boolean };

function slotsOf(subject: string, node: AttrNode): Slot[] {
  const by = new Map<string, Segment[]>();
  for (const s of node.segments) by.set(s.slot, [...(by.get(s.slot) ?? []), s]);
  return [...by.entries()].map(([slot, segs]) => {
    // unstable: a value comes back after being replaced, or two values start on one day
    const seen = new Set<string>();
    let stable = true;
    segs.forEach((s, i) => {
      if (seen.has(s.value)) stable = false;
      seen.add(s.value);
      if (i && segs[i - 1]!.from === s.from) stable = false;
    });
    const same = (o: { raw: V }) => slotOf(o.raw) === slot;
    return { subject, attribute: node.attribute, slot, segs, node, unsure: node.unsure.filter(same).length, hype: node.falseValues.filter(same).length, stable };
  });
}
const allSlots: Slot[] = [...tree.entries()].flatMap(([subject, attrs]) =>
  lexicon.subjects.some((s) => s.name === subject) ? [...attrs.values()].flatMap((n) => slotsOf(subject, n)) : [],
);

function conf(seg: Segment, slot: Slot) {
  let c = 0.62 + 0.08 * Math.min(seg.obs.length, 4);
  if (slot.unsure) c -= 0.08;
  if (slot.hype) c -= 0.03;
  if (!slot.stable) c -= 0.2;
  return Math.max(0.5, Math.min(0.97, Number(c.toFixed(2))));
}
export const MIN_CONF = 0.7;
const exact = (v: V): V => { const { op: _op, ...rest } = v; return rest as V; };

/** Event dates: the event's own `date` fact, by majority of true full-day values. */
export function eventDates(): Map<string, string> {
  const out = new Map<string, string>();
  for (const e of lexicon.events) {
    const n = tree.get(e)?.get("date");
    if (!n) continue;
    const counts = new Map<string, number>();
    for (const o of n.all) if (o.label === "true" && /^\d{4}-\d{2}-\d{2}$/.test(String(o.raw.value))) counts.set(String(o.raw.value), (counts.get(String(o.raw.value)) ?? 0) + 1);
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const total = best.reduce((a, b) => a + b[1], 0);
    if (best[0] && best[0][1] >= 2 && best[0][1] / total >= 0.75) out.set(e, best[0][0]);
  }
  return out;
}

/* ---------- candidate builders ---------- */
type Cand = Omit<Claim, "id" | "label"> & { check: Check };

function factCands(): Cand[] {
  const out: Cand[] = [];
  for (const s of allSlots) {
    if (!s.stable) continue;
    const seg = s.segs.at(-1)!;
    const v = exact(seg.raw), a = attrWords(s.attribute);
    const form = { subject: s.subject, attribute: s.attribute, value: v };
    if (v.kind === "boolean") {
      const text = `For ${s.subject}, ${a}: ${v.value ? "yes" : "no"}.`;
      out.push({ type: "fact", text, form, confidence: conf(seg, s), check: { required: [s.subject], values: [a], allowNo: !v.value } });
      continue;
    }
    const w = writeValue(v); if (!w) continue;
    const req = v.kind === "name" && resolveSubject(w) ? [s.subject, resolveSubject(w)!] : [s.subject];
    out.push({ type: "fact", text: `For ${s.subject}, the ${a} is ${w}.`, form, confidence: conf(seg, s), check: { required: [...new Set(req)], values: [w] } });
  }
  return out;
}

const AMOUNT = new Set(["money", "quantity", "percent", "duration", "version"]);
const DUR_S: Record<string, number> = { ms: 0.001, s: 1, min: 60, h: 3600, day: 86400, week: 604800 };
function magnitude(v: V): number | null {
  if (v.kind === "version") { const p = String(v.value).split(".").map(Number); return p[0]! * 1e6 + (p[1] ?? 0) * 1e3 + (p[2] ?? 0); }
  if (v.kind === "duration" && v.unit !== "month" && v.unit !== "year") return Number(v.value) * (DUR_S[v.unit ?? ""] ?? NaN);
  if (v.kind === "date") return /^\d{4}-\d{2}-\d{2}$/.test(String(v.value)) ? Date.parse(String(v.value)) : null;
  return typeof v.value === "number" ? v.value : null;
}
function compareKey(v: V, slot: string) {
  if (v.kind === "quantity") return `${slot}:${v.unit}`; // same unit only
  if (v.kind === "version") return `version`;
  return slot;
}

function compareCands(): Cand[] {
  const groups = new Map<string, { s: Slot; seg: Segment; m: number }[]>();
  for (const s of allSlots) {
    if (!s.stable) continue;
    const seg = s.segs.at(-1)!, v = exact(seg.raw);
    if (!AMOUNT.has(v.kind) && v.kind !== "date") continue;
    const m = magnitude(v); if (m === null || !Number.isFinite(m)) continue;
    const k = compareKey(v, s.slot);
    groups.set(k, [...(groups.get(k) ?? []), { s, seg, m }]);
  }
  const out: Cand[] = [];
  for (const [k, g] of groups) {
    const isDate = k === "date";
    for (const L of g) for (const R of g) {
      if (L === R || L.s.subject === R.s.subject && L.s.attribute === R.s.attribute) continue;
      if (L.s.subject === R.s.subject) continue; // keep left and right names distinct
      const op = L.m > R.m ? "gt" : L.m < R.m ? "lt" : "eq";
      if (op === "lt" && !isDate) continue; // keep one direction per pair for amounts
      const phrase = isDate ? { gt: "is later than", lt: "is earlier than", eq: "is on the same day as" }[op] : { gt: "is higher than", lt: "is lower than", eq: "is the same as" }[op];
      const text = `The ${attrWords(L.s.attribute)} of ${L.s.subject} ${phrase} the ${attrWords(R.s.attribute)} of ${R.s.subject}.`;
      const c = Math.min(conf(L.seg, L.s), conf(R.seg, R.s)) - (op === "eq" ? 0.05 : 0);
      out.push({ type: "compare", text, confidence: Number(c.toFixed(2)), form: { left: { subject: L.s.subject, attribute: L.s.attribute }, right: { subject: R.s.subject, attribute: R.s.attribute }, op }, check: { required: [L.s.subject, R.s.subject], values: [], compare: true, opPhrase: phrase } });
    }
  }
  return out;
}

function changeCands(): Cand[] {
  const out: Cand[] = [];
  for (const s of allSlots) {
    if (!s.stable || s.segs.length < 2) continue;
    for (let i = 1; i < s.segs.length; i++) {
      const A = s.segs[i - 1]!, B = s.segs[i]!;
      const from = exact(A.raw), to = exact(B.raw);
      if (from.kind === "boolean") continue;
      const wa = writeValue(from), wb = writeValue(to); if (!wa || !wb || wa === wb) continue;
      const text = `For ${s.subject}, the ${attrWords(s.attribute)} went from ${wa} to ${wb}.`;
      const c = Math.min(conf(A, s), conf(B, s));
      const req = [s.subject, ...[wa, wb].map((w) => (from.kind === "name" ? resolveSubject(w) : null)).filter((x): x is string => !!x)];
      out.push({ type: "change", text, confidence: c, form: { subject: s.subject, attribute: s.attribute, from, to }, check: { required: [...new Set(req)], values: [`from ${wa}`, `to ${wb}`] } });
    }
  }
  return out;
}

function atEventCands(): Cand[] {
  const out: Cand[] = [];
  for (const [event, d] of eventDates()) {
    for (const s of allSlots) {
      if (!s.stable || s.subject === event && s.attribute === "date") continue;
      // the segment must be observed both on/before and on/after the event day
      const seg = s.segs.find((g) => g.from <= d && (g.to === null || g.to > d) && g.obs.some((o) => o.date <= d) && g.obs.some((o) => o.date >= d));
      if (!seg) continue;
      const v = exact(seg.raw); if (v.kind === "boolean") continue;
      const w = writeValue(v); if (!w) continue;
      const text = `For ${s.subject}, the ${attrWords(s.attribute)} was ${w} at ${event}.`;
      const req = [s.subject, event, ...(v.kind === "name" && resolveSubject(w) ? [resolveSubject(w)!] : [])];
      out.push({ type: "at_event", text, confidence: Number((conf(seg, s) - 0.02).toFixed(2)), form: { subject: s.subject, attribute: s.attribute, event, value: v }, check: { required: [...new Set(req)], values: [w], eventPhrase: `at ${event}` } });
    }
  }
  return out;
}

function relationCands(): Cand[] {
  const out: Cand[] = [];
  for (const link of allSlots) {
    if (link.slot !== "name" || !link.stable) continue;
    for (const ls of link.segs) {
      const target = resolveSubject(String(ls.raw.value));
      if (!target || target === link.subject) continue;
      for (const t of allSlots.filter((x) => x.subject === target && x.stable && x.segs.length === 1)) {
        const seg = t.segs[0]!, v = exact(seg.raw);
        if (v.kind === "boolean" || v.kind === "name") continue;
        const w = writeValue(v); if (!w) continue;
        const text = `For the ${attrWords(link.attribute)} of ${link.subject}, the ${attrWords(t.attribute)} is ${w}.`;
        const c = Math.min(conf(ls, link), conf(seg, t));
        out.push({ type: "relation", text, confidence: c, form: { subject: link.subject, link: link.attribute, target, attribute: t.attribute, value: v }, check: { required: [link.subject], values: [w, attrWords(link.attribute)] } });
      }
    }
  }
  return out;
}

/* ---------- assemble exactly 1,000 ---------- */
export const TYPES: ClaimType[] = ["fact", "compare", "change", "at_event", "relation"];

export function generateClaims(target = 1000) {
  const rejected: Rejected[] = [];
  const pools = new Map<ClaimType, Cand[]>();
  const seen = new Set<string>();
  const all = [...factCands(), ...changeCands(), ...atEventCands(), ...relationCands(), ...compareCands()];
  const produced = Object.fromEntries(TYPES.map((t) => [t, 0])) as Record<ClaimType, number>;
  for (const c of all) {
    produced[c.type]++;
    const reason = c.confidence < MIN_CONF ? `confidence ${c.confidence} below ${MIN_CONF}` : !isNew(c.text) ? "copies a practice row" : seen.has(norm(c.text)) ? "duplicate" : validateText(c.text, c.check);
    if (reason) { rejected.push({ type: c.type, text: c.text, reason }); continue; }
    seen.add(norm(c.text));
    pools.set(c.type, [...(pools.get(c.type) ?? []), c]);
  }
  for (const p of pools.values()) p.sort((a, b) => b.confidence - a.confidence);
  // round-robin across types, best first, so every type is represented; compares fill the rest
  const picked: Cand[] = [];
  const idx = new Map<ClaimType, number>();
  while (picked.length < target) {
    let added = false;
    for (const t of TYPES) {
      const p = pools.get(t) ?? [], i = idx.get(t) ?? 0;
      if (i < p.length && picked.length < target) { picked.push(p[i]!); idx.set(t, i + 1); added = true; }
    }
    if (!added) break;
  }
  const claims: Claim[] = picked.map((c, i) => ({ id: `claim-${String(i + 1).padStart(4, "0")}`, type: c.type, text: c.text, form: c.form, label: "true", confidence: c.confidence }));
  const valid = Object.fromEntries(TYPES.map((t) => [t, pools.get(t)?.length ?? 0])) as Record<ClaimType, number>;
  return { claims, rejected, produced, valid, shortfall: Math.max(0, target - claims.length) };
}

const cell = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
export function toCsv(claims: Claim[]): string {
  const lines = ["id,type,text,form,label,confidence"];
  for (const c of claims) lines.push([c.id, c.type, c.text, JSON.stringify(c.form), c.label, String(c.confidence)].map(cell).join(","));
  return lines.join("\n") + "\n";
}

/** practice.csv (id,text,date,label,form) with the new claims appended as extra rows. */
export function toPracticePlusCsv(claims: Claim[]): string {
  const lines = ["id,text,date,label,form"];
  for (const r of rows) lines.push([r.id, r.text, r.date, r.label, JSON.stringify(r.form)].map(cell).join(","));
  for (const c of claims) lines.push([c.id, c.text, AS_OF, c.label, JSON.stringify(c.form)].map(cell).join(","));
  return lines.join("\n") + "\n";
}
