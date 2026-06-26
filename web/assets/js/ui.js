/**
 * UI 渲染层 — 纯 DOM 操作，无业务副作用
 *
 * 关键点：
 * 1. renderView(viewState, ctx) 是顶层入口，根据三态机切换大块布局可见性。
 * 2. 排行榜支持搜索框（按名/队过滤）。
 * 3. 单实体未选时也能看到榜单 → 点击进入详情。
 * 4. 空数据态有专门 empty 卡片，附操作引导。
 */
const UI = {
  // L1 直透八维 → 英文标签（雷达轴）
  DIM_EN: {
    '击杀产出':  'Kills',
    '助攻贡献':  'Assists',
    '生存能力':  'Survival',
    '经济效率':  'Economy',
    '伤害占比':  'DmgShare',
    '承伤强度':  'Tanking',
    '补刀效率':  'CS/M',
    '首杀参与':  'FirstBlood',
    // 兼容旧重建模型字段
    '团战参与':  'Teamfight',
    '线上压制':  'Laning',
    '长线运营':  'Macro',
    '操作输出':  'Mechanics',
    '心态稳定':  'Consistency',
    '版本适应':  'Adaptation',
    '团战决策':  'Teamfight',
    '操作上限':  'Mechanics',
  },
  POS_LABEL: { top: '上单', jng: '打野', mid: '中单', bot: '下路', sup: '辅助' },

  _handlers: null,
  _errorTimer: null,

  // ============ 顶部控件 ============

  setActiveTab(type) {
    document.querySelectorAll('#seg-type button').forEach(b => {
      const on = b.dataset.type === type;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  },

  renderSeasons(seasons, selectedId) {
    const sel = document.getElementById('sel-season');
    if (!sel) return;
    const placeholder = `<option value="" ${!selectedId ? 'selected' : ''}>选择赛季</option>`;
    sel.innerHTML = placeholder + seasons.map(s => {
      // LCK-2026-Cup → LCK 2026 · Cup
      const pretty = String(s.id).replace(/-/g, ' · ').replace(' · ', ' ');
      return `<option value="${s.id}" ${s.id === selectedId ? 'selected' : ''}>${pretty}</option>`;
    }).join('');
  },

  // ============ 视图切换 ============

  renderView(view, ctx) {
    const root = document.getElementById('poster-card');
    if (!root) return;
    root.dataset.view = view;

    if (view === 'empty-seasons') return this._renderEmptyState();
    if (view === 'pick-entity')   return this._renderPickEntity(ctx);
    this._renderDetail(ctx);
  },

  _renderEmptyState() {
    /* 模板由 index.html 直出，这里仅绑定重试按钮 */
    const btn = document.getElementById('btn-retry');
    if (btn) btn.onclick = () => this._handlers?.onRetry?.();
  },

  _renderPickEntity(ctx) {
    const noun = ctx.type === 'player' ? '选手' : '队伍';
    const title = document.getElementById('picker-title');
    if (title) {
      title.textContent = ctx.seasonId
        ? `请从下方列表选择${noun}`
        : `加载赛季中…`;
    }
    this.renderHeader('—', []);
    this._renderRanking(ctx, /* asPicker */ true);
    this._clearScoresAndMeta();
  },

  _renderDetail(ctx) {
    const data = ctx.currentData;
    if (!data) return;
    this.renderHeader(data.name, data.tags);
    this._renderScores(data.top_stats?.text_score, data.top_stats?.season_rating);
    this._renderMetaGrid(data.raw, ctx.type);
    this._renderRanking(ctx, /* asPicker */ false);
    this._updateLegend(ctx.type);
  },

  // ============ 子模块：标题/标签 ============

  renderHeader(name, tags = []) {
    const nameEl = document.getElementById('t-name');
    const tagsEl = document.getElementById('t-tags');
    if (nameEl) nameEl.textContent = name || '—';
    if (tagsEl) tagsEl.innerHTML = (tags || []).map(t =>
      `<div class="tag ${t.color || 'blue'}">${this._escape(t.label)}</div>`
    ).join('');
  },

  // ============ 子模块：评分卡 ============

  _renderScores(textScore, seasonRating) {
    this._setScore('s1', textScore || {}, '综合评分');
    this._setScore('s2', seasonRating || {}, '赛季评分');
  },

  _clearScoresAndMeta() {
    ['s1', 's2'].forEach(p => this._setScore(p, {}, p === 's1' ? '综合评分' : '赛季评分'));
    const grid = document.getElementById('meta-grid');
    if (grid) grid.innerHTML = '';
  },

  _setScore(prefix, data, defaultSub) {
    const sub  = document.getElementById(`${prefix}-sub`);
    const val  = document.getElementById(`${prefix}-val`);
    const rank = document.getElementById(`${prefix}-rank`);
    const bar  = document.getElementById(`${prefix}-bar`);
    if (sub)  sub.textContent = data.subtitle || defaultSub;
    if (val)  val.textContent = data.value != null ? data.value : '—';
    if (rank) rank.textContent = data.rank ? `#${data.rank}/${data.total || ''}` : '#—';
    if (bar) {
      const pct = Math.min(100, (data.value || 0) / 18);
      bar.style.width = pct + '%';
    }
  },

  // ============ 子模块：详情格 ============

  _renderMetaGrid(rawData, type) {
    const grid = document.getElementById('meta-grid');
    if (!grid) return;
    if (!rawData) { grid.innerHTML = ''; return; }

    const r = rawData;
    const num = v => (typeof v === 'number' ? v : Number(v));
    const winRate = ((r.win_rate || 0) * 100).toFixed(0) + '%';
    const wlSub = (r.wins || 0) + 'W' + (r.losses != null ? '-' + r.losses + 'L' : '');

    const cells = type === 'player' ? [
      { label: '场次',       val: r.games || 0,                                       sub: wlSub },
      { label: '胜率',       val: winRate,                                            sub: '' },
      { label: 'KP%',        val: (r.kp != null ? num(r.kp).toFixed(1) + '%' : '—'),  sub: '团战参与' },
      { label: 'KDA',        val: (r.kda != null ? num(r.kda).toFixed(2) : '—'),      sub: '' },
      { label: 'DPM',        val: (r.avg_dpm != null ? Math.round(num(r.avg_dpm)) : '—'),    sub: '每分钟伤害' },
      { label: 'VSPM',       val: (r.avg_vspm != null ? num(r.avg_vspm).toFixed(2) : '—'),   sub: '视野得分' },
      { label: (r.gd_field === 'gd10' ? 'GD@10' : 'GD@15'),
        val: this._signNum(r.avg_gd15),                                               sub: '金币差' },
      { label: '英雄池',     val: (r.champion_pool != null ? r.champion_pool : '—'),  sub: '局均池深' },
    ] : [
      { label: '场次',  val: r.games || 0,                                            sub: wlSub },
      { label: '胜率',  val: winRate,                                                 sub: '' },
      { label: 'GSPD',  val: this._signNum(r.avg_gspd, 3),                            sub: '经济差' },
      { label: 'GPR',   val: (r.avg_gpr != null ? num(r.avg_gpr).toFixed(3) : '—'),   sub: '黄金比率' },
      { label: 'CKPM',  val: (r.avg_ckpm != null ? num(r.avg_ckpm).toFixed(2) : '—'), sub: '击杀节奏' },
    ];

    grid.innerHTML = cells.map(c => {
      const subHtml = c.sub ? '<span class="meta-sub">' + this._escape(c.sub) + '</span>' : '';
      return '<div class="meta">'
           +   '<div class="meta-label">' + this._escape(c.label) + '</div>'
           +   '<div class="meta-val">' + this._escape(String(c.val)) + subHtml + '</div>'
           + '</div>';
    }).join('');
  },

  // ============ 子模块：排行榜 + 搜索 ============

  _renderRanking(ctx, asPicker) {
    const titleEl  = document.getElementById('ranking-title');
    const listEl   = document.getElementById('ranking-list');
    const searchEl = document.getElementById('rank-search');
    const filterEl = document.getElementById('ranking-filter');
    if (!listEl) return;

    const { entities, type, entityId, currentData, notFound, rankQuery, posFilter } = ctx;

    if (searchEl && searchEl.value !== (rankQuery || '')) {
      searchEl.value = rankQuery || '';
    }

    // 位置 chip 仅在选手视图可见 + 同步 active；未选赛季时整体禁用
    if (filterEl) {
      filterEl.style.display = type === 'player' ? '' : 'none';
      const active = posFilter || 'all';
      const disabled = !ctx.seasonId;
      filterEl.classList.toggle('is-disabled', disabled);
      filterEl.querySelectorAll('.rfilter-chip').forEach(btn => {
        const on = btn.dataset.pos === active;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
        btn.disabled = disabled;
      });
    }

    // 搜索框未选赛季时同步禁用
    if (searchEl) {
      const disabled = !ctx.seasonId;
      searchEl.disabled = disabled;
      searchEl.placeholder = disabled ? '请先选择赛季' : '搜索名称 / 战队';
    }

    if (!entities || entities.length === 0) {
      if (titleEl) titleEl.textContent = asPicker ? '请选择赛季' : '评分排行';
      listEl.innerHTML = '<div class="ranking-empty">' + (ctx.seasonId ? '该赛季暂无数据' : '请先在上方选择一个赛季') + '</div>';
      return;
    }

    // ─── 位置筛选完全由 chip 主导（'all' 即显示全部，不再按当前选手位置自动过滤） ───
    let pool = entities.slice();
    let titleText;
    let effectivePos = null;

    if (type === 'player' && posFilter && posFilter !== 'all') {
      effectivePos = posFilter;
    }

    if (effectivePos) {
      pool = entities.filter(e => e.position === effectivePos);
      titleText = (this.POS_LABEL[effectivePos] || effectivePos.toUpperCase()) + '评分排行';
    } else if (type === 'team') {
      titleText = '战队评分排行';
    } else {
      titleText = '选手评分排行';
    }
    if (titleEl) titleEl.textContent = titleText;

    // 搜索过滤
    const q = (rankQuery || '').trim().toLowerCase();
    if (q) {
      pool = pool.filter(e =>
        (e.name || '').toLowerCase().indexOf(q) >= 0 ||
        (e.team_name || '').toLowerCase().indexOf(q) >= 0 ||
        (e.current_handle || '').toLowerCase().indexOf(q) >= 0
      );
    }
    pool.sort((a, b) => (b.text_score || 0) - (a.text_score || 0));

    if (pool.length === 0) {
      listEl.innerHTML = '<div class="ranking-empty">没有匹配的结果</div>';
      return;
    }

    const banner = notFound
      ? '<div class="ranking-empty">未找到对应的' + (type === 'player' ? '选手' : '队伍') + '，请重新选择</div>'
      : '';

    listEl.innerHTML = banner + pool.map((e, idx) => {
      const isSelected = e.id === entityId;
      const name  = e.name || e.current_handle || '—';
      const score = Math.round(e.text_score || 0);
      const rank  = idx + 1;
      const teamLabel = e.team_name ? '<span class="rank-team">' + this._escape(e.team_name) + '</span>' : '';
      const posLabel  = (type === 'player' && e.position)
        ? '<span class="rank-pos pos-' + e.position + '">' + e.position.toUpperCase() + '</span>'
        : '';
      return '<div class="ranking-item ' + (isSelected ? 'active' : '') + '" data-id="' + this._escape(e.id) + '">'
        + '<span class="rank-number rank-' + (rank <= 3 ? rank : 'normal') + '">' + rank + '</span>'
        + '<div class="rank-info"><span class="rank-name">' + this._escape(name) + '</span>'
        + '<div class="rank-meta">' + posLabel + teamLabel + '</div></div>'
        + '<span class="rank-score">' + score + '</span></div>';
    }).join('');

    // 点击 → handler
    const self = this;
    listEl.querySelectorAll('.ranking-item').forEach(item => {
      item.addEventListener('click', () => {
        const id = item.dataset.id;
        if (id && self._handlers && self._handlers.onEntityChange) self._handlers.onEntityChange(id);
      });
    });
  },

  // ============ 子模块：图例 ============

  _updateLegend(type) {
    const selfLabel = document.getElementById('lg-self');
    const avgLabel  = document.getElementById('lg-avg');
    if (selfLabel) selfLabel.textContent = type === 'player' ? '该选手' : '该队伍';
    if (avgLabel)  avgLabel.textContent  = type === 'player' ? '同位置均值' : '联赛均值';
  },

  // ============ 公共：主题/加载/错误 ============

  updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (icon) icon.textContent = theme === 'dark' ? '🌙' : '☀️';
  },

  setLoading(isLoading) {
    const overlay = document.getElementById('loading-overlay');
    if (!overlay) return;
    // 延迟 400ms 才真正显示 → 本地 JSON 几乎都在此之前完成，蒙层根本不出现。
    // 仅在确实卡顿（首次冷加载 / 慢网络）时才反馈，杜绝高频切换爆闪。
    if (isLoading) {
      if (this._loadingTimer) return; // 已在排队
      this._loadingTimer = setTimeout(() => {
        overlay.classList.add('active');
        this._loadingTimer = null;
      }, 400);
    } else {
      if (this._loadingTimer) {
        clearTimeout(this._loadingTimer);
        this._loadingTimer = null;
      }
      overlay.classList.remove('active');
    }
  },

  showError(message) {
    const toast = document.getElementById('error-toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('active');
    clearTimeout(this._errorTimer);
    this._errorTimer = setTimeout(() => toast.classList.remove('active'), 4000);
  },

  // ============ 事件绑定 ============

  bindEvents(handlers) {
    this._handlers = handlers;

    document.querySelectorAll('#seg-type button').forEach(btn => {
      btn.addEventListener('click', e => handlers.onTypeChange(e.currentTarget.dataset.type));
    });

    const seasonSel = document.getElementById('sel-season');
    if (seasonSel) seasonSel.addEventListener('change', e => handlers.onSeasonChange(e.target.value));

    const search = document.getElementById('rank-search');
    if (search) search.addEventListener('input', e => handlers.onSearchChange(e.target.value));

    const filter = document.getElementById('ranking-filter');
    if (filter) {
      filter.addEventListener('click', e => {
        const btn = e.target.closest('.rfilter-chip');
        if (!btn) return;
        const pos = btn.dataset.pos;
        if (handlers.onPosFilterChange) handlers.onPosFilterChange(pos);
      });
    }

    const back = document.getElementById('back-to-list');
    if (back) back.remove();

    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', () => handlers.onThemeToggle());

    // 图例点击 toggle 显隐
    document.querySelectorAll('.lg-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const series = btn.dataset.series;
        const next = btn.getAttribute('aria-pressed') !== 'true' ? 'true' : 'false';
        btn.setAttribute('aria-pressed', next);
        if (typeof RadarChart !== 'undefined' && RadarChart.setSeriesVisible) {
          RadarChart.setSeriesVisible(series, next === 'true');
        }
      });
    });
  },

  // ============ Utils ============

  _signNum(val, decimals) {
    decimals = decimals || 0;
    const v = val || 0;
    const num = decimals ? v.toFixed(decimals) : Math.round(v);
    return v >= 0 ? '+' + num : '' + num;
  },

  _escape(str) {
    if (str == null) return '';
    return String(str).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '"', "'": '&#39;'
    }[c]));
  },
};