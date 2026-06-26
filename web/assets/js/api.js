/**
 * API 接口层
 * - 自动检测：静态 JSON 模式 / Flask API 模式
 * - 三级内存缓存（seasons / list / entity），避免来回切换重复网络请求
 * - 同一资源的并发请求会被去重（single-flight）
 * - 404 区分为「资源不存在」而不是错误（让上层渲染空态）
 */
const API = {
  /** 数据源根目录：默认 L1 直透；如需切回旧重建模型，可在 localStorage 设 radar_source='reborn' */
  get _root() {
    try {
      return localStorage.getItem('radar_source') === 'reborn' ? 'season' : 'season_l1';
    } catch { return 'season_l1'; }
  },

  /** @type {boolean|null} */
  _isStatic: null,

  /** 内存缓存（同一会话内复用） */
  _cache: {
    seasons: null,            // Array | null
    list:    new Map(),       // key: seasonId  → {players, teams}
    entity:  new Map(),       // key: `${seasonId}|${type}|${entityId}` → data
  },

  /** 单飞表：同一资源同时只有一个 in-flight 请求 */
  _inflight: new Map(),

  /** 检测运行模式（静态 vs Flask） */
  async init() {
    if (this._isStatic !== null) return;
    try {
      const res = await fetch('/healthz', { signal: AbortSignal.timeout(3000) });
      this._isStatic = !res.ok;
    } catch {
      this._isStatic = true;
    }
  },

  /** 获取所有赛季列表（永久缓存） */
  async getSeasons() {
    await this.init();
    if (this._cache.seasons) return this._cache.seasons;

    const url = this._isStatic ? './data/seasons.json' : '/api/seasons';
    const data = await this._dedupedJSON('seasons', url, { allow404: true });
    this._cache.seasons = Array.isArray(data) ? data : [];
    return this._cache.seasons;
  },

  /**
   * 获取赛季内的选手/队伍列表
   * @param {string} seasonId
   * @param {'player'|'team'} type
   * @returns {Promise<Array>}
   */
  async getEntities(seasonId, type = 'player') {
    if (!seasonId) return [];
    await this.init();

    const cached = this._cache.list.get(seasonId);
    if (cached) return type === 'player' ? cached.players : cached.teams;

    let payload;
    if (this._isStatic) {
      const safeId = this._safePath(seasonId);
      payload = await this._dedupedJSON(
        `list:${seasonId}`,
        `./data/${this._root}/${safeId}/list.json`,
        { allow404: true }
      );
    } else {
      const [players, teams] = await Promise.all([
        this._dedupedJSON(`list-p:${seasonId}`, `/api/players?season_id=${encodeURIComponent(seasonId)}`),
        this._dedupedJSON(`list-t:${seasonId}`, `/api/teams?season_id=${encodeURIComponent(seasonId)}`),
      ]);
      payload = { players, teams };
    }

    payload = payload || { players: [], teams: [] };
    this._cache.list.set(seasonId, payload);
    return type === 'player' ? (payload.players || []) : (payload.teams || []);
  },

  /**
   * 获取选手/队伍的完整雷达数据
   * @returns {Promise<Object|null>} 不存在时返回 null
   */
  async getEntityData(seasonId, type, entityId) {
    if (!seasonId || !entityId) return null;
    await this.init();

    const key = `${seasonId}|${type}|${entityId}`;
    if (this._cache.entity.has(key)) return this._cache.entity.get(key);

    let data;
    if (this._isStatic) {
      const safeSeasonId = this._safePath(seasonId);
      const safeEntityId = this._safePath(entityId);
      data = await this._dedupedJSON(
        key,
        `./data/${this._root}/${safeSeasonId}/${type}/${safeEntityId}.json`,
        { allow404: true }
      );
    } else {
      const endpoint = type === 'player' ? '/api/player' : '/api/team';
      data = await this._dedupedJSON(
        key,
        `${endpoint}/${encodeURIComponent(entityId)}?season_id=${encodeURIComponent(seasonId)}`
      );
    }

    this._cache.entity.set(key, data || null);
    return data || null;
  },

  /** 清空缓存（开发/手动刷新用） */
  clearCache() {
    this._cache.seasons = null;
    this._cache.list.clear();
    this._cache.entity.clear();
  },

  /** 带去重的 JSON 请求 */
  async _dedupedJSON(key, url, opts = {}) {
    if (this._inflight.has(key)) return this._inflight.get(key);
    const p = this._fetchJSON(url, opts).finally(() => this._inflight.delete(key));
    this._inflight.set(key, p);
    return p;
  },

  /** 通用 JSON 请求；404+allow404 → 返回 null */
  async _fetchJSON(url, { allow404 = false } = {}) {
    const res = await fetch(url, { cache: 'no-cache' });
    if (res.status === 404 && allow404) return null;
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`API ${res.status}: ${text || res.statusText}`);
    }
    return res.json();
  },

  /** 路径安全化：替换 OE id 中的 ':' 等字符 */
  _safePath(id) {
    return id.replace(/[\/\\:]/g, '_');
  },
};