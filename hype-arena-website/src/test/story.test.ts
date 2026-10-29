import { describe, expect, it } from "vitest";
import { buildStory, gateOf } from "@/lib/story";
import { generateClaims } from "@/lib/claims";

describe("story examples", () => {
  const s = buildStory();
  const r = generateClaims();
  it("one accepted example per claim type, all from the real output", () => {
    expect(s.accepted.map((a) => a.type)).toEqual(["fact", "compare", "change", "at_event", "relation"]);
    for (const a of s.accepted) expect(r.claims.some((c) => c.text === a.text)).toBe(true);
  });
  it("at least 3 distinct rejection reasons from the real rejected list", () => {
    expect(new Set(s.rejected.map((x) => x.why)).size).toBeGreaterThanOrEqual(3);
    for (const x of s.rejected) expect(r.rejected.some((y) => y.text === x.text)).toBe(true);
  });
  it("low confidence fails the first gate", () => expect(gateOf("confidence 0.6 below 0.7")).toBe(0));
});
