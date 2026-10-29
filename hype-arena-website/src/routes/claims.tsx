import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, Shell } from "@/components/Shell";
import { generateClaims, toCsv, toPracticePlusCsv, TYPES, type ClaimType } from "@/lib/claims";

export const Route = createFileRoute("/claims")({
  head: () => ({
    meta: [
      { title: "Hooly Lab — 1,000 new true claims" },
      { name: "description", content: "Generate 1,000 new, true claims about Hooly from the fact tree, checked against the challenge's claim rules." },
      { property: "og:title", content: "Hooly Lab — 1,000 new true claims" },
      { property: "og:description", content: "Generate 1,000 new, true claims about Hooly from the fact tree, checked against the challenge's claim rules." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: ClaimsPage,
});

function ClaimsPage() {
  const r = useMemo(() => generateClaims(), []);
  const [type, setType] = useState<ClaimType | "all">("all");
  const [q, setQ] = useState("");
  const [showRejected, setShowRejected] = useState(false);
  const list = r.claims.filter((c) => (type === "all" || c.type === type) && (!q || c.text.toLowerCase().includes(q.toLowerCase())));

  const download = (csv: string, name: string) => {
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  };

  return (
    <Shell title="New claims" sub="1,000 new claims built from the fact tree. Each one is written in the referee's allowed wording, uses only lexicon names, never copies a practice row, and is only kept when the evidence is strong.">
      <div className="grid gap-4 md:grid-cols-[1fr_auto]">
        <Panel title={`Output · ${r.claims.length} claims${r.shortfall ? ` · ${r.shortfall} short` : ""}`}>
          <div className="grid grid-cols-2 gap-3 font-mono text-xs sm:grid-cols-5">
            {TYPES.map((t) => (
              <button key={t} onClick={() => setType(type === t ? "all" : t)} className={`rounded border p-2 text-left ${type === t ? "border-primary" : "border-border"}`}>
                <div className="text-muted-foreground">{t}</div>
                <div className="text-lg font-bold text-primary">{r.claims.filter((c) => c.type === t).length}</div>
                <div className="text-muted-foreground">{r.valid[t]} valid / {r.produced[t]} tried</div>
              </button>
            ))}
          </div>
        </Panel>
        <div className="flex flex-col gap-2">
          <button className="field" onClick={() => download(toCsv(r.claims), "claims.csv")}>Download claims CSV</button>
          <button className="field" onClick={() => download(toPracticePlusCsv(r.claims), "practice.csv")}>Download practice + claims</button>
          <button className="field" onClick={() => setShowRejected((x) => !x)}>{showRejected ? "Show claims" : `Rejected (${r.rejected.length})`}</button>
        </div>
      </div>

      <input className="field mt-4 w-full" placeholder="Search claims…" value={q} onChange={(e) => setQ(e.target.value)} />

      <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="font-mono text-xs uppercase text-muted-foreground">
            <tr className="border-b border-border"><th className="p-2 text-left">{showRejected ? "type" : "id"}</th><th className="p-2 text-left">text</th><th className="p-2 text-left">{showRejected ? "why rejected" : "conf"}</th></tr>
          </thead>
          <tbody>
            {showRejected
              ? r.rejected.filter((x) => (type === "all" || x.type === type) && (!q || x.text.toLowerCase().includes(q.toLowerCase()))).slice(0, 400).map((x, i) => (
                  <tr key={i} className="border-b border-border align-top"><td className="p-2 font-mono text-xs">{x.type}</td><td className="p-2">{x.text}</td><td className="p-2 text-xs text-muted-foreground">{x.reason}</td></tr>
                ))
              : list.map((c) => (
                  <tr key={c.id} className="border-b border-border align-top">
                    <td className="p-2 font-mono text-xs text-muted-foreground">{c.id}<div className="text-primary">{c.type}</div></td>
                    <td className="p-2">{c.text}<details className="mt-1"><summary className="cursor-pointer font-mono text-xs text-muted-foreground">form</summary><pre className="mt-1 whitespace-pre-wrap font-mono text-xs">{JSON.stringify(c.form)}</pre></details></td>
                    <td className="p-2 font-mono text-xs">{c.confidence.toFixed(2)}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
