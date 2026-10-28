"use strict";

let graph = null;
let selectedNode = null;
const tabs = [...document.querySelectorAll("[data-tab]")];

function activateTab(tab) {
  for (const candidate of tabs) {
    const active = candidate === tab;
    candidate.setAttribute("aria-selected", String(active));
    candidate.tabIndex = active ? 0 : -1;
    document.getElementById(`panel-${candidate.dataset.tab}`).hidden = !active;
  }
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      activateTab(tabs[next]);
      tabs[next].focus();
    }
  });
});

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  const button = document.getElementById("refresh");
  const connection = document.getElementById("connection");
  button.disabled = true;
  connection.textContent = "Connecting";
  connection.classList.remove("online");
  try {
    const [info, map] = await Promise.all([getJson("/api/workspace"), getJson("/api/graph")]);
    document.getElementById("version").textContent = `v${info.version}`;
    connection.textContent = "API online";
    connection.classList.add("online");
    graph = map;
    document.getElementById("graph-count").textContent = `${map.nodes.length} nodes / ${map.edges.length} relationships`;
    renderNodes();
    selectNode(selectedNode || map.nodes[0]?.id);
  } catch {
    connection.textContent = "API unavailable";
    document.getElementById("graph-count").textContent = "Map unavailable";
  } finally {
    button.disabled = false;
  }
}

function renderNodes() {
  const list = document.getElementById("nodes");
  const filter = document.getElementById("node-search").value.toLowerCase();
  list.replaceChildren();
  for (const node of graph?.nodes || []) {
    if (!`${node.id} ${node.kind} ${node.path}`.toLowerCase().includes(filter)) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node";
    button.textContent = node.id;
    button.setAttribute("aria-pressed", String(node.id === selectedNode));
    button.addEventListener("click", () => selectNode(node.id));
    list.append(button);
  }
  if (!list.children.length) {
    const message = document.createElement("p");
    message.className = "muted";
    message.textContent = "No matching nodes.";
    list.append(message);
  }
}

function selectNode(id) {
  const node = graph?.nodes.find((item) => item.id === id);
  if (!node) return;
  selectedNode = id;
  const detail = document.getElementById("node-detail");
  detail.replaceChildren();
  const label = document.createElement("p");
  label.className = "eyebrow";
  label.textContent = `${node.kind} / ${node.status}`;
  const title = document.createElement("h3");
  title.textContent = node.id;
  const link = document.createElement("a");
  link.textContent = node.path;
  link.href = `https://github.com/teodorbalan/VERIDYCT/blob/main/${node.path.split("/").map(encodeURIComponent).join("/")}`;
  link.target = "_blank";
  link.rel = "noreferrer";
  const heading = document.createElement("p");
  heading.textContent = "Declared relationships";
  const list = document.createElement("ul");
  const edges = graph.edges.filter((edge) => edge.from === id || edge.to === id);
  for (const edge of edges) {
    const item = document.createElement("li");
    item.textContent = `${edge.from} → ${edge.relation.replaceAll("_", " ")} → ${edge.to}`;
    list.append(item);
  }
  if (!edges.length) {
    const item = document.createElement("li");
    item.textContent = "No declared relationships yet.";
    list.append(item);
  }
  detail.append(label, title, link, heading, list);
  renderNodes();
}

document.getElementById("refresh").addEventListener("click", refresh);
document.getElementById("node-search").addEventListener("input", renderNodes);
document.querySelectorAll(".copy").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Select text";
    }
    setTimeout(() => { button.textContent = "Copy"; }, 1800);
  });
});
refresh();
