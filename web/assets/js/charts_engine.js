/**
 * L2 多维数据浏览页 - 渲染引擎（Part 1：核心 + C1-C4）
 * 数据源：web/data/charts/index.json + {CHxx}.json
 */
const CHARTS_PATH = './data/charts';

const TYPE_LABEL = {
  C1: '散点', C2: '堆叠面积', C3: '折线',
  C4: '雷达', C5: '条形', C6: '复合', C7: '指标卡',
};

const CSS = () => getComputedStyle(document.documentElement);
const COLOR = {
  blue:   () => CSS().getPropertyValue('--blue').trim()   || '#6366f1',
  orange: () => CSS().getPropertyValue('--orange').trim() || '#f59e0b',
  ink:    () => CSS().getPropertyValue('--ink').trim()    || '#1e293b',
  muted:  () => CSS().getPropertyValue('--muted').trim()  || '#64748b',
  line:   () => CSS().getPropertyValue('--line').trim()   || 'rgba(148,163,184,0.2)',
};
const PALETTE = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6',
  '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#3b82f6',
  '#a855f7', '#14b8a6',
];

function rowsToRecords(payload) {
  const cols = payload.columns;
  return (payload.rows || []).map(r => {
    const o = {}; cols.forEach((c, i) => { o[c] = r[i]; }); return o;
  });
}

function pickField(cols, slotText) {
  if (!slotText) return null;
  const t = String(slotText).toLowerCase();
  return cols.find(c => t.includes(c.toLowerCase()));
}

// ===== C1 散点 =====
function renderC1(ctx, payload) {
  const records = rowsToRecords(payload);
  const cols = payload.columns;
  const slot = payload.slots || {};
  const xField = pickField(cols, slot.s1) || cols[4] || cols[1];
  const yField = pickField(cols, slot.s2) || cols[3] || cols[2];
  return new Chart(ctx, {
    type: 'scatter',
    data: { datasets: [{
      label: payload.title,
      data: records.map(r => ({ x: r[xField], y: r[yField], _name: r[cols[0]] })),
      backgroundColor: COLOR.blue() + '99',
      borderColor: COLOR.blue(),
      pointRadius: 3.5, pointHoverRadius: 6,
    }]},
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => `${c.raw._name}: ${xField}=${c.parsed.x}, ${yField}=${c.parsed.y}` } }
      },
      scales: {
        x: { title: { display: true, text: xField, color: COLOR.muted() }, grid: { color: COLOR.line() } },
        y: { title: { display: true, text: yField, color: COLOR.muted() }, grid: { color: COLOR.line() } },
      }
    }
  });
}

// ===== C2 堆叠面积（long 表 → 宽表） =====
function renderC2(ctx, payload) {
  const records = rowsToRecords(payload);
  const cols = payload.columns;
  const timeCol = cols.find(c => /patch|date/i.test(c)) || cols[0];
  const keyCol  = cols.find(c => c !== timeCol && /name|key|champion|objective|type/i.test(c)) || cols[1];
  const valCol  = cols.find(c => c !== timeCol && c !== keyCol) || cols[2];

  const times = [...new Set(records.map(r => r[timeCol]))].sort();
  const sumBy = {};
  records.forEach(r => { sumBy[r[keyCol]] = (sumBy[r[keyCol]] || 0) + (r[valCol] || 0); });
  const topKeys = Object.keys(sumBy).sort((a,b) => sumBy[b] - sumBy[a]).slice(0, 8);

  const datasets = topKeys.map((k, i) => ({
    label: k,
    data: times.map(t => {
      const hit = records.find(r => r[timeCol] === t && r[keyCol] === k);
      return hit ? hit[valCol] : 0;
    }),
    backgroundColor: PALETTE[i % PALETTE.length] + 'cc',
    borderColor: PALETTE[i % PALETTE.length],
    fill: true, stack: 'a', pointRadius: 0, borderWidth: 1,
  }));
  return new Chart(ctx, {
    type: 'line', data: { labels: times, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 8, font: { size: 9 } } } },
      scales: {
        x: { grid: { display: false }, title: { display: true, text: timeCol, color: COLOR.muted() } },
        y: { stacked: true, grid: { color: COLOR.line() } },
      }
    }
  });
}

// ===== C3 折线 =====
function renderC3(ctx, payload) {
  const records = rowsToRecords(payload);
  const cols = payload.columns;
  const xField = cols[0];
  const yFields = cols.slice(1).filter(c => typeof records[0]?.[c] === 'number').slice(0, 3);
  const lines = yFields.map((f, i) => ({
    label: f,
    data: records.map(r => r[f]),
    borderColor: PALETTE[i], backgroundColor: PALETTE[i] + '22',
    tension: 0.3, pointRadius: 3,
  }));
  return new Chart(ctx, {
    type: 'line',
    data: { labels: records.map(r => r[xField]), datasets: lines },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 8, font: { size: 10 } } } },
      scales: {
        x: { grid: { display: false }, title: { display: true, text: xField, color: COLOR.muted() } },
        y: { grid: { color: COLOR.line() } },
      }
    }
  });
}

// ===== C4 雷达（取样本量最高的实体） =====
function renderC4(ctx, payload) {
  const records = rowsToRecords(payload);
  if (records.length === 0) return null;
  const pctlCols = payload.columns.filter(c => c.endsWith('_pctl') || c.endsWith('_safe_pctl'));
  const sorted = [...records].sort((a, b) => (b.games_played || 0) - (a.games_played || 0));
  const top = sorted[0];
  return new Chart(ctx, {
    type: 'radar',
    data: {
      labels: pctlCols.map(c => c.replace('_safe_pctl', '_safe').replace('_pctl', '')),
      datasets: [{
        label: top[payload.columns[0]],
        data: pctlCols.map(c => top[c]),
        borderColor: COLOR.blue(),
        backgroundColor: COLOR.blue() + '33',
        pointRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } },
      scales: { r: {
        min: 0, max: 100, ticks: { stepSize: 25, color: COLOR.muted(), backdropColor: 'transparent' },
        grid: { color: COLOR.line() }, angleLines: { color: COLOR.line() },
        pointLabels: { font: { size: 9 }, color: COLOR.ink() }
      }}
    }
  });
}