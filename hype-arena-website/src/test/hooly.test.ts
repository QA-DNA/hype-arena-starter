import { describe, expect, it } from "vitest";
import { buildTimeline, resolveSubject, rows, tokenise, trueChanges } from "@/lib/hooly";

describe("hooly tokeniser", () => {
  it("resolves aliases to canonical subjects", () => {
    expect(resolveSubject("Hooly AI")).toBe("Hooly");
    expect(resolveSubject("brightline")).toBe("Brightline Labs");
    expect(resolveSubject("Nobody")).toBeNull();
  });
  it("tokenises p-1 into a joined date fact", () => {
    const t = tokenise(rows.find((r) => r.id === "p-1")!)[0];
    expect(t).toMatchObject({ canonical: "Holdan", attribute: "joined", date: "2026-01-12", kind: "date", value: "2026-01-12" });
  });
  it("timelines are date-sorted and changes skip repeats", () => {
    const pts = buildTimeline(rows, "Holdan", "team_size");
    expect(pts.map((p) => p.date)).toEqual([...pts.map((p) => p.date)].sort());
    const steps = trueChanges(pts);
    steps.forEach((s, i) => i && expect(s.value).not.toBe(steps[i - 1]!.value));
  });
});
