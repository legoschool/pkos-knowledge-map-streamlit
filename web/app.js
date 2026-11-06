/* PKOS 지식맵 — all assets and data stay on this computer. No external libraries. */
(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const offline = !!window.PKOS_EXPORT;
  const MAP_LIMIT = 220;
  const LIST_PAGE_SIZE = 100;
  const state = {
    graph: null, selected: null, category: '', query: '', view: 'map', busy: false,
    listPage: 0,
    actionBusy: false, stopped: false, initialized: false, graphKey: '',
    zoom: 1, panX: 0, panY: 0, drag: null, bodyRequest: 0, bodyCache: new Map(),
    toastTimer: null, pollTimer: null, pollInFlight: false, projectKey: '', requested: false,
  };

  const asText = value => value == null ? '' : String(value);
  const lower = value => asText(value).toLocaleLowerCase('ko');
  const colorFor = value => /^#[0-9a-f]{3,8}$/i.test(asText(value)) ? value : '#87aa8c';
  const short = (value, count) => Array.from(asText(value)).slice(0, count).join('') + (Array.from(asText(value)).length > count ? '…' : '');

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = asText(text);
    return el;
  }

  function svg(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attrs || {})) el.setAttribute(name, asText(value));
    if (text != null) el.textContent = asText(text);
    return el;
  }

  function toast(message, error = false) {
    clearTimeout(state.toastTimer);
    $('toast').textContent = message;
    $('toast').classList.toggle('error', error);
    $('toast').hidden = false;
    state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 6500 : 3500);
  }

  async function api(path, data) {
    const response = await fetch(path, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
      credentials: 'same-origin', cache: 'no-store',
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const contentType = response.headers.get('content-type') || '';
    const result = contentType.includes('application/json') ? await response.json() : { error: await response.text() };
    if (!response.ok || result.error) {
      const message = typeof result.error === 'object' ? result.error.message : result.error;
      throw new Error(message || result.message || `요청을 처리하지 못했습니다 (${response.status}).`);
    }
    return result;
  }

  function errorPanel(message) {
    $('error-text').textContent = asText(message);
    $('error-panel').hidden = !message;
  }

  function setDisabled() {
    const busy = state.busy || state.actionBusy;
    for (const el of document.querySelectorAll('#build-form input, #build-form button, #demo-button, #welcome-demo, #edit-form input, #edit-form textarea, #edit-form button, #link-form input, #link-form select, #link-form button, .remove-link')) {
      el.disabled = busy;
    }
    $('shutdown').disabled = busy;
    $('build-button').textContent = state.busy ? '자료를 정리하고 있어요…' : '✦ 지식맵 만들기';
    $('build-form').setAttribute('aria-busy', String(busy));
  }

  function modeChanged() {
    const existing = document.querySelector('input[name="mode"]:checked').value === 'existing';
    $('source-label').textContent = existing ? '기존 변환 결과 폴더' : '내 자료 폴더';
    $('source-help').textContent = existing ? '_index.json이 있는 폴더를 고르면 지도를 만듭니다.' : '문서·발표·사진 등 자료가 담긴 폴더를 고릅니다.';
    $('source-path').placeholder = existing ? '_변환결과 폴더를 선택하세요' : '폴더를 선택하세요';
    $('output-field').hidden = existing;
    $('conversion-options').hidden = existing;
  }

  function projectToForm(project) {
    if (!project) return;
    const key = JSON.stringify(project);
    if (state.projectKey === key) return;
    state.projectKey = key;
    if (project.title) $('project-title').value = project.title;
    if (project.source) $('source-path').value = project.source;
    $('output-path').value = project.output || '';
    // Old/imported projects can have unknown provenance. Only hydrate known
    // settings; the checkbox describes the next conversion, not past masking.
    if (typeof project.privacy === 'boolean') $('privacy').checked = project.privacy;
    if (typeof project.ocr === 'boolean') $('ocr').checked = project.ocr;
    const mode = project.mode === 'existing' ? 'existing' : 'convert';
    document.querySelector(`input[name="mode"][value="${mode}"]`).checked = true;
    modeChanged();
  }

  function applyStatus(data) {
    const wasBusy = state.busy;
    state.busy = !!data.busy;
    if (!state.initialized || state.requested || (wasBusy && !state.busy)) projectToForm(data.project);
    state.initialized = true;
    if (!state.busy) state.requested = false;
    setDisabled();
    const hasJob = state.busy || !!data.error || !!data.phase && !['idle', 'ready'].includes(data.phase);
    $('job-panel').hidden = !hasJob;
    $('job-title').textContent = state.busy ? '나의 지식맵을 만들고 있어요' : data.error ? '작업을 확인해 주세요' : '자료 정리가 끝났습니다';
    $('job-message').textContent = data.message || (state.busy ? '파일을 읽고 분류하고 있습니다. 자료가 많으면 시간이 걸릴 수 있어요.' : '지도의 자료를 눌러 내용을 살펴보세요.');
    $('job-indicator').classList.toggle('done', !state.busy);
    $('job-indicator').textContent = state.busy ? '' : data.error ? '!' : '✓';
    const logLines = Array.isArray(data.logs) ? data.logs : [];
    $('job-logs').textContent = logLines.slice(-120).join('\n');
    if ($('job-details').open) $('job-logs').scrollTop = $('job-logs').scrollHeight;
    errorPanel(data.error || '');
    if (data.graph) {
      const key = JSON.stringify(data.graph);
      if (key !== state.graphKey) {
        state.graphKey = key;
        setGraph(data.graph);
      }
    }
  }

  async function poll() {
    if (offline || state.stopped || state.pollInFlight) return;
    state.pollInFlight = true;
    try {
      applyStatus(await api('/api/state'));
      $('local-label').textContent = '내 컴퓨터에서 실행 중';
    } catch (error) {
      $('local-label').textContent = '프로그램 연결 확인';
      if (!state.initialized) errorPanel('프로그램에 연결할 수 없습니다. 지식맵 실행 파일로 다시 시작한 뒤 열린 브라우저를 사용해 주세요.');
      else if (state.busy) errorPanel('프로그램 연결이 끊겼습니다. 실행 창이 열려 있는지 확인해 주세요. 다시 연결되면 진행 상황을 불러옵니다.');
    }
    state.pollInFlight = false;
    clearTimeout(state.pollTimer);
    if (!state.stopped) state.pollTimer = setTimeout(poll, state.busy ? 1000 : 4000);
  }

  async function startJob(path, payload) {
    if (state.busy || state.actionBusy) return;
    state.actionBusy = true;
    state.requested = true;
    setDisabled();
    errorPanel('');
    try {
      await api(path, payload);
      state.busy = true;
      $('job-panel').hidden = false;
      $('job-title').textContent = '나의 지식맵을 만들고 있어요';
      $('job-message').textContent = '자료를 준비하고 있습니다…';
      $('job-indicator').classList.remove('done');
      $('job-indicator').textContent = '';
      clearTimeout(state.pollTimer);
      await poll();
      $('job-panel').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (error) {
      state.requested = false;
      state.busy = false;
      errorPanel(error.message);
    } finally {
      state.actionBusy = false;
      setDisabled();
    }
  }

  function setGraph(graph) {
    if (!graph || !Array.isArray(graph.nodes)) return;
    state.graph = { ...graph, categories: Array.isArray(graph.categories) ? graph.categories : [], edges: Array.isArray(graph.edges) ? graph.edges : [] };
    state.bodyCache.clear();
    $('welcome').hidden = true;
    $('explorer').hidden = false;
    $('map-title').textContent = graph.title || '나의 지식맵';
    document.title = `${graph.title || '나의 지식맵'} · PKOS 지식맵`;
    $('stat-documents').textContent = graph.nodes.length.toLocaleString();
    $('stat-categories').textContent = state.graph.categories.length.toLocaleString();
    $('stat-links').textContent = state.graph.edges.length.toLocaleString();
    $('map-description').textContent = graph.nodes.length ? '자료를 선택해 내용과 연결 이유를 살펴보세요.' : '읽을 수 있는 자료가 없습니다. 진행 기록을 확인하거나 다른 폴더를 선택해 주세요.';
    if (state.selected && !graph.nodes.some(node => node.id === state.selected)) state.selected = null;
    if (state.category && !state.graph.categories.some(c => c.id === state.category)) state.category = '';
    const select = $('category-filter');
    select.replaceChildren(new Option('모든 분야', ''));
    $('category-options').replaceChildren();
    for (const category of state.graph.categories) {
      select.append(new Option(`${category.label} (${category.count})`, category.id));
      $('category-options').append(new Option(category.label, category.label));
    }
    select.value = state.category;
    state.listPage = 0;
    render();
    renderDetail();
  }

  function categoryOf(node) {
    return state.graph.categories.find(category => category.id === node.category) || { id: node.category, label: node.category || '미분류', color: '#8ba587' };
  }

  function filteredNodes() {
    if (!state.graph) return [];
    const terms = lower(state.query).split(/\s+/).filter(Boolean);
    return state.graph.nodes.filter(node => {
      if (state.category && node.category !== state.category) return false;
      const haystack = lower([node.title, node.summary, ...(node.tags || []), node.notes, categoryOf(node).label].join(' '));
      return terms.every(term => haystack.includes(term));
    });
  }

  function tagList(tags) {
    const list = element('div', 'tags');
    for (const tag of (tags || []).slice(0, 12)) list.append(element('span', 'tag', tag));
    return list;
  }

  // Give every field a turn, then spread its allocation across the whole field.
  function balancedSample(nodes, limit, selectedId) {
    if (nodes.length <= limit) return nodes;
    const buckets = new Map();
    for (const node of nodes) {
      if (!buckets.has(node.category)) buckets.set(node.category, { nodes: [], count: 0 });
      buckets.get(node.category).nodes.push(node);
    }
    let remaining = limit;
    while (remaining > 0) {
      for (const bucket of buckets.values()) {
        if (bucket.count < bucket.nodes.length) { bucket.count++; remaining--; }
        if (!remaining) break;
      }
    }
    const sample = [];
    for (const bucket of buckets.values()) {
      for (let i = 0; i < bucket.count; i++) {
        sample.push(bucket.nodes[Math.floor((i + .5) * bucket.nodes.length / bucket.count)]);
      }
    }
    const selected = nodes.find(node => node.id === selectedId);
    if (selected && !sample.some(node => node.id === selected.id)) {
      const replace = sample.findIndex(node => node.category === selected.category);
      sample[replace < 0 ? sample.length - 1 : replace] = selected;
    }
    return sample;
  }

  function render() {
    if (!state.graph) return;
    const nodes = filteredNodes();
    const sample = state.view === 'map' ? balancedSample(nodes, MAP_LIMIT, state.selected) : [];
    state.listPage = Math.min(state.listPage, Math.max(0, Math.ceil(nodes.length / LIST_PAGE_SIZE) - 1));
    const total = state.graph.nodes.length.toLocaleString();
    const matched = nodes.length.toLocaleString();
    const prefix = state.query || state.category ? `전체 ${total}개 · 검색·분야에 일치하는 ${matched}개` : `전체 ${total}개`;
    if (state.view === 'map') {
      $('result-count').textContent = sample.length < nodes.length
        ? `${prefix} 중 지도에는 분야별 대표 ${sample.length}개 표시. 분야/검색으로 좁혀 보세요.`
        : `${prefix} · 지도에 ${matched}개 표시`;
    } else {
      const start = nodes.length ? state.listPage * LIST_PAGE_SIZE + 1 : 0;
      const end = Math.min((state.listPage + 1) * LIST_PAGE_SIZE, nodes.length);
      $('result-count').textContent = `${prefix} · 목록 ${start.toLocaleString()}–${end.toLocaleString()}개 표시`;
    }
    $('clear-filters').hidden = !state.query && !state.category;
    $('map-canvas').hidden = state.view !== 'map';
    $('document-list').hidden = state.view !== 'list';
    $('view-map').setAttribute('aria-pressed', String(state.view === 'map'));
    $('view-list').setAttribute('aria-pressed', String(state.view === 'list'));
    $('map-empty').hidden = nodes.length > 0;
    renderLegend(nodes);
    if (state.view === 'map') renderMap(sample, nodes);
    else renderList(nodes);
  }

  function renderLegend(nodes) {
    const legend = $('category-legend');
    legend.replaceChildren();
    const counts = new Map();
    for (const node of nodes) counts.set(node.category, (counts.get(node.category) || 0) + 1);
    for (const category of state.graph.categories) {
      const count = counts.get(category.id) || 0;
      const button = element('button', state.category === category.id ? 'active' : '', `${category.label} ${count.toLocaleString()}`);
      button.type = 'button';
      button.title = `${category.label} · 현재 검색·분야 조건에 일치하는 자료 ${count.toLocaleString()}개`;
      const dot = element('i');
      dot.style.backgroundColor = colorFor(category.color);
      button.prepend(dot);
      button.setAttribute('aria-pressed', String(state.category === category.id));
      button.addEventListener('click', () => setCategory(state.category === category.id ? '' : category.id));
      legend.append(button);
    }
  }

  function setCategory(category) {
    state.category = category;
    state.listPage = 0;
    $('category-filter').value = category;
    $('document-list').scrollTop = 0;
    resetZoom();
    render();
  }

  function renderList(nodes) {
    const list = $('document-list');
    list.replaceChildren();
    if (!nodes.length) {
      const empty = element('div', 'document-card');
      empty.append(element('h3', '', '찾는 자료가 없습니다'), element('p', '', '검색어를 줄이거나 다른 분야를 선택해 보세요.'));
      list.append(empty);
      return;
    }
    const pages = Math.ceil(nodes.length / LIST_PAGE_SIZE);
    if (pages > 1) {
      const pagination = element('nav', 'list-pagination');
      pagination.setAttribute('aria-label', '자료 목록 페이지');
      const previous = element('button', 'secondary compact', '이전 100개');
      const next = element('button', 'secondary compact', '다음 100개');
      for (const [button, direction] of [[previous, -1], [next, 1]]) {
        button.type = 'button';
        button.dataset.pageDirection = direction;
        button.disabled = direction < 0 ? state.listPage === 0 : state.listPage === pages - 1;
        button.addEventListener('click', () => {
          state.listPage += direction;
          render();
          list.scrollTop = 0;
          list.querySelector(`[data-page-direction="${direction}"]`)?.focus();
        });
      }
      pagination.append(previous, element('span', '', `${state.listPage + 1} / ${pages} 페이지 · 총 ${nodes.length.toLocaleString()}개`), next);
      list.append(pagination);
    }
    const start = state.listPage * LIST_PAGE_SIZE;
    for (const node of nodes.slice(start, start + LIST_PAGE_SIZE)) {
      const category = categoryOf(node);
      const card = element('button', `document-card${state.selected === node.id ? ' selected' : ''}`);
      card.type = 'button';
      card.setAttribute('aria-pressed', String(state.selected === node.id));
      const kind = element('span', 'card-category', `${category.label} · ${node.format || '문서'}`);
      const dot = element('i');
      dot.style.backgroundColor = colorFor(category.color);
      kind.prepend(dot);
      card.append(kind, element('h3', '', node.title), element('p', '', node.summary || '자료를 선택해 내용을 확인하세요.'), tagList((node.tags || []).slice(0, 4)));
      card.addEventListener('click', () => selectNode(node.id, true));
      list.append(card);
    }
  }

  function renderMap(nodes, matchedNodes) {
    const root = $('map-transform');
    root.replaceChildren();
    if (!nodes.length) return;
    const matchedCounts = new Map();
    for (const node of matchedNodes) matchedCounts.set(node.category, (matchedCounts.get(node.category) || 0) + 1);
    const categories = state.graph.categories.filter(category => matchedCounts.has(category.id));
    const positions = new Map();
    const categoryPositions = new Map();
    const count = categories.length;
    const canvasWidth = Math.max(320, $('map-canvas').clientWidth);
    const canvasHeight = Math.max(360, $('map-canvas').clientHeight);
    const readable = nodes.length <= 36 && count <= 6;
    const narrow = canvasWidth < 560;
    const labelChars = readable ? (narrow ? 6 : 8) : nodes.length > 35 ? 9 : 13;
    let extent = readable ? 0 : 660;
    let maxX = 0, maxY = 0;
    const ring = count <= 3 ? 310 : count <= 6 ? 360 : 400 + count * 10;
    const orbitX = readable ? Math.max(95, canvasWidth / 2 - 145) : ring;
    const orbitY = readable ? Math.max(90, canvasHeight / 2 - 110) : ring;
    const edgeLayer = svg('g', { class: 'map-edges' });
    const categoryLayer = svg('g', {});
    const nodeLayer = svg('g', {});
    root.append(edgeLayer, categoryLayer, nodeLayer);

    categories.forEach((category, index) => {
      const offset = count <= 2 ? 0 : count === 4 ? -Math.PI / 4 : -Math.PI / 2;
      const angle = offset + (Math.PI * 2 * index) / count;
      const cx = Math.cos(angle) * orbitX;
      const cy = Math.sin(angle) * orbitY;
      categoryPositions.set(category.id, { x: cx, y: cy });
      const members = nodes.filter(node => node.category === category.id);
      const matchedCount = matchedCounts.get(category.id);
      const perRing = readable ? 8 : count >= 7 ? 10 : 14;
      members.forEach((node, i) => {
        const tier = Math.floor(i / perRing);
        const ringSize = Math.min(perRing, members.length - tier * perRing);
        const a = angle + Math.PI * 2 * (i % perRing) / Math.max(1, ringSize) + tier * .3;
        const radius = readable ? 65 + tier * 44 : 112 + tier * 58;
        const x = cx + Math.cos(a) * radius;
        const y = cy + Math.sin(a) * radius;
        const horizontal = readable && Math.abs(Math.cos(a)) > .55;
        const labelX = horizontal ? (Math.cos(a) < 0 ? -13 : 13) : 0;
        const labelY = horizontal ? 4 : readable && Math.sin(a) < 0 ? -15 : readable ? 23 : 31;
        const anchor = horizontal ? (Math.cos(a) < 0 ? 'end' : 'start') : 'middle';
        positions.set(node.id, { x, y, labelX, labelY, anchor });
        maxX = Math.max(maxX, Math.abs(x) + (horizontal ? labelChars * 11 + 20 : labelChars * 6));
        maxY = Math.max(maxY, Math.abs(y) + 35);
        extent = Math.max(extent, Math.abs(x) + 100, Math.abs(y) + 100);
        edgeLayer.append(svg('line', { x1: cx, y1: cy, x2: x, y2: y, class: 'map-edge' }));
      });
      edgeLayer.append(svg('line', { x1: 0, y1: 0, x2: cx, y2: cy, class: 'map-edge', 'stroke-dasharray': '6 7' }));
      const group = svg('g', { class: 'map-node', transform: `translate(${cx} ${cy})`, tabindex: '0', role: 'button', 'aria-label': `${category.label} 분야 ${matchedCount}개 자료 보기`, 'pointer-events': 'all' });
      const categoryRadius = readable ? 32 : 49;
      group.append(svg('rect', { x: -categoryRadius, y: -categoryRadius, width: categoryRadius * 2, height: categoryRadius * 2, fill: 'transparent', 'pointer-events': 'all' }));
      group.append(svg('circle', { r: categoryRadius, fill: colorFor(category.color), 'fill-opacity': '.17', stroke: colorFor(category.color), 'stroke-width': 1.2, 'stroke-opacity': '.4' }));
      group.append(svg('text', { y: -1, 'text-anchor': 'middle', class: 'category-label', style: `font-size:${readable ? 13 : 18}px` }, short(category.label, readable ? 5 : 6)));
      group.append(svg('text', { y: readable ? 17 : 22, 'text-anchor': 'middle', class: 'category-count', style: `font-size:${readable ? 10 : 12}px` }, `${matchedCount.toLocaleString()}개 자료`));
      group.append(svg('title', {}, `${category.label} · 일치하는 자료 ${matchedCount.toLocaleString()}개 · 지도에 ${members.length}개 표시`));
      const choose = () => setCategory(state.category === category.id ? '' : category.id);
      group.addEventListener('click', event => { event.stopPropagation(); if (!state.drag?.moved) choose(); });
      group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
      categoryLayer.append(group);
    });

    const visibleEdges = state.graph.edges.filter(edge => positions.has(edge.source) && positions.has(edge.target));
    const selectedEdges = state.selected ? visibleEdges.filter(edge => edge.source === state.selected || edge.target === state.selected) : visibleEdges.slice(0, 150);
    const relatedIds = new Set([state.selected]);
    for (const edge of selectedEdges) {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      relatedIds.add(edge.source); relatedIds.add(edge.target);
      const line = svg('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: `map-edge relation ${edge.kind === 'manual' ? 'manual' : ''} ${state.selected ? 'selected' : ''}` });
      line.append(svg('title', {}, edge.label || '연결된 자료'));
      edgeLayer.append(line);
    }

    for (const node of nodes) {
      const point = positions.get(node.id);
      if (!point) continue;
      const category = categoryOf(node);
      const selected = state.selected === node.id;
      const group = svg('g', { class: `map-node${selected ? ' selected' : ''}${state.selected && !relatedIds.has(node.id) ? ' dimmed' : ''}`, transform: `translate(${point.x} ${point.y})`, tabindex: '0', role: 'button', 'aria-label': `${node.title}, ${category.label}`, 'aria-pressed': selected ? 'true' : 'false', 'pointer-events': 'all' });
      const hitWidth = readable ? labelChars * 11 + 22 : 150;
      const hitX = readable && point.anchor === 'start' ? -16 : readable && point.anchor === 'end' ? 16 - hitWidth : -hitWidth / 2;
      group.append(svg('rect', { x: hitX, y: readable ? -25 : -20, width: hitWidth, height: readable ? 55 : 65, fill: 'transparent', 'pointer-events': 'all' }));
      if (selected) group.append(svg('circle', { r: readable ? 17 : 25, fill: colorFor(category.color), 'fill-opacity': '.16' }));
      group.append(svg('circle', { r: readable ? (selected ? 10 : 7) : selected ? 14 : 10, fill: colorFor(category.color), stroke: '#fff', 'stroke-width': readable ? 1.8 : 2.5, class: 'doc-circle' }));
      if (nodes.length <= 85 || selected || state.selected && relatedIds.has(node.id)) group.append(svg('text', { x: readable ? point.labelX : 0, y: readable ? point.labelY : selected ? 39 : 31, 'text-anchor': readable ? point.anchor : 'middle', class: 'node-label', style: `font-size:${readable ? 11 : 15}px;stroke-width:${readable ? 3 : 5}px` }, short(node.title, labelChars)));
      group.append(svg('title', {}, [node.title, ...(node.tags || [])].join('\n')));
      group.addEventListener('click', event => { event.stopPropagation(); if (!state.drag?.moved) selectNode(node.id, true); });
      group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectNode(node.id, true); } });
      nodeLayer.append(group);
    }
    const core = svg('g', { class: 'map-core' });
    core.append(svg('circle', { r: readable ? 39 : 63, fill: '#234d3e' }));
    core.append(svg('circle', { r: readable ? 46 : 72, fill: 'none', stroke: '#cdddc7', 'stroke-width': 1, 'stroke-dasharray': '2 6' }));
    core.append(svg('text', { y: -2, style: `font-size:${readable ? 12 : 19}px` }, short(state.graph.title || '나의 지식맵', readable ? 6 : 8)));
    core.append(svg('text', { y: readable ? 18 : 23, class: 'core-caption', style: `font-size:${readable ? 10 : 12}px` }, `${matchedNodes.length.toLocaleString()}개의 기록`));
    categoryLayer.append(core);
    const ratio = canvasWidth / canvasHeight;
    const halfH = readable ? Math.max(canvasHeight / 2, maxY + 15, (maxX + 15) / ratio) : Math.max(extent, extent / ratio);
    const halfW = halfH * ratio;
    $('knowledge-svg').setAttribute('viewBox', `${-halfW} ${-halfH} ${halfW * 2} ${halfH * 2}`);
    if (!readable) {
      // Keep overview headings readable at the fitted (zoom 1) screen size.
      const unitsPerPixel = halfH * 2 / canvasHeight;
      const titleSize = Math.max(18, 13 * unitsPerPixel);
      const countSize = Math.max(12, 10 * unitsPerPixel);
      const wrapLabel = (label, columns) => {
        const chars = Array.from(label.textContent);
        const lines = [chars.slice(0, columns).join(''), chars.slice(columns).join('')].filter(Boolean);
        const firstY = lines.length > 1 ? -titleSize * .6 : -titleSize * .15;
        label.style.fontSize = `${titleSize}px`;
        label.replaceChildren(...lines.map((line, i) => svg('tspan', { x: 0, y: firstY + i * titleSize * 1.2 }, line)));
        return firstY + (lines.length - 1) * titleSize * 1.2 + countSize * 1.5;
      };
      for (const label of categoryLayer.querySelectorAll('.category-label')) {
        const countLabel = label.parentNode.querySelector('.category-count');
        countLabel.setAttribute('y', wrapLabel(label, 4));
        countLabel.style.fontSize = `${countSize}px`;
        for (const text of [label, countLabel]) {
          text.style.paintOrder = 'stroke';
          text.style.stroke = '#fcfdfb';
          text.style.strokeWidth = `${2 * unitsPerPixel}px`;
          text.style.strokeLinejoin = 'round';
        }
      }
      const coreTitle = core.querySelector('text:not(.core-caption)');
      const coreCaption = core.querySelector('.core-caption');
      coreCaption.setAttribute('y', wrapLabel(coreTitle, 5));
      coreCaption.style.fontSize = `${countSize}px`;
      const coreCircles = core.querySelectorAll('circle');
      coreCircles[0].setAttribute('r', Math.max(63, 45 * unitsPerPixel));
      coreCircles[1].setAttribute('r', Math.max(72, 50 * unitsPerPixel));
    }
    transformMap();
  }

  function transformMap() {
    $('map-transform').setAttribute('transform', `translate(${state.panX} ${state.panY}) scale(${state.zoom})`);
  }

  function resetZoom() {
    state.zoom = 1; state.panX = 0; state.panY = 0;
    transformMap();
  }

  function zoom(factor) {
    state.zoom = Math.min(5, Math.max(.35, state.zoom * factor));
    transformMap();
  }

  function selectNode(id, focusDetail = false) {
    state.selected = id;
    let nodes = filteredNodes();
    if (!nodes.some(node => node.id === id)) {
      state.category = ''; state.query = '';
      $('category-filter').value = ''; $('search').value = '';
      nodes = filteredNodes();
      resetZoom();
    }
    state.listPage = Math.max(0, Math.floor(nodes.findIndex(node => node.id === id) / LIST_PAGE_SIZE));
    render();
    renderDetail();
    if (state.view === 'list') $('document-list').querySelector('.selected')?.scrollIntoView({ block: 'nearest' });
    if (focusDetail && window.innerWidth <= 1440) $('detail-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  async function loadBody(node) {
    const request = ++state.bodyRequest;
    if (offline) return;
    $('detail-body').textContent = '자료를 불러오고 있습니다…';
    try {
      let data = state.bodyCache.get(node.id);
      if (!data) { data = await api(`/api/document?id=${encodeURIComponent(node.id)}`); state.bodyCache.set(node.id, data); }
      if (request === state.bodyRequest) $('detail-body').textContent = data.body || '읽을 수 있는 본문이 없습니다. 원본 파일을 확인해 주세요.';
    } catch (error) {
      if (request === state.bodyRequest) $('detail-body').textContent = `본문을 불러오지 못했습니다. ${error.message}`;
    }
  }

  function renderDetail() {
    const node = state.graph?.nodes.find(item => item.id === state.selected);
    $('detail-placeholder').hidden = !!node;
    $('detail-content').hidden = !node;
    if (!node) { state.bodyRequest++; return; }
    const category = categoryOf(node);
    $('detail-category').textContent = category.label;
    $('detail-title').textContent = node.title;
    $('detail-format').textContent = [node.format || '문서', `${(node.tags || []).length}개 태그`].join(' · ');
    $('detail-tags').replaceChildren(...tagList(node.tags).childNodes);
    $('detail-summary').textContent = node.summary || '요약이 없습니다. 변환한 본문이나 원본 파일을 확인해 주세요.';
    $('detail-notes').textContent = node.notes || '';
    $('detail-note-block').hidden = !node.notes;
    $('detail-source').textContent = `원본 경로 · ${node.source || '기록 없음'}\n변환본 · ${node.md || '기록 없음'}`;
    $('edit-title').value = node.title || '';
    $('edit-category').value = category.label || '';
    $('edit-tags').value = (node.tags || []).join(', ');
    $('edit-notes').value = node.notes || '';
    $('link-target').replaceChildren(new Option('자료를 선택하세요', ''));
    for (const target of state.graph.nodes) if (target.id !== node.id) $('link-target').append(new Option(target.title, target.id));
    $('link-label').value = '';
    $('open-source').disabled = !node.source;
    $('open-md').disabled = !node.md;
    renderRelated(node);
    loadBody(node);
    setDisabled();
  }

  function renderRelated(node) {
    const edges = state.graph.edges.filter(edge => edge.source === node.id || edge.target === node.id);
    $('related-count').textContent = edges.length;
    const list = $('related-list');
    list.replaceChildren();
    if (!edges.length) list.append(element('p', 'empty-related', offline ? '연결된 자료가 아직 없습니다.' : '아직 연결된 자료가 없습니다. 다른 자료와 같은 태그를 붙이거나 직접 연결해 보세요.'));
    for (const edge of edges) {
      const target = state.graph.nodes.find(item => item.id === (edge.source === node.id ? edge.target : edge.source));
      if (!target) continue;
      const row = element('div', 'related-item');
      const button = element('button');
      button.type = 'button';
      button.append(element('strong', '', target.title), element('small', '', `${edge.kind === 'manual' ? '직접 연결 · ' : ''}${edge.label || '공통 태그'}`));
      button.addEventListener('click', () => selectNode(target.id));
      row.append(button);
      if (!offline && edge.kind === 'manual') {
        const remove = element('button', 'remove-link', '해제');
        remove.type = 'button';
        remove.setAttribute('aria-label', `${target.title} 자료와 직접 연결 해제`);
        remove.addEventListener('click', () => mutate('/api/unlink', { source: edge.source, target: edge.target }, '직접 만든 연결을 해제했습니다.'));
        row.append(remove);
      }
      list.append(row);
    }
  }

  async function mutate(path, payload, message) {
    if (offline || state.busy || state.actionBusy) return;
    state.actionBusy = true;
    setDisabled();
    try {
      const result = await api(path, payload);
      if (result.graph) { state.graphKey = JSON.stringify(result.graph); setGraph(result.graph); }
      toast(message);
    } catch (error) {
      toast(error.message, true);
    } finally {
      state.actionBusy = false;
      setDisabled();
    }
  }

  for (const radio of document.querySelectorAll('input[name="mode"]')) radio.addEventListener('change', modeChanged);
  for (const button of document.querySelectorAll('[data-browse]')) button.addEventListener('click', async () => {
    if (state.busy || state.actionBusy) return;
    const input = $(button.dataset.browse === 'source' ? 'source-path' : 'output-path');
    state.actionBusy = true;
    setDisabled();
    $('browse-notice').hidden = false;
    $('cancel-browse').disabled = false;
    $('cancel-browse').textContent = '선택 취소·직접 입력';
    try {
      const result = await api('/api/browse', { kind: button.dataset.browse });
      if (result.path) input.value = result.path;
    } catch (error) { toast(error.message, true); }
    finally {
      $('browse-notice').hidden = true;
      state.actionBusy = false;
      setDisabled();
      input.focus();
    }
  });
  $('cancel-browse').addEventListener('click', async () => {
    $('cancel-browse').disabled = true;
    $('cancel-browse').textContent = '선택 창 닫는 중…';
    try {
      await api('/api/cancel-browse', {});
    } catch (error) {
      toast(error.message, true);
      $('cancel-browse').disabled = false;
      $('cancel-browse').textContent = '선택 취소·직접 입력';
    }
  });
  $('build-form').addEventListener('submit', event => {
    event.preventDefault();
    const mode = document.querySelector('input[name="mode"]:checked').value;
    startJob('/api/build', { source: $('source-path').value.trim(), output: mode === 'existing' ? $('source-path').value.trim() : $('output-path').value.trim(), title: $('project-title').value.trim() || '나의 지식맵', mode, privacy: $('privacy').checked, ocr: $('ocr').checked });
  });
  $('demo-button').addEventListener('click', () => startJob('/api/demo', {}));
  $('welcome-demo').addEventListener('click', () => startJob('/api/demo', {}));
  $('edit-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!state.selected) return;
    const title = $('edit-title').value.trim();
    const category = $('edit-category').value.trim();
    if (!title || !category) { toast('제목과 분야를 입력해 주세요.', true); return; }
    const tags = [...new Set($('edit-tags').value.split(/[,，\n]/).map(tag => tag.trim().replace(/^#/, '')).filter(Boolean))];
    mutate('/api/edit', { id: state.selected, title, category, tags, notes: $('edit-notes').value.trim() }, '분류와 메모를 저장했습니다.');
  });
  $('link-form').addEventListener('submit', event => {
    event.preventDefault();
    const target = $('link-target').value, label = $('link-label').value.trim();
    if (!target || !label) { toast('연결할 자료와 연결 이유를 입력해 주세요.', true); return; }
    mutate('/api/link', { source: state.selected, target, label }, '자료를 연결했습니다.');
  });
  $('search').addEventListener('input', () => { state.query = $('search').value.trim(); state.listPage = 0; $('document-list').scrollTop = 0; resetZoom(); render(); });
  $('category-filter').addEventListener('change', () => setCategory($('category-filter').value));
  $('clear-filters').addEventListener('click', () => { state.query = ''; $('search').value = ''; setCategory(''); });
  $('view-map').addEventListener('click', () => { state.view = 'map'; render(); });
  $('view-list').addEventListener('click', () => { state.view = 'list'; render(); });
  $('detail-close').addEventListener('click', () => { state.selected = null; render(); renderDetail(); });
  $('zoom-in').addEventListener('click', () => zoom(1.25));
  $('zoom-out').addEventListener('click', () => zoom(.8));
  $('zoom-reset').addEventListener('click', resetZoom);
  for (const kind of ['source', 'md']) $(`open-${kind}`).addEventListener('click', async () => {
    if (!state.selected || offline) return;
    try { await api('/api/open', { id: state.selected, kind }); toast(kind === 'source' ? '원본 파일을 열었습니다.' : '변환본 파일을 열었습니다.'); }
    catch (error) { toast(error.message, true); }
  });
  $('shutdown').addEventListener('click', async () => {
    if (state.busy || state.actionBusy || offline) return;
    if (!window.confirm('PKOS 지식맵을 종료할까요? 저장한 자료와 설정은 그대로 남습니다.')) return;
    try {
      await api('/api/shutdown', {});
      state.stopped = true;
      clearTimeout(state.pollTimer);
      document.body.classList.add('program-ended');
      $('local-label').textContent = '프로그램 종료됨';
      $('shutdown').disabled = true;
      toast('프로그램을 종료했습니다. 브라우저 탭을 닫아도 됩니다.');
    } catch (error) { toast(error.message, true); }
  });
  document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  document.addEventListener('keydown', event => {
    const editing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
    if (event.key === '/' && !editing && state.graph) { event.preventDefault(); $('search').focus(); }
    if (event.key === 'Escape' && !editing) { state.selected = null; render(); renderDetail(); }
  });

  const mapSvg = $('knowledge-svg');
  mapSvg.addEventListener('wheel', event => { event.preventDefault(); zoom(event.deltaY < 0 ? 1.12 : .89); }, { passive: false });
  mapSvg.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('[role="button"]')) return;
    state.drag = { x: event.clientX, y: event.clientY, panX: state.panX, panY: state.panY, moved: false };
    mapSvg.setPointerCapture(event.pointerId);
    mapSvg.classList.add('dragging');
  });
  mapSvg.addEventListener('pointermove', event => {
    if (!state.drag || !mapSvg.hasPointerCapture(event.pointerId)) return;
    const rect = mapSvg.getBoundingClientRect(), vb = mapSvg.viewBox.baseVal;
    const dx = event.clientX - state.drag.x, dy = event.clientY - state.drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) state.drag.moved = true;
    state.panX = state.drag.panX + dx * vb.width / Math.max(1, rect.width);
    state.panY = state.drag.panY + dy * vb.height / Math.max(1, rect.height);
    transformMap();
  });
  const endDrag = event => {
    if (mapSvg.hasPointerCapture(event.pointerId)) mapSvg.releasePointerCapture(event.pointerId);
    mapSvg.classList.remove('dragging');
    state.drag = null;
  };
  mapSvg.addEventListener('pointerup', endDrag);
  mapSvg.addEventListener('pointercancel', endDrag);
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.graph && state.view === 'map') render(); }, 150); });

  if (offline) {
    document.body.classList.add('offline');
    $('offline-notice').hidden = false;
    $('local-label').textContent = '읽기 전용 지도';
    setGraph(window.PKOS_EXPORT);
  } else {
    modeChanged();
    poll();
  }
})();
