import { createFileRoute } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/Shell";
import { MIN_CONF, toCsv } from "@/lib/claims";
import { buildStory, GATES, type Example } from "@/lib/story";

export const Route = createFileRoute("/how-it-works")({
  head: () => ({
    meta: [
      { title: "Hooly Lab — Step through the claim generator" },
      { name: "description", content: "A step-by-step debugger view of how the claim generator builds true claims and rejects the wrong ones." },
      { property: "og:title", content: "Hooly Lab — Step through the claim generator" },
      { property: "og:description", content: "A step-by-step debugger view of how the claim generator builds true claims and rejects the wrong ones." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: HowPage,
});

const CODE = [
  'rows = load_notes("practice.json")',
  'tree = build_tree([r for r in rows if r.label == "true"])',
  "for kind, node in walk(tree):",
  "    cand = make_claim(kind, node)",
  "    text = write_sentence(cand)",
  `    if cand.confidence < ${MIN_CONF}:`,
  '        reject(cand, "not enough proof"); continue',
  "    if text in practice_texts:",
  '        reject(cand, "not new"); continue',
  "    if text in seen:",
  '        reject(cand, "duplicate"); continue',
  "    problem = validate_text(text)",
  "    if problem:",
  "        reject(cand, problem); continue",
  "    accept(cand)",
  "return pick_round_robin(accepted, 1000)",
];
const GATE_LINE = [5, 7, 9, 11];

type Step = { line: number; vars: [string, string][]; say: string; claim?: boolean; status?: "ok" | "fail" | "pass" };
type Story = ReturnType<typeof buildStory>;

function traceFor(e: Example, s: Story): Step[] {
  const steps: Step[] = [
    { line: 0, vars: [["rows", `${s.counts.true + s.counts.false + s.counts.unsure} notes`]], say: `${s.counts.true} true · ${s.counts.false} false · ${s.counts.unsure} unsure` },
    { line: 1, vars: [["tree", "thing → property → values over time"]], say: "true notes → tree" },
    { line: 2, vars: [["kind", e.type]], say: e.type },
    { line: 3, vars: [["kind", e.type], ["cand.confidence", e.confidence.toFixed(2)]], say: `confidence ${e.confidence.toFixed(2)}` },
    { line: 4, vars: [["text", `"${e.text}"`]], say: "sentence written", claim: true },
  ];
  for (let g = 0; g < GATES.length; g++) {
    const fails = !e.ok && e.gate === g;
    steps.push({ line: GATE_LINE[g]!, vars: [["check", GATES[g]!], ["result", fails ? "False" : "True"]], say: `${GATES[g]} ${fails ? "no" : "yes"}`, claim: true, status: fails ? "fail" : "pass" });
    if (fails) {
      steps.push({ line: GATE_LINE[g]! + (g === 3 ? 2 : 1), vars: [["rejected", "True"], ["reason", e.why]], say: `rejected: ${e.why}`, claim: true, status: "fail" });
      return steps;
    }
  }
  steps.push({ line: 14, vars: [["accepted", "True"]], say: "kept", claim: true, status: "ok" });
  steps.push({ line: 15, vars: [["accepted", `${s.total} claims`]], say: `${s.total.toLocaleString()} kept / ${s.tried.toLocaleString()} tried`, claim: true, status: "ok" });
  return steps;
}

function HowPage() {
  const s = useMemo(() => buildStory(), []);
  const runs = useMemo(() => s.accepted.flatMap((a, i) => [a, s.rejected[i]]).filter((x): x is Example => !!x), [s]);
  const [run, setRun] = useState(0);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const ex = runs[run]!;
  const trace = useMemo(() => traceFor(ex, s), [ex, s]);
  const cur = trace[step]!;
  const last = step === trace.length - 1;

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      if (!last) setStep(step + 1);
      else if (run < runs.length - 1) { setRun(run + 1); setStep(0); }
      else setPlaying(false);
    }, 1900);
    return () => clearTimeout(t);
  }, [playing, step, last, run, runs.length]);

  const pick = (i: number) => { setRun(i); setStep(0); };
  const download = () => {
    const url = URL.createObjectURL(new Blob([toCsv(s.claims)], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: "claims.csv" }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <Shell title="Step through the claim generator" sub="Left: the code running line by line. Right: what it outputs.">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button className="dbg-btn" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Run"}</button>
        <button className="dbg-btn" disabled={step === 0} onClick={() => setStep(step - 1)}>Step back</button>
        <button className="dbg-btn" disabled={last} onClick={() => setStep(step + 1)}>Step over</button>
        <button className="dbg-btn" onClick={() => { setStep(0); setPlaying(false); }}>Restart</button>
        <span className="ml-auto font-mono text-xs text-muted-foreground">step {step + 1}/{trace.length}</span>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {runs.map((r, i) => (
          <button key={i} onClick={() => pick(i)} className={`dbg-tab ${i === run ? "dbg-tab-on" : ""}`}>
            <span className={r.ok ? "text-primary" : "text-destructive"}>{r.ok ? "keep" : "drop"}</span> {r.type}
          </button>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="dbg-pane">
          <div className="dbg-head">generate_claims.py</div>
          <pre className="dbg-code">
            {CODE.map((l, i) => (
              <div key={i} className={`dbg-line ${i === cur.line ? (cur.status === "fail" ? "dbg-line-fail" : "dbg-line-on") : ""}`}>
                <span className="dbg-gutter">{i === cur.line ? "▶" : ""}</span>
                <span className="dbg-num">{i + 1}</span>
                <span>{l}</span>
              </div>
            ))}
          </pre>
          <div className="dbg-head border-t border-border">Variables</div>
          <div className="space-y-1 p-3 font-mono text-xs">
            <AnimatePresence mode="popLayout">
              {cur.vars.map(([k, v]) => (
                <motion.div key={`${step}-${k}`} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="break-words">
                  <span className="text-primary">{k}</span> = <span className="text-foreground">{v}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </section>

        <section className="dbg-pane">
          <div className="dbg-head">Output</div>
          <div className="p-3">
            <AnimatePresence mode="wait">
              <motion.div key={`${run}-${step}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className={`font-mono text-sm ${cur.status === "fail" ? "text-destructive" : cur.status === "ok" ? "text-primary" : "text-foreground"}`}>
                {cur.say}
              </motion.div>
            </AnimatePresence>
          </div>
          <div className="border-t border-border p-3">
            <div className="mb-1 font-mono text-xs text-muted-foreground">Claim</div>
            <motion.div className={`dbg-claim ${cur.status === "fail" ? "dbg-claim-fail" : cur.status === "ok" ? "dbg-claim-ok" : ""}`}>
              {cur.claim ? ex.text : <span className="text-muted-foreground">not written yet…</span>}
            </motion.div>
            {cur.claim && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {GATES.map((g, i) => {
                  const done = trace.slice(0, step + 1).find((t) => t.line === GATE_LINE[i]);
                  const st = !done ? "" : done.status === "fail" ? "dbg-gate-fail" : "dbg-gate-pass";
                  return <span key={g} className={`dbg-gate ${st}`}>{g}</span>;
                })}
              </div>
            )}
            {last && cur.line === 15 && <button className="dbg-btn mt-3" onClick={download}>Download {s.total} claims</button>}
          </div>
        </section>
      </div>
    </Shell>
  );
}
