"use strict";

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 12;
const state = { rows: [], claims: [], csv: null, rowPage: 0, claimPage: 0, selected: null, timer: null, polling: false, jobId: null, logCount: 0, busy: false };
const tabs = [...document.querySelectorAll("[data-tab]")];

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}
function formatNumber(value) { return Number(value || 0).toLocaleString("en-US"); }
function percent(value) { return `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`; }
function known(row) { return typeof row.known_label === "string" && row.known_label.length > 0; }
function activateTab(name) {
  for (const tab of tabs) {
    const active = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    $(`panel-${tab.dataset.tab}`).hidden = !active;
  }
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); activateTab(tabs[next].dataset.tab); tabs[next].focus(); }
  });
});
$("show-architecture").addEventListener("click", () => { activateTab("architecture"); $("tab-architecture").focus(); });

async function request(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(20000), ...options });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { error: text.slice(0, 240) || `HTTP ${response.status}` }; }
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.message || `HTTP ${response.status}`);
  return data;
}
function actionError(message) {
  $("action-error").textContent = message || "";
  $("action-error").hidden = !message;
}
function setBusy(value) {
  state.busy = value;
  $("run").disabled = value;
  $("csv-file").disabled = value;
  $("generate-claims").disabled = value;
  $("use-demo").disabled = value;
  $("run-button-label").textContent = value ? "Pipeline running…" : "Run pipeline";
}
function badge(label) {
  const valid = ["true", "false", "unsure"].includes(label);
  return element("span", `verdict ${valid ? label : "pending"}`, valid ? label : "Pending");
}
function scoreNode(probabilities) {
  const wrap = element("div");
  if (!probabilities || !["true", "false", "unsure"].every((key) => Number.isFinite(probabilities[key]))) {
    wrap.append(element("span", "score-pending", "Run to score"));
    return wrap;
  }
  const bars = element("div", "score-bars");
  const values = element("div", "score-values");
  bars.setAttribute("aria-label", `Model scores: true ${percent(probabilities.true)}, false ${percent(probabilities.false)}, unsure ${percent(probabilities.unsure)}`);
  for (const key of ["true", "false", "unsure"]) {
    const bar = element("span", key);
    bar.style.width = percent(probabilities[key]);
    bars.append(bar);
    values.append(element("span", key, percent(probabilities[key])));
  }
  wrap.append(bars, values);
  return wrap;
}
function factValue(value) {
  if (!value || typeof value !== "object") return String(value ?? "—");
  const raw = typeof value.value === "boolean" ? (value.value ? "yes" : "no") : String(value.value ?? "—");
  const op = value.op ? `${value.op} ` : "";
  const unit = value.unit ? ` ${value.unit}` : "";
  const currency = value.currency ? ` ${value.currency}` : "";
  const period = value.period ? ` / ${value.period}` : "";
  return `${op}${raw}${unit}${currency}${period}${value.kind === "percent" ? "%" : ""}`;
}
function factCard(fact) {
  const card = element("div", "fact-card");
  for (const [key, value] of [["SUBJECT", fact.subject], ["ATTRIBUTE", fact.attribute], ["VALUE", factValue(fact.value)]]) {
    const line = element("div");
    const content = element("span", `fact-value${key === "SUBJECT" ? " strong" : ""}`, value);
    if (key === "VALUE" && fact.value?.kind) content.append(element("span", "value-type", fact.value.kind));
    line.append(element("span", "fact-key", key), content);
    card.append(line);
  }
  return card;
}
function evidenceNode(evidence) {
  const card = element("div", "evidence-card");
  const source = element("div", "evidence-source");
  source.append(element("strong", "", evidence.row_id || "Source"), element("span", "", `${evidence.date || "Undated"} · ${evidence.label || "observation"}`));
  card.append(source, element("p", "", evidence.text || ""));
  if (evidence.fact) card.append(element("p", "mono", `${evidence.fact.subject} / ${evidence.fact.attribute} → ${factValue(evidence.fact.value)}`));
  return card;
}
function inspectRow(row) {
  state.selected = row.id;
  $("inspect-id").textContent = row.id;
  const content = $("inspector-content");
  const title = element("h3", "", known(row) ? "A known observation." : "A decision you can inspect.");
  title.id = "inspector-title";
  const meta = element("div", "inspect-meta");
  meta.append(badge(row.label), element("span", "mono", `${row.date || "Undated"} · ${known(row) ? "known label" : "unlabelled input"}`));
  content.replaceChildren(title, element("p", "inspect-statement", row.text), meta);
  if (row.probabilities) content.append(scoreNode(row.probabilities));
  content.append(element("p", "inspect-label", "STRUCTURED FACTS"));
  const facts = row.facts || [];
  if (!facts.length) content.append(element("p", "muted", "No reliable subject–attribute–value extraction is available for this statement."));
  for (const fact of facts) content.append(factCard(fact));
  content.append(element("p", "inspect-label", "REASONING"), element("p", "inspect-reason", row.reason || "Source data preview. Run the pipeline to extract evidence and model scores."));
  content.append(element("p", "inspect-label", `SOURCE OBSERVATIONS · ${(row.evidence || []).length}`));
  if (!(row.evidence || []).length) content.append(element("p", "muted", "No supporting source attached. Missing evidence remains visible."));
  for (const evidence of row.evidence || []) content.append(evidenceNode(evidence));
  renderRows();
}
function filteredRows() {
  const query = $("row-search").value.trim().toLowerCase();
  const filter = $("verdict-filter").value;
  return state.rows.filter((row) => {
    if (filter === "known" && !known(row)) return false;
    if (filter === "unknown" && known(row)) return false;
    if (["true", "false", "unsure"].includes(filter) && row.label !== filter) return false;
    if (!query) return true;
    return `${row.id} ${row.text} ${(row.facts || []).map((fact) => `${fact.subject} ${fact.attribute} ${factValue(fact.value)}`).join(" ")}`.toLowerCase().includes(query);
  });
}
function renderRows() {
  const rows = filteredRows();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  state.rowPage = Math.max(0, Math.min(state.rowPage, pages - 1));
  const start = state.rowPage * PAGE_SIZE;
  const body = $("rows");
  body.replaceChildren();
  for (const row of rows.slice(start, start + PAGE_SIZE)) {
    const tr = element("tr", row.id === state.selected ? "selected" : "");
    tr.dataset.row = row.id;
    tr.tabIndex = 0;
    tr.setAttribute("aria-label", `Inspect ${row.id}: ${row.text}`);
    tr.addEventListener("click", () => inspectRow(row));
    tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspectRow(row); } });
    const textCell = element("td");
    const meta = element("div", "row-meta");
    meta.append(element("span", "", row.id), element("span", "", row.date), element("span", `row-source${known(row) ? "" : " predicted"}`, known(row) ? "KNOWN" : "UNLABELLED"));
    textCell.append(meta, element("div", "row-text", row.text));
    const verdict = element("td"); verdict.append(badge(row.label));
    const scores = element("td"); scores.append(scoreNode(row.probabilities));
    const arrow = element("td"); arrow.append(element("span", "inspect-arrow", "↗"));
    tr.append(textCell, verdict, scores, arrow);
    body.append(tr);
  }
  if (!rows.length) {
    const cell = element("td", "empty-cell", state.rows.length ? "No rows match these filters." : "Choose a CSV and press Run to inspect the result.");
    cell.colSpan = 4;
    const tr = element("tr"); tr.append(cell); body.append(tr);
  }
  $("row-page-info").textContent = rows.length ? `${formatNumber(start + 1)}–${formatNumber(Math.min(start + PAGE_SIZE, rows.length))} of ${formatNumber(rows.length)} rows` : "0 rows";
  $("row-page").textContent = `${state.rowPage + 1} / ${pages}`;
  $("row-prev").disabled = state.rowPage === 0;
  $("row-next").disabled = state.rowPage >= pages - 1;
}
function renderClaims() {
  const query = $("claim-search").value.trim().toLowerCase();
  const claims = state.claims.filter((claim) => !query || `${claim.id} ${claim.text} ${claim.type} ${JSON.stringify(claim.form)}`.toLowerCase().includes(query));
  const pages = Math.max(1, Math.ceil(claims.length / PAGE_SIZE));
  state.claimPage = Math.max(0, Math.min(state.claimPage, pages - 1));
  const start = state.claimPage * PAGE_SIZE;
  const list = $("claims");
  list.replaceChildren();
  for (const claim of claims.slice(start, start + PAGE_SIZE)) {
    const details = element("details", "claim-item");
    const summary = element("summary");
    const type = element("div");
    type.append(element("span", "claim-type", (claim.type || claim.kind || "claim").replaceAll("_", " ")), element("div", "row-meta", claim.id));
    const confidence = element("span", "claim-confidence", percent(claim.confidence));
    confidence.append(element("small", "", "confidence"));
    summary.append(type, element("span", "claim-text", claim.text), confidence, element("span", "claim-open", "+"));
    const detail = element("div", "claim-detail");
    const form = element("div"); form.append(element("p", "inspect-label", "STRUCTURED FORM"), element("pre", "", JSON.stringify(claim.form, null, 2)));
    const sources = element("div"); sources.append(element("p", "inspect-label", "SUPPORTING OBSERVATIONS"));
    for (const evidence of claim.evidence || []) sources.append(evidenceNode(evidence));
    if (!(claim.evidence || []).length) sources.append(element("p", "muted", "No source evidence attached."));
    detail.append(form, sources); details.append(summary, detail); list.append(details);
  }
  if (!claims.length) {
    const empty = element("div", "claims-empty");
    empty.append(element("span", "empty-orbit", "✳"), element("h3", "", state.claims.length ? "No matching claims." : "Evidence first. New claims next."), element("p", "", state.claims.length ? "Try another search." : "Enable claim generation and run the pipeline to fill this view."));
    list.append(empty);
  }
  $("claim-page-info").textContent = claims.length ? `${formatNumber(start + 1)}–${formatNumber(Math.min(start + PAGE_SIZE, claims.length))} of ${formatNumber(claims.length)} claims` : "0 claims";
  $("claim-page").textContent = `${state.claimPage + 1} / ${pages}`;
  $("claim-prev").disabled = state.claimPage === 0;
  $("claim-next").disabled = state.claimPage >= pages - 1;
}
function logTime(value) {
  if (typeof value === "number") return `${(value / (value > 1000000000 ? 1000 : 1)).toFixed(1)}s`;
  const text = String(value || "");
  const match = text.match(/(?:T|\s)(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : text.slice(0, 12);
}
function updateLogs(logs) {
  const list = $("logs");
  if (logs.length < state.logCount) { list.replaceChildren(); state.logCount = 0; }
  if (logs.length && !state.logCount) list.replaceChildren();
  for (const entry of logs.slice(state.logCount)) {
    const line = element("div", "log-entry");
    line.append(element("span", "log-time", logTime(entry.time)), element("span", "log-message", entry.message || String(entry)));
    list.append(line);
  }
  if (logs.length > state.logCount) list.scrollTop = list.scrollHeight;
  state.logCount = logs.length;
  $("log-count").textContent = `${logs.length} events`;
}
function updateMetrics(summary = {}) {
  const count = state.rows.length;
  const knownCount = state.rows.filter(known).length;
  $("metric-rows").textContent = formatNumber(summary.rows ?? count);
  $("metric-known").textContent = formatNumber(summary.known ?? knownCount);
  $("metric-unknown").textContent = formatNumber(summary.unknown ?? count - knownCount);
  if (Number.isFinite(summary.elapsed_ms)) {
    $("metric-time").replaceChildren(document.createTextNode((summary.elapsed_ms / 1000).toFixed(2)), element("small", "", "s"));
  }
  if (summary.model) $("metric-model").textContent = String(summary.model);
}
function updateJob(job) {
  if (!job || typeof job.status !== "string") return;
  if (job.id !== state.jobId) { state.jobId = job.id; state.logCount = 0; $("logs").replaceChildren(); }
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  $("run-progress").value = progress;
  $("progress-percent").textContent = `${Math.round(progress)}%`;
  $("run-state").className = `status-label ${job.status}`;
  $("run-state").textContent = ({ idle: "Ready when you are", running: "Pipeline running", complete: "Run complete", error: "Run needs attention" })[job.status] || job.status;
  $("run-stage").textContent = job.stage || "Progress reflects completed processing stages.";
  updateLogs(job.logs || []);
  setBusy(job.status === "running");
  if (job.error) actionError(job.error);
  if (Array.isArray(job.results) && job.results.length) {
    state.rows = job.results;
    renderRows();
    const selected = state.rows.find((row) => row.id === state.selected);
    if (selected) inspectRow(selected);
    $("metric-source").textContent = job.status === "complete" ? "Completed live run" : "Current live run";
  }
  updateMetrics(job.summary || {});
  if (job.generation) {
    state.claims = job.generation.claims || [];
    $("claim-tab-count").textContent = formatNumber(state.claims.length);
    $("claim-total").textContent = formatNumber(state.claims.length);
    $("candidate-count").textContent = `${formatNumber(job.generation.candidate_count)} candidates considered`;
    $("generation-notes").replaceChildren(...(job.generation.notes || []).map((note) => element("p", "", note)));
    renderClaims();
  }
  $("download-output").hidden = job.status !== "complete";
  if (job.status === "running") schedulePoll();
}
function schedulePoll(delay = 800) {
  clearTimeout(state.timer);
  state.timer = setTimeout(poll, delay);
}
async function poll() {
  if (state.polling) return;
  state.polling = true;
  try { updateJob(await request("/api/runs/current")); }
  catch (error) { actionError(`Could not read the run: ${error.message}. Retrying…`); schedulePoll(2500); }
  finally { state.polling = false; }
}
async function startRun() {
  if (state.busy) return;
  actionError("");
  setBusy(true);
  clearTimeout(state.timer);
  $("download-output").hidden = true;
  $("run-state").textContent = "Submitting input…";
  $("run-state").className = "status-label running";
  const body = { generate: $("generate-claims").checked };
  if (state.csv !== null) body.csv = state.csv;
  try {
    const job = await request("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    state.rowPage = 0; state.claimPage = 0;
    activateTab("workbench");
    updateJob(job);
    schedulePoll(100);
  } catch (error) { setBusy(false); actionError(error.message); $("run-state").textContent = "Input not accepted"; $("run-state").className = "status-label error"; }
}
$("run").addEventListener("click", startRun);
$("csv-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  actionError("");
  if (file.size > 16 * 1024 * 1024) { actionError("Choose a CSV smaller than 16 MiB."); event.target.value = ""; return; }
  try {
    state.csv = await file.text();
    $("file-name").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KiB`;
    $("source-badge").textContent = "YOUR CSV";
    $("source-description").textContent = "Your CSV is ready. Press Run to validate the input and classify its unlabelled rows.";
    $("use-demo").hidden = false;
  } catch (error) { actionError(`Could not open this file: ${error.message}`); }
});
$("use-demo").addEventListener("click", () => {
  state.csv = null; $("csv-file").value = "";
  $("file-name").textContent = "id · text · date · label";
  $("source-badge").textContent = "PRACTICE DEMO";
  $("source-description").textContent = "Practice data with every fifth label hidden. Or bring your own CSV.";
  $("use-demo").hidden = true; actionError("");
});
for (const id of ["row-search", "verdict-filter"]) $(id).addEventListener(id === "row-search" ? "input" : "change", () => { state.rowPage = 0; renderRows(); });
$("claim-search").addEventListener("input", () => { state.claimPage = 0; renderClaims(); });
$("row-prev").addEventListener("click", () => { state.rowPage--; renderRows(); });
$("row-next").addEventListener("click", () => { state.rowPage++; renderRows(); });
$("claim-prev").addEventListener("click", () => { state.claimPage--; renderClaims(); });
$("claim-next").addEventListener("click", () => { state.claimPage++; renderClaims(); });
async function initialize() {
  const outcomes = await Promise.allSettled([request("/api/health"), request("/api/dataset"), request("/api/runs/current")]);
  if (outcomes[0].status === "fulfilled") { $("connection").textContent = "API online"; $("connection").classList.add("online"); }
  else $("connection").textContent = "API unavailable";
  if (outcomes[1].status === "fulfilled") {
    const data = outcomes[1].value;
    state.rows = (data.rows || []).map((row) => ({ ...row, known_label: row.label || null, facts: row.form || [], probabilities: null, evidence: [], reason: "Practice source preview. Model scores and evidence appear after a live run." }));
    updateMetrics(data.summary || {}); renderRows();
    $("metric-source").textContent = "Practice source preview";
  } else { renderRows(); actionError(`Dataset unavailable: ${outcomes[1].reason.message}`); }
  if (outcomes[2].status === "fulfilled" && outcomes[2].value.status !== "idle") updateJob(outcomes[2].value);
  renderClaims();
}
initialize();
