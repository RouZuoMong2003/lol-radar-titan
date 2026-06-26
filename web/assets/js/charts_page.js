/**
 * L2 多维数据浏览页 - 调度层 (Part 1)
 *
 * 三层筛选：
 *   1) 业务领域(domain)   英雄/战队/选手/比赛节奏/横扫矩阵
 *   2) 图谱(chart_type)   C1..C7
 *   3) 标题搜索(模糊)
 *
 * 卡片内子操作：
 *   - C1 / C6 大数据集：Top N
 *   - C4 雷达：实体选择器
 *
 * 依赖 charts_engine.js：COLOR / PALETTE / TYPE_LABEL / rowsToRecords / renderC1..renderC4
 */

// ===== C5 条形 =====
function renderC5(ctx, payload) {
  const records = rowsToRecords(payload);
  const cols = payload.columns;
  const xField = cols[0], yField = cols[1];
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: records.map(r => r[xField]),
      datasets: [{
        label: yField,
        data: records.map(r => r[yField]),
        backgroundColor: records.map((_, i) => PALETTE[i % PALETTE.length] + 'cc'),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { grid: { color: COLOR.line() }, title: { display: true, text: yField, color: COLOR.muted() } },
      }
    }
  });
}

// ===== C6 复合 =====
function renderC6(ctx, payload) {
  const records = rowsToRecords(payload).slice(0, 12);
  const cols = payload.columns;
  const nameField = cols[1] && /name|id/i.test(cols[1]) ? cols[1] : cols[0];
  const numCols = cols.slice(1).filter(c => typeof records[0]?.[c] === 'number');
  const barField  = numCols[0];
  const lineField = numCols[1] || barField;
  return new Chart(ctx, {
    data: {
      labels: records.map(r => r[nameField]),
      datasets: [
        { label: barField, type: 'bar',
          data: records.map(r => r[barField]),
          backgroundColor: COLOR.blue() + 'cc', borderRadius: 4, yAxisID: 'y' },
        { label: lineField, type: 'line',
          data: records.map(r => r[lineField]),
          borderColor: COLOR.orange(), backgroundColor: COLOR.orange() + '33',
          tension: 0.3, pointRadius: 3, yAxisID: 'y1' },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 8, font: { size: 10 } } } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 50 } },
        y:  { position: 'left',  grid: { color: COLOR.line() } },
        y1: { position: 'right', grid: { display: false } },
      }
    }
  });
}

// ===== C7 指标卡 =====
function renderC7(wrapEl, payload) {
  const records = rowsToRecords(payload);
  const cols = payload.columns;
  const FOLD = 8;                              // 移动端折叠阈值
  const expandKey = `__c7_expanded__${payload.chart_id || Math.random()}`;
  const expanded = wrapEl.dataset.expanded === '1';
  const visible = expanded ? records : records.slice(0, FOLD);
  const html = ['<div class="kpi-grid">'];
  visible.forEach(r => {
    const label = r[cols[0]];
    const numCol = cols.slice(1).find(c => typeof r[c] === 'number');
    const value  = numCol ? r[numCol] : '—';
    const subs   = cols.slice(1).filter(c => c !== numCol);
    html.push(`<div class="kpi-cell">
      <div class="k-label">${label}</div>
      <div class="k-value">${value}</div>
      ${subs.slice(0, 3).map(c => `<div class="k-row">${c}: ${r[c]}</div>`).join('')}
    </div>`);
  });
  html.push('</div>');
  // 折叠展开按钮
  if (records.length > FOLD) {
    const more = records.length - FOLD;
    html.push(
      `<button class="kpi-toggle" data-action="toggle">${
        expanded ? `▲ 收起（共 ${records.length} 项）` : `▼ 展开剩余 ${more} 项`
      }</button>`
    );
  }
  wrapEl.innerHTML = html.join('');
  const btn = wrapEl.querySelector('.kpi-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      wrapEl.dataset.expanded = expanded ? '' : '1';
      renderC7(wrapEl, payload);
    });
  }
}

const RENDERERS = { C1: renderC1, C2: renderC2, C3: renderC3, C4: renderC4,
                    C5: renderC5, C6: renderC6 };

// ===== 全局状态 =====
const state = {
  index: null,           // {domains, charts, count}
  domain: 'ALL',
  type: 'ALL',
  q: '',
  cards: new Map(),      // chart_id -> {topN, entityId, chartInst}
};

async function fetchJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
}

// 找出当 Top N 时用什么列排序
function pickSortIdx(payload) {
  const cols = payload.columns;
  const preferred = ['games_played', 'games', 'patch_games', 'patch_picks',
                     'pickrate_pct', 'winrate_pct', 'team_games'];
  for (const p of preferred) {
    const i = cols.indexOf(p);
    if (i >= 0) return i;
  }
  const firstRow = payload.rows[0] || [];
  for (let i = 1; i < cols.length; i++) {
    if (typeof firstRow[i] === 'number') return i;
  }
  return 1;
}

// C4 实体选择器需要确定 id 列 / 显示名列
function entityCols(payload) {
  const cols = payload.columns;
  let idCol, nameCol;
  if (cols.includes('player_id')) { idCol = 'player_id'; nameCol = 'player_name'; }
  else if (cols.includes('team_id')) { idCol = 'team_id'; nameCol = 'team_name'; }
  else { idCol = nameCol = cols[0]; }   // 英雄：champion_name 同时是 id 和名
  return { idCol, nameCol };
}

// ===== 卡片骨架 =====
function buildCard(meta) {
  const card = document.createElement('div');
  card.className = 'chart-card' + (meta.chart_type === 'C7' ? ' kpi' : '');
  card.dataset.chartId = meta.chart_id;
  card.dataset.type = meta.chart_type;
  card.dataset.domain = meta.domain;
  card.innerHTML = `
    <div class="ch-title">
      <h3>${meta.title}</h3>
      <span class="ch-id">${meta.chart_id} · ${meta.domain_label} · ${TYPE_LABEL[meta.chart_type]}</span>
    </div>
    <div class="ch-sub">${meta.subtitle || ''}</div>
    <div class="ch-toolbar"></div>
    <div class="ch-canvas-wrap"><canvas></canvas></div>
  `;
  return card;
}

// ===== 卡片内工具栏（按图谱差异化） =====
function setupCardToolbar(card, meta, payload, rerender) {
  const bar = card.querySelector('.ch-toolbar');
  bar.innerHTML = '';
  const cardState = state.cards.get(meta.chart_id) || {};

  // C1 / C6：Top N 控制
  if (['C1', 'C6'].includes(meta.chart_type) && payload.rows.length > 30) {
    const total = payload.rows.length;
    const defaultN = total > 200 ? 50 : (total > 50 ? 50 : total);
    const cur = cardState.topN || defaultN;
    const options = [20, 50, 100, 200, total]
      .map(n => Math.min(n, total))
      .filter((n, i, a) => a.indexOf(n) === i);
    const sel = document.createElement('select');
    options.forEach(n => {
      const opt = document.createElement('option');
      opt.value = n;
      opt.textContent = n === total ? `全部 ${n}` : `Top ${n}`;
      if (n === cur) opt.selected = true;
      sel.appendChild(opt);
    });
    if (!cardState.topN) state.cards.set(meta.chart_id, { ...cardState, topN: defaultN });
    sel.addEventListener('change', () => {
      const cs = state.cards.get(meta.chart_id) || {};
      state.cards.set(meta.chart_id, { ...cs, topN: +sel.value });
      rerender();
    });
    const lbl = document.createElement('span'); lbl.textContent = '显示';
    bar.append(lbl, sel);
  }

  // C4：实体选择器
  if (meta.chart_type === 'C4') {
    const records = rowsToRecords(payload);
    const minSample = payload.sample_min || 0;
    const pool = records
      .filter(r => (r.games_played || 0) >= minSample)
      .sort((a, b) => (b.games_played || 0) - (a.games_played || 0))
      .slice(0, 200);   // 限 200，避免下拉过长
    const { idCol, nameCol } = entityCols(payload);
    if (!cardState.entityId && pool[0]) {
      state.cards.set(meta.chart_id, { ...cardState, entityId: pool[0][idCol] });
    }
    const sel = document.createElement('select');
    pool.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r[idCol];
      opt.textContent = `${r[nameCol]} (${r.games_played || 0}场)`;
      if (r[idCol] === (state.cards.get(meta.chart_id) || {}).entityId) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', () => {
      const cs = state.cards.get(meta.chart_id) || {};
      state.cards.set(meta.chart_id, { ...cs, entityId: sel.value });
      rerender();
    });
    const lbl = document.createElement('span'); lbl.textContent = '实体';
    bar.append(lbl, sel);
  }
}

// ===== 渲染单卡 =====
async function renderChart(card, meta) {
  const wrap = card.querySelector('.ch-canvas-wrap');
  try {
    const payload = await fetchJSON(`${CHARTS_PATH}/${meta.chart_id}.json`);

    const doRender = () => {
      const cs = state.cards.get(meta.chart_id) || {};
      if (cs.chartInst) { try { cs.chartInst.destroy(); } catch (_) {} }
      wrap.innerHTML = '<canvas></canvas>';

      if (meta.chart_type === 'C7') { renderC7(wrap, payload); return; }

      // 应用 Top N
      let cropped = payload;
      if (cs.topN && payload.rows.length > cs.topN) {
        const idx = pickSortIdx(payload);
        const rows = [...payload.rows]
          .sort((a, b) => (b[idx] || 0) - (a[idx] || 0))
          .slice(0, cs.topN);
        cropped = { ...payload, rows };
      }
      // 应用 C4 实体选择
      if (meta.chart_type === 'C4' && cs.entityId) {
        const { idCol } = entityCols(payload);
        const i = payload.columns.indexOf(idCol);
        const hit = payload.rows.find(r => r[i] === cs.entityId);
        if (hit) cropped = { ...payload, rows: [hit] };
      }

      const fn = RENDERERS[meta.chart_type];
      if (!fn) {
        wrap.innerHTML = `<div style="color:${COLOR.muted()};padding:20px;font-size:12px;">未实现谱: ${meta.chart_type}</div>`;
        return;
      }
      const ctx = wrap.querySelector('canvas').getContext('2d');
      const inst = fn(ctx, cropped);
      state.cards.set(meta.chart_id, { ...cs, chartInst: inst });
    };

    setupCardToolbar(card, meta, payload, doRender);
    doRender();
  } catch (e) {
    wrap.innerHTML = `<div style="color:#ef4444;padding:20px;font-size:12px;">渲染失败: ${e.message}</div>`;
  }
}

// ===== 三层筛选 =====
function applyFilter() {
  const q = state.q.trim().toLowerCase();
  return state.index.charts.filter(c =>
    (state.domain === 'ALL' || c.domain === state.domain) &&
    (state.type   === 'ALL' || c.chart_type === state.type) &&
    (!q || c.title.toLowerCase().includes(q) || c.chart_id.toLowerCase().includes(q))
  );
}

// type 联动 domain：只展示当前 domain 下存在的图谱
function visibleTypes() {
  const m = {};
  state.index.charts
    .filter(c => state.domain === 'ALL' || c.domain === state.domain)
    .forEach(c => { m[c.chart_type] = (m[c.chart_type] || 0) + 1; });
  return m;
}

function renderFilterBar() {
  const root = document.getElementById('charts-filter');
  const domains = state.index.domains;
  const typesAll = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'];
  const typesCount = visibleTypes();
  // 当 type 不在当前 domain 中时自动回退到 ALL
  if (state.type !== 'ALL' && !typesCount[state.type]) state.type = 'ALL';

  root.innerHTML = `
    <div class="filter-row scrollable">
      <span class="filter-label">领域</span>
      <button class="chip ${state.domain === 'ALL' ? 'on' : ''}" data-dim="domain" data-val="ALL">
        全部<span class="chip-count">${state.index.count}</span>
      </button>
      ${domains.map(d => `
        <button class="chip ${state.domain === d.key ? 'on' : ''}" data-dim="domain" data-val="${d.key}">
          ${d.label}<span class="chip-count">${d.count}</span>
        </button>
      `).join('')}
    </div>
    <div class="filter-row scrollable">
      <span class="filter-label">图谱</span>
      <button class="chip ${state.type === 'ALL' ? 'on' : ''}" data-dim="type" data-val="ALL">全部</button>
      ${typesAll.filter(t => typesCount[t]).map(t => `
        <button class="chip ${state.type === t ? 'on' : ''}" data-dim="type" data-val="${t}">
          ${t} ${TYPE_LABEL[t]}<span class="chip-count">${typesCount[t]}</span>
        </button>
      `).join('')}
    </div>
    <div class="filter-row search-row">
      <span class="filter-label">搜索</span>
      <input class="search" type="search" placeholder="标题或编号…" value="${state.q}">
      ${state.q || state.domain !== 'ALL' || state.type !== 'ALL'
        ? '<button class="clear-btn" id="clear-filter">清除</button>'
        : ''}
    </div>
  `;

  // 绑定 chip
  root.querySelectorAll('.chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const dim = btn.dataset.dim, val = btn.dataset.val;
      state[dim] = val;
      // 切换 domain 时清掉 type
      if (dim === 'domain') state.type = 'ALL';
      rerenderAll();
    });
  });
  // 绑定搜索
  const inp = root.querySelector('input.search');
  let t = null;
  inp.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(() => {
      state.q = inp.value;
      renderGrid();
      // 搜索时不重渲 filter bar，避免 input 失焦
      const btn = document.getElementById('clear-filter');
      if (!btn && state.q) renderFilterBar();
      if (btn && !state.q && state.domain === 'ALL' && state.type === 'ALL') renderFilterBar();
    }, 160);
  });
  const clearBtn = document.getElementById('clear-filter');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    state.q = ''; state.domain = 'ALL'; state.type = 'ALL';
    rerenderAll();
  });
}

function renderGrid() {
  const root = document.getElementById('charts-grid');
  const pool = applyFilter();
  // 销毁旧实例
  state.cards.forEach((cs, id) => {
    if (cs.chartInst) { try { cs.chartInst.destroy(); } catch (_) {} cs.chartInst = null; }
  });
  root.innerHTML = '';
  if (pool.length === 0) {
    root.innerHTML = `<div class="empty-result">
      没有匹配的图表。<br>
      <button class="clear-btn" id="empty-clear">清除筛选</button>
    </div>`;
    const btn = document.getElementById('empty-clear');
    if (btn) btn.addEventListener('click', () => {
      state.q = ''; state.domain = 'ALL'; state.type = 'ALL';
      rerenderAll();
    });
    document.getElementById('charts-meta').textContent =
      `0 / ${state.index.count} 张`;
    return;
  }
  document.getElementById('charts-meta').textContent =
    `${pool.length} / ${state.index.count} 张`;
  pool.forEach(meta => {
    const card = buildCard(meta);
    root.appendChild(card);
    requestAnimationFrame(() => renderChart(card, meta));
  });
}

function rerenderAll() {
  renderFilterBar();
  renderGrid();
}

async function bootstrap() {
  const root = document.getElementById('charts-grid');
  try {
    state.index = await fetchJSON(`${CHARTS_PATH}/index.json`);
  } catch (e) {
    root.innerHTML = `<div class="empty-result" style="color:#ef4444;">
      无法加载 ${CHARTS_PATH}/index.json：${e.message}<br>
      请先运行 <code>python3 scripts/09_export_l2_charts.py</code>
    </div>`;
    return;
  }
  rerenderAll();
}

document.addEventListener('DOMContentLoaded', bootstrap);