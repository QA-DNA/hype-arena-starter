import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { LabelPill, Shell } from "@/components/Shell";
import { buildExample, PIPELINE, type Block } from "@/lib/classifier";

export const Route = createFileRoute("/classifier")({
  head: () => ({
    meta: [
      { title: "Hooly Lab — How the classifier decides true, false or unsure" },
      { name: "description", content: "The row classifier explained as six animated building blocks: subject finder, fact router, value extractor, knowledge base, evidence features and the judge." },
      { property: "og:title", content: "Hooly Lab — How the classifier decides true, false or unsure" },
      { property: "og:description", content: "The row classifier explained as six animated building blocks: subject finder, fact router, value extractor, knowledge base, evidence features and the judge." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: ClassifierPage,
});

type Example = ReturnType<typeof buildExample>;

function Chip({ children, on }: { children: ReactNode; on?: boolean | undefined }) {
  return <span className={`inline-block border px-1.5 py-0.5 font-mono text-xs ${on === undefined ? "border-border text-foreground" : on ? "border-primary text-primary" : "border-destructive text-destructive"}`}>{children}</span>;
}

/** The one thing each block hands to the next — nothing else is shown. */
function Result({ block, ex }: { block: Block; ex: Example }) {
  switch (block.live) {
    case "subjects":
      return <div className="flex flex-wrap gap-1.5">{ex.subjects.map((s) => <Chip key={s} on>{s}</Chip>)}</div>;
    case "tokens":
      return <div className="flex flex-wrap gap-1.5">{ex.tokens.map((t) => <Chip key={t}>{t}</Chip>)}</div>;
    case "kb":
      return (
        <div className="space-y-1">
          {ex.steps.map((s) => (
            <div key={s.date + s.token} className="flex items-center gap-2 font-mono text-xs">
              <span className="text-muted-foreground">{s.date}</span>
              <span>→</span>
              <Chip on={s.token === ex.want ? true : undefined}>{s.token}</Chip>
            </div>
          ))}
        </div>
      );
    case "features":
      return (
        <div className="flex flex-wrap gap-1.5">
          <Chip on={ex.curMatch}>cur_match = {ex.curMatch ? 1 : 0}</Chip>
          <Chip on={!ex.lieMatch}>lie_match = {ex.lieMatch ? 1 : 0}</Chip>
          <Chip on={!ex.negated}>neg = {ex.negated ? 1 : 0}</Chip>
          <Chip>… +27 more</Chip>
        </div>
      );
    default:
      return null;
  }
}

function ClassifierPage() {
  const ex = useMemo(() => buildExample(), []);
  // step -1 = only the sentence shown; 0..5 = blocks done up to that index; 6 = verdict
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (!playing || step >= PIPELINE.length) return;
    const t = setTimeout(() => setStep((s) => s + 1), step === -1 ? 900 : 1800);
    return () => clearTimeout(t);
  }, [playing, step]);

  const done = step >= PIPELINE.length;

  return (
    <Shell
      title="How the classifier decides"
      sub="One sentence walks through six blocks. Each new block lands on top and pushes the older ones down, so read from the bottom up."
    >
      {/* controls */}
      <div className="mb-6 flex items-center gap-3 font-mono text-xs">
        <button
          onClick={() => { setStep(-1); setPlaying(true); }}
          className="border border-border px-3 py-1.5 text-foreground hover:border-primary hover:text-primary"
        >
          restart
        </button>
        <button
          onClick={() => {
            // play on a finished run starts it over instead of sitting on the verdict
            if (done) { setStep(-1); setPlaying(true); } else setPlaying((p) => !p);
          }}
          className="border border-border px-3 py-1.5 text-foreground hover:border-primary hover:text-primary"
        >
          {playing && !done ? "pause" : "play"}
        </button>
        <button
          onClick={() => { setPlaying(false); setStep((s) => Math.min(s + 1, PIPELINE.length)); }}
          className="border border-border px-3 py-1.5 text-foreground hover:border-primary hover:text-primary"
        >
          next block →
        </button>
      </div>

      {/* newest block on top: older ones slide down, the sentence being judged sits at the bottom as the origin */}
      <div className="space-y-2">
        <AnimatePresence>
          {done && (
            <motion.div
              key="verdict"
              initial={{ opacity: 0, height: 0, y: -24 }}
              animate={{ opacity: 1, height: "auto", y: 0 }}
              transition={{ duration: 0.45, ease: "easeOut" }}
              style={{ overflow: "hidden" }}
            >
              <section className="border border-primary bg-card p-5">
                <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">verdict</p>
                <p className="mt-2 flex items-center gap-2 text-sm">
                  <LabelPill label={ex.row.label} />
                  <span className="text-muted-foreground">the text holds exactly the value that was valid on {ex.row.date}.</span>
                </p>
              </section>
              <div className="flex justify-center py-1 font-mono text-lg text-muted-foreground">↑</div>
            </motion.div>
          )}
          {PIPELINE.slice(0, step + 1)
            .map((b, i) => ({ b, i }))
            .reverse()
            .map(({ b, i }) => (
              <motion.div
                key={b.id}
                initial={{ opacity: 0, height: 0, y: -24 }}
                animate={{ opacity: 1, height: "auto", y: 0 }}
                transition={{ duration: 0.45, ease: "easeOut" }}
                style={{ overflow: "hidden" }}
              >
                <section className={`border bg-card p-5 ${i === step && !done ? "border-primary" : "border-border"}`}>
                  <div className="flex flex-wrap items-baseline gap-x-4">
                    <h2 className="font-display text-xl font-light text-primary">{b.name}</h2>
                    <p className="text-sm text-muted-foreground">{b.short}</p>
                  </div>
                  {b.live ? (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.5, duration: 0.4 }}
                      className="mt-3 border border-border p-3"
                    >
                      <Result block={b} ex={ex} />
                    </motion.div>
                  ) : (
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.5, duration: 0.4 }}
                      className="mt-3 border border-border p-3 font-mono text-xs text-muted-foreground"
                    >
                      {b.id === "router" ? `learned from the practice rows → ${ex.subjects[0] ?? "?"}‖price` : "learned from the practice rows → true · false · unsure"}
                    </motion.p>
                  )}
                </section>
                <div className="flex justify-center py-1 font-mono text-lg text-muted-foreground">↑</div>
              </motion.div>
            ))}
        </AnimatePresence>

        {/* the sentence being judged: the origin, always at the bottom */}
        <section className="border border-primary bg-card p-5">
          <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">the sentence</p>
          <p className="mt-2 font-mono text-sm text-foreground">“{ex.row.text}”</p>
          <p className="mt-2 font-mono text-xs text-muted-foreground">judged on {ex.row.date}</p>
        </section>
      </div>
    </Shell>
  );
}
