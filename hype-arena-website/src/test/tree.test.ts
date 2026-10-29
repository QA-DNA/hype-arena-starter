import { describe, expect, it } from "vitest";
import { combine, eraOf, sameValue } from "@/lib/tree";

describe("fact tree checker", () => {
  it("a sentence is true only if every fact is true", () => {
    expect(combine(["true", "true"])).toBe("true");
    expect(combine(["true", "false", "unsure"])).toBe("false");
    expect(combine(["true", "unsure"])).not.toBe("true");
  });
  it("anchors dates between events", () => {
    expect(eraOf("2026-03-30")).toEqual({ after: "Hooly I/O 2026", before: "Hooly Maps Day" });
  });
  it("matches dates by precision", () => {
    expect(sameValue({ kind: "date", value: "2025-11" }, { kind: "date", value: "2025-11-04" })).toBe(true);
    expect(sameValue({ kind: "date", value: "2025-12" }, { kind: "date", value: "2025-11-04" })).toBe(false);
  });
});
