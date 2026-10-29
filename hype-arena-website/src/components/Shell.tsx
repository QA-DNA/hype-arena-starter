import { Link } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import type { Label } from "@/lib/hooly";

const nav = [
  { to: "/claims", label: "New claims" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/classifier", label: "Classifier" },
] as const;

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  // read the saved choice on every mount; only a click changes it
  useEffect(() => {
    // the live run page (another port) passes its theme as ?theme= on the link back
    const asked = new URLSearchParams(window.location.search).get("theme");
    if (asked === "dark" || asked === "light") {
      localStorage.setItem("theme", asked);
      window.history.replaceState(window.history.state, "", window.location.pathname); // so a reload keeps later toggles
    }
    const d = localStorage.getItem("theme") === "dark";
    document.documentElement.classList.toggle("dark", d);
    setDark(d);
  }, []);
  const toggle = () => {
    const d = !dark;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    localStorage.setItem("theme", d ? "dark" : "light");
  };
  return (
    <button onClick={toggle} className="nav-link" aria-label="Toggle dark theme">
      {dark ? "Light" : "Dark"}
    </button>
  );
}

export function Shell({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border">
        <div className="mx-auto flex h-12 max-w-6xl items-stretch border-x border-border">
          <span className="flex items-center px-5 text-lg font-light text-primary">hooly{"{"}lab{"}"}</span>
          <nav className="ml-auto flex">
            {nav.map((n) => (
              <Link key={n.to} to={n.to} className="nav-link" activeProps={{ className: "nav-link nav-active" }} activeOptions={{ exact: true }}>
                {n.label}
              </Link>
            ))}
            {/* the live run is served by frontend/server.py (the real Python system) */}
            <a
              href="http://localhost:8000/"
              className="nav-link"
              onClick={(e) => { e.currentTarget.href = `http://localhost:8000/?theme=${localStorage.getItem("theme") ?? "light"}`; }}
            >
              Live run
            </a>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="font-display text-5xl font-light tracking-tight text-primary">{title}</h1>
        <p className="mt-2 max-w-3xl text-muted-foreground">{sub}</p>
        <div className="mt-8">{children}</div>
      </main>
    </div>
  );
}

export function LabelPill({ label }: { label: Label }) {
  return <span className={`pill pill-${label}`}>{label}</span>;
}

export function Bars({ data, max }: { data: [string, number][]; max?: number }) {
  const top = max ?? Math.max(...data.map((d) => d[1]), 1);
  return (
    <div className="space-y-1.5">
      {data.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm">
          <span className="truncate font-mono text-xs" title={k}>{k}</span>
          <div className="h-2.5 rounded-sm bg-muted">
            <div className="h-full rounded-sm bg-primary" style={{ width: `${(v / top) * 100}%` }} />
          </div>
          <span className="text-right font-mono text-xs text-muted-foreground">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}
