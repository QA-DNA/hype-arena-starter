import { describe, expect, it } from "vitest";
import { buildExample, findSubjects, textTokens, valueToken } from "@/lib/classifier";

describe("classifier building blocks", () => {
  it("subject finder prefers the longest alias", () => {
    expect(findSubjects("Since 1 April, Hooly AI Pro is €59 per month.")).toEqual(["Hooly AI Pro"]);
    expect(findSubjects("Hooly AI is growing.")).toEqual(["Hooly"]);
  });
  it("value extractor normalises dates, scales and negation", () => {
    const t = textTokens("Holdan started at Hooly on 12 January 2026.");
    expect(t.has("date:2026-01-12")).toBe(true);
    expect(t.has("bool:true")).toBe(true);
    expect(textTokens("January 2026").has("date:2026-01")).toBe(true);
    expect(textTokens("2 million users").has("num:2000000")).toBe(true);
    expect(textTokens("It is not available.").has("bool:false")).toBe(true);
  });
  it("value tokens match the script's normalisation", () => {
    expect(valueToken({ kind: "money", value: 59 })).toBe("num:59");
    expect(valueToken({ kind: "boolean", value: true })).toBe("bool:true");
    expect(valueToken({ kind: "date", value: "2026-04-01" })).toBe("date:2026-04-01");
  });
  it("the worked example's value is on the true timeline and matches the text", () => {
    const ex = buildExample();
    expect(ex.steps.map((s) => s.token)).toContain("num:59");
    expect(ex.steps.map((s) => s.token)).toContain("num:49");
    expect(ex.curMatch).toBe(true);
    expect(ex.lieMatch).toBe(false);
  });
});
