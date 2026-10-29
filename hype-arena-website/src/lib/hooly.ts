import practiceRaw from "@/data/practice.json";
import lexiconRaw from "@/data/lexicon.json";

export type Label = "true" | "false" | "unsure";
export type Value = { kind: string; value: string | number | boolean; unit?: string; [k: string]: unknown };
export type Fact = { subject: string; attribute: string; value: Value };
export type Row = { id: string; text: string; date: string; label: Label; form: Fact[] };
export type Subject = { name: string; aliases: string[]; attributes: string[] };
export type Lexicon = { subjects: Subject[]; events: string[] };

export const rows = practiceRaw as Row[];
export const lexicon = lexiconRaw as unknown as Lexicon;

/** Map every name and alias (case-insensitive) to its canonical subject. */
export function buildAliasMap(lex: Lexicon): Map<string, string> {
  const m = new Map<string, string>();
  for (const s of lex.subjects) {
    m.set(s.name.toLowerCase(), s.name);
    for (const a of s.aliases) m.set(a.toLowerCase(), s.name);
  }
  return m;
}
export const aliasMap = buildAliasMap(lexicon);
export const resolveSubject = (name: string, map = aliasMap) => map.get(name.trim().toLowerCase()) ?? null;

export function formatValue(v: Value): string {
  const rest = Object.entries(v)
    .filter(([k]) => !["kind", "value", "unit"].includes(k))
    .map(([k, x]) => `${k}=${x}`);
  return [String(v.value), v.unit ?? "", rest.length ? `(${rest.join(", ")})` : ""].filter(Boolean).join(" ");
}

export type Token = { subject: string; canonical: string | null; attribute: string; attributeKnown: boolean; date: string; kind: string; value: string; label: Label };

/** Tokenise a row into (subject, attribute, date) -> value triples. */
export function tokenise(row: Row, lex: Lexicon = lexicon, map = aliasMap): Token[] {
  return row.form.map((f) => {
    const canonical = resolveSubject(f.subject, map);
    const subj = lex.subjects.find((s) => s.name === canonical);
    return {
      subject: f.subject,
      canonical,
      attribute: f.attribute,
      attributeKnown: !!subj?.attributes.includes(f.attribute),
      date: row.date,
      kind: f.value.kind,
      value: formatValue(f.value),
      label: row.label,
    };
  });
}

export type TimelinePoint = { date: string; value: string; label: Label; rowId: string; text: string };

/** All observations for one subject+attribute, sorted by date. */
export function buildTimeline(all: Row[], subject: string, attribute: string): TimelinePoint[] {
  const pts: TimelinePoint[] = [];
  for (const r of all)
    for (const f of r.form)
      if ((resolveSubject(f.subject) ?? f.subject) === subject && f.attribute === attribute)
        pts.push({ date: r.date, value: formatValue(f.value), label: r.label, rowId: r.id, text: r.text });
  return pts.sort((a, b) => a.date.localeCompare(b.date));
}

/** Distinct true values in order — the "change" steps. */
export function trueChanges(pts: TimelinePoint[]): TimelinePoint[] {
  const out: TimelinePoint[] = [];
  for (const p of pts) if (p.label === "true" && out.at(-1)?.value !== p.value) out.push(p);
  return out;
}
