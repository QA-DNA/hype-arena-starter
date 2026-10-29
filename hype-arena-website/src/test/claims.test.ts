import { describe, expect, it } from "vitest";
import { generateClaims, isNew, writeValue } from "@/lib/claims";
import { lexicon, rows } from "@/lib/hooly";

const r = generateClaims();
const KEYS = { fact: ["attribute", "subject", "value"], compare: ["left", "op", "right"], change: ["attribute", "from", "subject", "to"], at_event: ["attribute", "event", "subject", "value"], relation: ["attribute", "link", "subject", "target", "value"] };

describe("claim generator", () => {
  it("outputs exactly 1,000 unique, true claims with confidence 0.5–1.0", () => {
    expect(r.claims).toHaveLength(1000);
    expect(new Set(r.claims.map((c) => c.id)).size).toBe(1000);
    for (const c of r.claims) {
      expect(c.label).toBe("true");
      expect(c.confidence).toBeGreaterThanOrEqual(0.5);
      expect(c.confidence).toBeLessThanOrEqual(1);
      expect(c.id).toMatch(/^[A-Za-z0-9_.-]{1,64}$/);
      expect(c.text.length).toBeLessThanOrEqual(300);
    }
  });
  it("forms have exactly the schema keys and lexicon attributes, with no op", () => {
    for (const c of r.claims) {
      expect(Object.keys(c.form).sort()).toEqual(KEYS[c.type]);
      expect(JSON.stringify(c.form)).not.toContain('"op":"le"');
      const f = c.form as { subject?: string; attribute?: string };
      if (f.subject && c.type !== "relation") expect(lexicon.subjects.find((s) => s.name === f.subject)?.attributes).toContain(f.attribute);
    }
  });
  it("compare texts hold no digits outside subject names", () => {
    for (const c of r.claims.filter((c) => c.type === "compare")) {
      const { left, right } = c.form as { left: { subject: string }; right: { subject: string } };
      expect(c.text.replace(left.subject, "").replace(right.subject, "")).not.toMatch(/\d/);
    }
  });
  it("no claim copies a practice row", () => {
    const texts = new Set(rows.map((x) => x.text));
    for (const c of r.claims) expect(texts.has(c.text)).toBe(false);
    expect(isNew(rows[0]!.text)).toBe(false);
  });
  it("writes values as the referee reads them", () => {
    expect(writeValue({ kind: "money", value: 59, currency: "EUR", per: "month" })).toBe("€59 per month");
    expect(writeValue({ kind: "date", value: "2026-07-01" })).toBe("1 July 2026");
    expect(writeValue({ kind: "quantity", value: 2048, unit: "customer" })).toBe("2,048 customers");
  });
  it("Hooly AI Pro is €59 per month and changed from €49 per month", () => {
    const texts = r.claims.map((c) => c.text);
    expect(texts).toContain("For Hooly AI Pro, the price is €59 per month.");
    expect(texts).toContain("For Hooly AI Pro, the price went from €49 per month to €59 per month.");
  });
});
