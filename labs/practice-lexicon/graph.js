// The explorer owns its camera and modal; the data model remains unchanged.
const explorer = { width: 900, height: 500, fit: true, frame: 0, history: [], selection: null, row: null, limit: 30, details: true, native: false, opener: null, scroll: 0, pointers: new Map(), gesture: null, layoutCache: new Map() };

function layoutNodes(names, edges, global) {
  const narrow = $('#graph-stage').clientWidth < 520;
  const key = JSON.stringify([global, narrow, global ? '' : state.focus, names, edges.map(e => [e.source, e.target])]);
  if (explorer.layoutCache.has(key)) return explorer.layoutCache.get(key);
  const positions = new Map();
  if (!global) {
    positions.set(state.focus, { x: 500, y: 370 });
    const other = names.filter(name => name !== state.focus);
    other.forEach((name, i) => {
      const angle = i / Math.max(1, other.length) * Math.PI * 2 - Math.PI / 2;
      positions.set(name, { x: 500 + Math.cos(angle) * (other.length > 8 ? 440 : narrow ? 120 : 325), y: 370 + Math.sin(angle) * (other.length > 8 ? 300 : narrow ? 260 : 220) });
    });
  } else {
    // Keep connected components together, then lay out unconnected subjects in a grid.
    const adjacent = new Map(names.map(name => [name, new Set()]));
    edges.forEach(e => { adjacent.get(e.source)?.add(e.target); adjacent.get(e.target)?.add(e.source); });
    const seen = new Set(), ordered = [];
    for (const name of [...names].sort((a, b) => adjacent.get(b).size - adjacent.get(a).size || a.localeCompare(b))) {
      const queue = [name];
      for (let i = 0; i < queue.length; i++) {
        const next = queue[i]; if (seen.has(next)) continue;
        seen.add(next); ordered.push(next); queue.push(...adjacent.get(next));
      }
    }
    ordered.forEach((name, i) => positions.set(name, { x: 150 + (i % 8) * 235, y: 100 + Math.floor(i / 8) * 155 }));
  }
  if (explorer.layoutCache.size > 16) explorer.layoutCache.delete(explorer.layoutCache.keys().next().value);
  explorer.layoutCache.set(key, positions);
  return positions;
}

function graphLabel(name) {
  const words = name.replaceAll('_', ' ').split(' '), lines = [''];
  for (const word of words) {
    if (lines.at(-1).length + word.length > 23 && lines.at(-1)) lines.push(word);
    else lines[lines.length - 1] += (lines.at(-1) ? ' ' : '') + word;
  }
  return lines;
}

function renderGraph() {
  explorer.narrow = $('#graph-stage').clientWidth < 520;
  const attributeMode = state.graphMode === 'attributes';
  $('#relations-mode').classList.toggle('active', !attributeMode); $('#attributes-mode').classList.toggle('active', attributeMode);
  $('#relations-mode').setAttribute('aria-pressed', String(!attributeMode)); $('#attributes-mode').setAttribute('aria-pressed', String(attributeMode));
  $('#graph-all').disabled = attributeMode; $('#graph-focus').value = state.focus;
  $('#graph-back').disabled = !explorer.history.length;
  const subject = model.subjects.get(state.focus);
  let nodes, positions, lines = '', caption;
  if (attributeMode) {
    const attributes = subject.attributes.map(attribute => ({ attribute, count: filtered.filter(row => row.facts.some(f => f.subject === state.focus && f.attribute === attribute)).length })).sort((a, b) => b.count - a.count || a.attribute.localeCompare(b.attribute));
    const visible = attributes.slice(0, 16);
    positions = layoutNodes([state.focus, ...visible.map(a => a.attribute)], [], false);
    lines = visible.map(a => { const p = positions.get(a.attribute); return `<line x1="500" y1="370" x2="${p.x}" y2="${p.y}" stroke="#bdcdd6" stroke-width="1.5" stroke-dasharray="4 6"/>`; }).join('');
    caption = `${visible.length} / ${attributes.length} atribute · lista completă în Detalii · legături de schemă`;
    nodes = [{ name: state.focus }, ...visible.map(a => ({ name: a.attribute, attribute: true, count: a.count }))]; activeEdges = [];
  } else {
    const edges = relationEdges(filtered);
    activeEdges = state.all ? edges : edges.filter(edge => edge.source === state.focus || edge.target === state.focus);
    const names = state.all ? [...model.subjects.keys()] : [...new Set([state.focus, ...activeEdges.flatMap(edge => [edge.source, edge.target])])];
    nodes = names.map(name => ({ name })); positions = layoutNodes(names, activeEdges, state.all);
    const pairCount = new Map(), labeled = new Set();
    lines = activeEdges.map((edge, index) => {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      const group = [edge.source, edge.target].sort().join('|'), order = pairCount.get(group) || 0; pairCount.set(group, order + 1);
      const labelKey = JSON.stringify([edge.source, edge.target, edge.attribute]);
      const showLabel = !labeled.has(labelKey); labeled.add(labelKey);
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
      const offset = order % 2 ? -Math.ceil(order / 2) * 90 : Math.ceil(order / 2) * 90;
      const mid = { x: (a.x + b.x) / 2 - dy / distance * offset, y: (a.y + b.y) / 2 + dx / distance * offset };
      const end = { x: b.x - dx / distance * 30, y: b.y - dy / distance * 30 };
      const path = edge.source === edge.target ? `M ${a.x} ${a.y - 20} C ${a.x + 100} ${a.y - 100}, ${a.x + 110} ${a.y + 65}, ${a.x + 20} ${a.y}` : `M ${a.x} ${a.y} Q ${mid.x} ${mid.y} ${end.x} ${end.y}`;
      return `<g class="graph-edge" data-source="${esc(edge.source)}" data-target="${esc(edge.target)}"><path class="graph-link" d="${path}" fill="none" stroke="transparent" stroke-width="18" tabindex="0" role="button" data-edge="${index}" aria-label="${esc(edge.source + ' → ' + edge.attribute + ' → ' + edge.target + ', ' + edge.label + ', ' + edge.rowIds.length + ' query-uri')}"><title>${esc(edge.attribute)} · ${edge.label} · ${edge.rowIds.length} query-uri. Click pentru surse.</title></path><path class="edge-ink" d="${path}" fill="none" stroke="${palette[edge.label]}" stroke-width="2" ${edge.label !== 'true' ? 'stroke-dasharray="6 5"' : ''} marker-end="url(#arrow-${edge.label})"/>${showLabel && !state.all && activeEdges.length <= 12 ? `<text class="edge-label" x="${mid.x}" y="${mid.y - 10}" text-anchor="middle">${esc(edge.attribute.replaceAll('_', ' '))}</text>` : ''}</g>`;
    }).join('');
    caption = `${nodes.length} subiecte · ${activeEdges.length} relații · ${filtered.length} query-uri în filtrele curente`;
    if (!activeEdges.length) caption += ' · vezi și Atribute';
  }
  $('#graph').innerHTML = `<defs>${LABELS.map(label => `<marker id="arrow-${label}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${palette[label]}"/></marker>`).join('')}</defs><g id="graph-camera">${lines}${nodes.map(node => {
    const p = positions.get(node.name), focused = node.name === state.focus, event = model.lexicon.events.includes(node.name);
    const color = focused ? '#187f79' : node.attribute ? '#90aaba' : event ? '#b39350' : '#527692';
    const radius = focused ? 30 : 22, label = graphLabel(node.name), labelWidth = Math.max(...label.map(l => l.length)) * 7.8 + 22;
    return `<g class="graph-node ${focused ? 'is-selected' : ''}" transform="translate(${p.x} ${p.y})" tabindex="0" role="button" ${node.attribute ? `data-pair="${esc(pairKey(state.focus, node.name))}"` : `data-node="${esc(node.name)}"`} aria-label="${esc(node.name)}${node.attribute ? ', ' + node.count + ' query-uri' : ', selectează subiectul'}"><title>${esc(node.name)}${node.attribute ? ' · ' + node.count + ' query-uri' : ''}</title>${focused ? `<circle class="node-halo" r="43" fill="#deefea"/>` : ''}<circle r="${radius}" fill="${color}"/><text class="node-initial" y="5" text-anchor="middle">${node.attribute ? '·' : esc(node.name.replace(/^Hooly /, '').slice(0, 2).toUpperCase())}</text><rect class="node-label-bg" x="${-labelWidth / 2}" y="${radius + 9}" width="${labelWidth}" height="${label.length * 19 + 8}" rx="7"/><text class="node-name" text-anchor="middle">${label.map((line, i) => `<tspan x="0" y="${radius + 27 + i * 19}">${esc(line)}</tspan>`).join('')}</text>${node.attribute ? `<text class="node-sub" y="${radius + 42 + label.length * 19}" text-anchor="middle">${node.count} query-uri</text>` : ''}</g>`;
  }).join('')}</g>`;
  $('#graph-caption').textContent = caption;
  $('#graph-status').textContent = state.all && !attributeMode ? 'Tot lexiconul · caută un nume pentru a te apropia' : `${state.focus} · ${attributeMode ? 'atribute' : 'vecinătate'}`;
  if (explorer.fit) resetCamera(); else updateCamera();
  syncGraphDetails();
}

function updateCamera() {
  if (explorer.frame) return;
  explorer.frame = requestAnimationFrame(() => {
    explorer.frame = 0;
    $('#graph-camera')?.setAttribute('transform', `translate(${state.panX} ${state.panY}) scale(${state.zoom})`);
    $('#graph-zoom').textContent = Math.round(state.zoom * 100) + '%';
    $('#graph').dataset.zoom = String(state.zoom);
    $('#zoom-in').disabled = state.zoom >= 5; $('#zoom-out').disabled = state.zoom <= .12;
  });
}

function resetCamera() {
  const svg = $('#graph'), rect = svg.getBoundingClientRect(), camera = $('#graph-camera');
  explorer.fit = true;
  if (!camera || rect.width < 1 || rect.height < 1) return;
  explorer.width = rect.width; explorer.height = rect.height; svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
  const bounds = camera.getBBox(), padding = rect.width < 500 ? 30 : 80;
  state.zoom = Math.max(.12, Math.min(1.8, (rect.width - padding) / Math.max(1, bounds.width), (rect.height - 95) / Math.max(1, bounds.height)));
  state.panX = (rect.width - bounds.width * state.zoom) / 2 - bounds.x * state.zoom;
  state.panY = (rect.height - bounds.height * state.zoom) / 2 - bounds.y * state.zoom - 8;
  updateCamera();
}

function graphPoint(clientX, clientY) {
  const matrix = $('#graph').getScreenCTM();
  return new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
}

function zoomGraph(factor, point = { x: explorer.width / 2, y: explorer.height / 2 }) {
  const next = Math.max(.12, Math.min(5, state.zoom * factor)), ratio = next / state.zoom;
  state.panX = point.x - (point.x - state.panX) * ratio;
  state.panY = point.y - (point.y - state.panY) * ratio;
  state.zoom = next; explorer.fit = false; updateCamera();
}

function selectGraphNode(name, remember = true, jump = false) {
  if (!model.subjects.has(name)) return;
  if (name !== state.focus && remember) explorer.history.push(state.focus);
  state.focus = name; explorer.selection = null; explorer.row = null;
  if (!state.all || state.graphMode === 'attributes') explorer.fit = true;
  renderEntity(); renderGraph();
  if (jump && state.all && state.graphMode === 'relations') {
    const node = [...$('#graph').querySelectorAll('[data-node]')].find(n => n.dataset.node === name);
    const position = node.transform.baseVal.getItem(0).matrix;
    state.zoom = 1.4; state.panX = explorer.width / 2 - position.e * state.zoom; state.panY = explorer.height / 2 - position.f * state.zoom;
    explorer.fit = false; updateCamera(); highlightGraph(name);
  }
}

function syncGraphDetails() {
  const expanded = $('#graph-dialog').open;
  $('#graph-workspace').classList.toggle('details-hidden', expanded && !explorer.details);
  $('#graph-details-toggle').setAttribute('aria-pressed', String(explorer.details));
  $('#entity-panel').hidden = expanded && !!explorer.selection;
  $('#graph-evidence').hidden = !expanded || !explorer.selection;
}

function showGraphEvidence(selection) {
  explorer.selection = selection; explorer.row = null; explorer.limit = 30; explorer.details = true;
  renderGraphEvidence(); syncGraphDetails();
}

function renderGraphEvidence() {
  const selection = explorer.selection;
  if (!selection) return;
  const row = explorer.row && model.byId.get(explorer.row);
  $('#graph-evidence').innerHTML = `<button class="text-button" id="graph-evidence-back">← ${row ? 'Înapoi la surse' : 'Înapoi la subiect'}</button><div class="eyebrow" style="margin-top:24px">${row ? 'QUERY INSPECTOR' : 'SURSELE CONEXIUNII'}</div><h2>${esc(row ? row.id : selection.title)}</h2>${row ? `${badge(row.label)}<div class="query-date">${dateLabel(row.date)} · data paginii</div><p class="query-text">${esc(row.text)}</p>${row.facts.map(f => `<div class="fact-card"><div class="fact-subject">${esc(f.subject)}</div><div class="fact-attribute">${esc(f.attribute)}</div><div class="fact-value">${esc(formatValue(f.value))}</div></div>`).join('')}<p class="note">Eticheta aparține întregului rând.</p><details><summary>Form original</summary><pre>${esc(JSON.stringify(row.form, null, 2))}</pre></details>` : `<p class="note">${selection.rows.length} query-uri în filtrele curente, în ordine cronologică. Etichetele sunt cele publicate.</p>${selection.rows.slice(0, explorer.limit).map(r => `<button class="related-button" data-graph-row="${esc(r.id)}"><span class="related-meta">${esc(r.id)} · ${r.date}${badge(r.label)}</span>${esc(r.text)}</button>`).join('') || '<p class="note">Nicio sursă în filtrele curente.</p>'}${selection.rows.length > explorer.limit ? '<button class="text-button" id="graph-more-evidence">Mai multe surse ↓</button>' : ''}`}<button id="graph-open-timeline" class="button entity-action">Deschide în cronologie ↗</button>`;
}

function openGraph() {
  const dialog = $('#graph-dialog'); if (dialog.open) return;
  explorer.opener = document.activeElement; explorer.scroll = window.scrollY; explorer.native = false;
  explorer.details = innerWidth > 720;
  dialog.append($('#graph-workspace')); $('#graph-expand').hidden = true; $('#graph-close').hidden = false;
  document.body.classList.add('graph-is-open'); dialog.showModal(); syncGraphDetails();
  resetCamera(); $('#graph-close').focus({ preventScroll: true });
  if (!document.fullscreenElement && document.documentElement.requestFullscreen && navigator.userActivation?.isActive) {
    document.documentElement.requestFullscreen().then(() => {
      if (!dialog.open) { if (document.fullscreenElement === document.documentElement) document.exitFullscreen().catch(() => {}); }
      else { explorer.native = true; resetCamera(); }
    }).catch(() => {}); // The viewport dialog also works when browser fullscreen is unavailable.
  }
}

function closeGraph() {
  const dialog = $('#graph-dialog'); if (!dialog.open) return;
  if (explorer.native && document.fullscreenElement === document.documentElement) document.exitFullscreen().catch(() => {});
  explorer.native = false;
  dialog.close(); $('#graph-view').prepend($('#graph-workspace'));
  $('#graph-expand').hidden = false; $('#graph-close').hidden = true;
  document.body.classList.remove('graph-is-open'); explorer.selection = null; explorer.row = null; syncGraphDetails();
  resetCamera(); window.scrollTo(0, explorer.scroll); explorer.opener?.focus({ preventScroll: true });
}

function highlightGraph(name) {
  const neighbors = new Set([name]); activeEdges.forEach(edge => { if (edge.source === name) neighbors.add(edge.target); if (edge.target === name) neighbors.add(edge.source); });
  $('#graph').querySelectorAll('.graph-node').forEach(node => node.classList.toggle('is-muted', !!name && !!node.dataset.node && !neighbors.has(node.dataset.node)));
  $('#graph').querySelectorAll('.graph-edge').forEach(edge => edge.classList.toggle('is-muted', !!name && edge.dataset.source !== name && edge.dataset.target !== name));
}

function initGraph() {
  const svg = $('#graph');
  const names = [...model.subjects.values()];
  $('#graph-names').innerHTML = names.map(s => `<option value="${esc(s.name)}">${esc(s.aliases.join(', '))}</option>`).join('');
  const find = () => {
    const query = $('#graph-search').value.trim(), canonical = model.resolve(query);
    const matches = names.filter(s => [s.name, ...s.aliases].some(name => name.toLowerCase().includes(query.toLowerCase())));
    if (canonical || query && matches.length === 1) { selectGraphNode(canonical || matches[0].name, true, true); $('#graph-search').value = ''; }
    else $('#graph-status').textContent = query ? `${matches.length} subiecte găsite · alege numele complet` : 'Caută un nume sau un alias din lexicon';
  };
  $('#graph-search').addEventListener('change', find);
  $('#graph-search').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); find(); } });
  $('#graph-dialog').addEventListener('cancel', event => { event.preventDefault(); closeGraph(); });
  document.addEventListener('fullscreenchange', () => {
    // Embedded hosts may leave native fullscreen when changing their browser layout.
    // Keep the viewport explorer and its selection open in that case.
    if (explorer.native && document.fullscreenElement !== document.documentElement) {
      explorer.native = false; if ($('#graph-dialog').open) resetCamera();
    }
  });
  new ResizeObserver(() => {
    const rect = svg.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    if ((rect.width < 520) !== explorer.narrow) { explorer.fit = true; renderGraph(); return; }
    if (explorer.fit) resetCamera();
    else {
      state.panX += (rect.width - explorer.width) / 2; state.panY += (rect.height - explorer.height) / 2;
      explorer.width = rect.width; explorer.height = rect.height; svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`); updateCamera();
    }
  }).observe($('#graph-stage'));
  svg.addEventListener('wheel', event => {
    event.preventDefault(); const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? explorer.height : 1);
    zoomGraph(Math.exp(-Math.max(-120, Math.min(120, delta)) * .0025), graphPoint(event.clientX, event.clientY));
  }, { passive: false });
  svg.addEventListener('dblclick', event => { event.preventDefault(); zoomGraph(event.shiftKey ? .65 : 1.55, graphPoint(event.clientX, event.clientY)); });
  svg.addEventListener('pointerover', event => { const node = event.target.closest('[data-node]'); if (node) highlightGraph(node.dataset.node); });
  svg.addEventListener('pointerout', event => { if (!event.relatedTarget?.closest?.('[data-node]')) highlightGraph(null); });
  const beginGesture = () => {
    const points = [...explorer.pointers.values()];
    if (!points.length) { explorer.gesture = null; return; }
    const center = points.length > 1 ? { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 } : points[0];
    explorer.gesture = { center, distance: points.length > 1 ? Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)) : 0, zoom: state.zoom, x: state.panX, y: state.panY };
  };
  svg.addEventListener('pointerdown', event => {
    if (event.button > 0) return;
    if (event.pointerType !== 'touch' && event.target.closest('.graph-node, .graph-link')) return;
    explorer.pointers.set(event.pointerId, graphPoint(event.clientX, event.clientY)); dragged = false; beginGesture();
    if (event.pointerType !== 'touch') svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener('pointermove', event => {
    if (!explorer.pointers.has(event.pointerId)) return;
    const point = graphPoint(event.clientX, event.clientY); explorer.pointers.set(event.pointerId, point);
    const points = [...explorer.pointers.values()], gesture = explorer.gesture;
    const center = points.length > 1 ? { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 } : point;
    if (Math.hypot(center.x - gesture.center.x, center.y - gesture.center.y) > 3 || points.length > 1) {
      dragged = true; explorer.fit = false; svg.classList.add('is-dragging');
      if (!svg.hasPointerCapture(event.pointerId)) svg.setPointerCapture(event.pointerId);
      const distance = points.length > 1 ? Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) : 0;
      state.zoom = gesture.distance ? Math.max(.12, Math.min(5, gesture.zoom * distance / gesture.distance)) : gesture.zoom;
      const ratio = state.zoom / gesture.zoom;
      state.panX = center.x - (gesture.center.x - gesture.x) * ratio;
      state.panY = center.y - (gesture.center.y - gesture.y) * ratio; updateCamera();
    }
  });
  const endPointer = event => {
    explorer.pointers.delete(event.pointerId); beginGesture();
    if (!explorer.pointers.size) { svg.classList.remove('is-dragging'); setTimeout(() => { dragged = false; }, 0); }
  };
  svg.addEventListener('pointerup', endPointer); svg.addEventListener('pointercancel', endPointer); svg.addEventListener('lostpointercapture', endPointer);
  document.addEventListener('keydown', event => {
    if (event.target.closest('input,select,textarea') || event.ctrlKey || event.metaKey || event.altKey) return;
    const expanded = $('#graph-dialog').open;
    if (!expanded && !event.target.closest('#graph-workspace')) return;
    if (['Enter', ' '].includes(event.key) && event.target.matches('#graph [role=button]')) { event.preventDefault(); event.target.dispatchEvent(new MouseEvent('click', { bubbles: true })); return; }
    const actions = { '+': () => zoomGraph(1.25), '=': () => zoomGraph(1.25), '-': () => zoomGraph(.8), '0': resetCamera, f: () => expanded ? closeGraph() : openGraph(), '/': () => $('#graph-search').focus(), ArrowLeft: () => { state.panX += 60; }, ArrowRight: () => { state.panX -= 60; }, ArrowUp: () => { state.panY += 60; }, ArrowDown: () => { state.panY -= 60; } };
    if (actions[event.key]) { event.preventDefault(); if (event.key.startsWith('Arrow')) explorer.fit = false; actions[event.key](); updateCamera(); }
  });
}
