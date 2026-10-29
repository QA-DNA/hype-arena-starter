import { formatValue, lexicon, resolveSubject, rows, type Fact, type Label, type Row } from "@/lib/hooly";

/* ---------- 1. Event timeline: anchor every date between events ---------- */
export type EventAnchor = { name: string; date: string | null; mentions: number };

/** An event's date = first practice row whose text mentions it. Unmentioned events stay unanchored. */
export function buildEvents(all: Row[] = rows): EventAnchor[] {
  return lexicon.events
    .map((name) => {
      const hits = all.filter((r) => r.text.toLowerCase().includes(name.toLowerCase())).map((r) => r.date).sort();
      return { name, date: hits[0] ?? null, mentions: hits.length };
    })
    .sort((a, b) => (a.date ?? "9").localeCompare(b.date ?? "9"));
}
export const events = buildEvents();
const datedEvents = events.filter((e) => e.date);

export type Era = { after: string | null; before: string | null };
/** Which events a date sits between (last event on/before, next event after). */
export function eraOf(date: string, evs = datedEvents): Era {
  let after: string | null = null, before: string | null = null;
  for (const e of evs) {
    if (e.date! <= date) after = e.name;
    else { before = e.name; break; }
  }
  return { after, before };
}

/* ---------- 2. The tree: subject → attribute → value segment → observations ---------- */
export type Obs = { rowId: string; date: string; label: Label; value: string; raw: Fact["value"]; text: string };
/** A period where one true value holds: [from, to). */
export type Segment = { value: string; raw: Fact["value"]; slot: string; from: string; to: string | null; era: Era; obs: Obs[] };

const DIM: Record<string, string> = { b: "data", kb: "data", mb: "data", gb: "data", tb: "data", mm: "len", cm: "len", m: "len", km: "len", in: "len", g: "mass", kg: "mass", hz: "freq", khz: "freq", mhz: "freq", ghz: "freq", mw: "pow", w: "pow", kw: "pow" };
/** Values in the same slot compete for one truth: a monthly price never replaces a yearly one. */
export function slotOf(v: Fact["value"]): string {
  if (v.kind === "money") return `money:${v["currency"]}:${v["per"] ?? "once"}`;
  if (v.kind === "quantity") { const u = String(v.unit ?? "").toLowerCase(); return `q:${DIM[u] ?? u.replace(/s$/, "")}`; }
  if (v.kind === "duration") return `d:${v.unit === "month" || v.unit === "year" ? v.unit : "time"}`;
  return v.kind;
}
export type AttrNode = { attribute: string; segments: Segment[]; falseValues: Obs[]; unsure: Obs[]; all: Obs[] };

const key = (v: Fact["value"]) => { const { op: _op, ...rest } = v; return formatValue(rest as Fact["value"]); };

export function buildTree(all: Row[] = rows, skipId?: string): Map<string, Map<string, AttrNode>> {
  const tree = new Map<string, Map<string, AttrNode>>();
  for (const r of all) {
    if (r.id === skipId) continue;
    for (const f of r.form) {
      const s = resolveSubject(f.subject) ?? f.subject;
      const attrs = tree.get(s) ?? tree.set(s, new Map()).get(s)!;
      const node = attrs.get(f.attribute) ?? attrs.set(f.attribute, { attribute: f.attribute, segments: [], falseValues: [], unsure: [], all: [] }).get(f.attribute)!;
      node.all.push({ rowId: r.id, date: r.date, label: r.label, value: key(f.value), raw: f.value, text: r.text });
    }
  }
  for (const attrs of tree.values())
    for (const n of attrs.values()) {
      n.all.sort((a, b) => a.date.localeCompare(b.date));
      for (const o of n.all) {
        if (o.label === "false") n.falseValues.push(o);
        else if (o.label === "unsure") n.unsure.push(o);
        else if (!o.raw["op"]) {
          // true exact observation: extend the current segment of its slot or open a new one
          const slot = slotOf(o.raw);
          const last = n.segments.filter((x) => x.slot === slot).at(-1);
          if (last && sameValue(last.raw, o.raw)) {
            last.obs.push(o);
            if (o.raw.kind === "date" && String(o.raw.value).length > String(last.raw.value).length) { last.raw = o.raw; last.value = o.value; }
          } else {
            if (last) last.to = o.date;
            n.segments.push({ value: o.value, raw: o.raw, slot, from: o.date, to: null, era: eraOf(o.date), obs: [o] });
          }
        }
      }
    }
  return tree;
}
export const tree = buildTree();

/* ---------- 3. Navigation: walk the tree to the value valid on a date ---------- */
export function segmentAt(node: AttrNode, date: string, slot?: string): Segment | null {
  let hit: Segment | null = null;
  for (const s of node.segments) if (s.from <= date && (!slot || s.slot === slot)) hit = s;
  return hit;
}

/* ---------- 4. Checking: fact verdict, then sentence = logical AND ---------- */
export type Verdict = { verdict: Label; confidence: number; reason: string; segment: Segment | null; era: Era };

function compareOp(op: string, claimed: number, actual: number) {
  return op === "le" ? actual <= claimed : op === "lt" ? actual < claimed : op === "ge" ? actual >= claimed : op === "gt" ? actual > claimed : actual === claimed;
}

/** Value equality tolerant of date precision ("2025-11" ≈ "2025-11-04") and name aliases ("Nimbus" ≈ "Nimbus Cloud"). */
export function sameValue(a: Fact["value"], b: Fact["value"]): boolean {
  if (a.kind === "date" || b.kind === "date") {
    const x = String(a.value), y = String(b.value);
    return x.startsWith(y) || y.startsWith(x);
  }
  if (a.kind === "name" && b.kind === "name") {
    const x = String(a.value), y = String(b.value);
    const rx = resolveSubject(x) ?? x.toLowerCase(), ry = resolveSubject(y) ?? y.toLowerCase();
    return rx === ry || x.toLowerCase().startsWith(y.toLowerCase()) || y.toLowerCase().startsWith(x.toLowerCase());
  }
  return key(a) === key(b);
}

export function checkFact(fact: Fact, date: string, t = tree): Verdict {
  const era = eraOf(date);
  const subject = resolveSubject(fact.subject);
  if (!subject) return { verdict: "unsure", confidence: 0.9, reason: `“${fact.subject}” is not in the lexicon (outside Hooly's world)`, segment: null, era };
  const allowed = lexicon.subjects.find((s) => s.name === subject)!.attributes;
  if (!allowed.includes(fact.attribute)) return { verdict: "unsure", confidence: 0.9, reason: `${subject} has no “${fact.attribute}” attribute`, segment: null, era };
  const node = t.get(subject)?.get(fact.attribute);
  const { op: _o, ...plain } = fact.value;
  const slot = slotOf(plain as Fact["value"]);
  const seg = node ? segmentAt(node, date, slot) : null;
  if (node && seg) {
    if (fact.value["op"] && typeof fact.value.value === "number" && typeof seg.raw.value === "number") {
      const ok = compareOp(String(fact.value["op"]), fact.value.value, seg.raw.value);
      return { verdict: ok ? "true" : "false", confidence: 0.85, reason: `${seg.value} holds since ${seg.from}; claim is ${fact.value["op"]} ${fact.value.value}`, segment: seg, era };
    }
    if (sameValue(fact.value, seg.raw)) return { verdict: "true", confidence: 0.95, reason: `matches value valid since ${seg.from}`, segment: seg, era };
  }
  // Look ahead inside the same event era: a change announced "today" is only confirmed by later rows.
  const next = node?.segments.find((s) => s.from > date && s.slot === slot);
  if (next && sameValue(fact.value, next.raw) && eraOf(next.from).after === era.after)
    return { verdict: "true", confidence: 0.7, reason: `becomes ${next.value} on ${next.from}, same event era — announced change`, segment: next, era };
  if (seg) return { verdict: "false", confidence: 0.85, reason: `on ${date} the value is ${seg.value} (since ${seg.from}), not ${key(fact.value)}`, segment: seg, era };
  const everTrue = node?.segments.some((s) => sameValue(fact.value, s.raw));
  if (node?.falseValues.some((o) => sameValue(fact.value, o.raw)) && !everTrue)
    return { verdict: "false", confidence: 0.75, reason: "known hype value, never true", segment: null, era };
  return { verdict: "unsure", confidence: 0.6, reason: node ? `no true value recorded before ${date}` : "no evidence for this subject+attribute", segment: null, era };
}

/** Sentence logic: all facts true → true; any false → false; otherwise unsure. Never true unless every fact is true. */
export function combine(verdicts: Label[]): Label {
  if (verdicts.includes("false")) return "false";
  if (verdicts.includes("unsure")) return "unsure";
  return "true";
}

export function checkRow(row: Row, t = tree) {
  const facts = row.form.map((f) => ({ fact: f, ...checkFact(f, row.date, t) }));
  const verdict = combine(facts.map((f) => f.verdict));
  const deciding = facts.filter((f) => f.verdict === verdict);
  return { facts, verdict, confidence: Math.min(...deciding.map((f) => f.confidence)) };
}

/** Honest score: rebuild the tree without the row being judged (leave-one-out). */
export function evaluate(sample: Row[] = rows) {
  let correct = 0;
  const confusion: Record<string, number> = {};
  for (const r of sample) {
    const v = checkRow(r, buildTree(rows, r.id)).verdict;
    if (v === r.label) correct++;
    confusion[`${r.label}→${v}`] = (confusion[`${r.label}→${v}`] ?? 0) + 1;
  }
  return { accuracy: correct / sample.length, confusion };
}
