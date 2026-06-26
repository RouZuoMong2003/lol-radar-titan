/**
 * 应用状态管理 — 单一数据源 + 发布-订阅
 *
 * viewState 三态机（驱动 UI 顶层骨架切换）：
 *   - 'empty-seasons'   : 没有任何赛季数据（首次启动 / 数据全清）
 *   - 'pick-entity'     : 已选赛季、未选实体 → 显示榜单/搜索
 *   - 'detail'          : 已选赛季 + 实体 → 显示雷达 + 详情
 *
 * 任何分支态由派生 getter 计算，不在 set() 里写副作用，避免 UI 漂移。
 */
const AppState = {
  // ───── 选择态（与 URL 路由对齐） ─────
  type: 'player',      // 'player' | 'team'
  seasonId: null,
  entityId: null,

  // ───── 数据缓存 ─────
  seasons: [],
  entities: [],
  currentData: null,

  // ───── UI 态 ─────
  isLoading: false,
  error: null,
  notFound: false,     // 当前选中实体在数据集中找不到时
  theme: 'light',      // 与 index.html data-theme 默认一致；用户切换后写入 localStorage
  rankQuery: '',       // 排行榜搜索关键字
  posFilter: 'all',    // 'all' | 'top' | 'jng' | 'mid' | 'bot' | 'sup'（仅在 player 视图生效）

  // ───── 订阅器 ─────
  _subscribers: [],

  subscribe(cb) {
    this._subscribers.push(cb);
    return () => { this._subscribers = this._subscribers.filter(x => x !== cb); };
  },

  _notify() {
    for (const cb of this._subscribers) {
      try { cb(this); } catch (e) { console.error('[Store]', e); }
    }
  },

  /** 批量更新 + 通知 */
  set(updates) {
    Object.assign(this, updates);
    this._notify();
  },

  /** 静默更新，不触发订阅者；用于原子化流程内累积 patch，结束时再 set() 一次 */
  setSilent(updates) {
    Object.assign(this, updates);
  },

  /** 派生：当前应该展示哪种视图 */
  get viewState() {
    if (!this.seasons || this.seasons.length === 0) return 'empty-seasons';
    if (!this.seasonId || !this.entityId || !this.currentData) return 'pick-entity';
    return 'detail';
  },

  /** 主题 */
  toggleTheme() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', this.theme);
    try { localStorage.setItem('lol-radar-theme', this.theme); } catch {}
    this._notify();
  },

  restoreTheme() {
    const saved = localStorage.getItem('lol-radar-theme');
    if (saved) {
      this.theme = saved;
      document.documentElement.setAttribute('data-theme', saved);
    }
  },

  /** 提取雷达图渲染数据 */
  getRadarData() {
    if (!this.currentData?.dimensions) return null;
    return {
      dimensions: this.currentData.dimensions,
      playerScore: this.currentData.top_stats?.text_score,
      seasonRating: this.currentData.top_stats?.season_rating,
      meta: this.currentData.raw,
      formulaNote: this.currentData.formula_note,
    };
  },
};