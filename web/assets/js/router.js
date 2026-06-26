/**
 * Hash 路由
 * 形式：#/p/{seasonId}/{entityId}    选手
 *      #/t/{seasonId}/{entityId}    队伍
 *      #/p/{seasonId}               只选了赛季，未选实体
 *      #/p                          初始（未选赛季）
 * 设计目标：
 * - URL 是唯一真源，刷新/分享/前进后退 = 还原状态
 * - 业务侧只调用 Router.navigate({...})，不直接操作 location
 */
const Router = {
  /** @type {Function|null} */
  _onChange: null,

  /** 解析当前 hash → {type, seasonId, entityId} */
  parse() {
    const raw = (location.hash || '').replace(/^#\/?/, '');
    const [scope, seasonId, entityId] = raw.split('/').map(s => s ? decodeURIComponent(s) : '');
    const type = scope === 't' ? 'team' : 'player';
    return {
      type,
      seasonId: seasonId || null,
      entityId: entityId || null,
    };
  },

  /**
   * 写入新路由
   * @param {{type?: 'player'|'team', seasonId?: string|null, entityId?: string|null, replace?: boolean}} opts
   */
  navigate(opts = {}) {
    const cur = this.parse();
    const next = { ...cur, ...opts };
    const scope = next.type === 'team' ? 't' : 'p';

    let hash = `#/${scope}`;
    if (next.seasonId) {
      hash += `/${encodeURIComponent(next.seasonId)}`;
      if (next.entityId) hash += `/${encodeURIComponent(next.entityId)}`;
    }

    if (location.hash === hash) {
      // 主动派发，确保订阅者也能感知（例如初始化时）
      if (this._onChange) this._onChange(this.parse());
      return;
    }

    if (opts.replace) {
      const url = location.pathname + location.search + hash;
      history.replaceState(null, '', url);
      if (this._onChange) this._onChange(this.parse());
    } else {
      location.hash = hash;
    }
  },

  /**
   * 静默替换 URL（不触发 _onChange，避免重入业务流程）
   * 用于 syncRoute 内部决定默认赛季/默认实体后回写 URL。
   */
  replaceSilent(opts = {}) {
    const cur = this.parse();
    const next = { ...cur, ...opts };
    const scope = next.type === 'team' ? 't' : 'p';
    let hash = `#/${scope}`;
    if (next.seasonId) {
      hash += `/${encodeURIComponent(next.seasonId)}`;
      if (next.entityId) hash += `/${encodeURIComponent(next.entityId)}`;
    }
    if (location.hash === hash) return;
    const url = location.pathname + location.search + hash;
    history.replaceState(null, '', url);
    // history.replaceState 不会触发 hashchange，所以这里也不调 _onChange
  },

  /** 启动监听 */
  start(onChange) {
    this._onChange = onChange;
    window.addEventListener('hashchange', () => {
      if (this._onChange) this._onChange(this.parse());
    });
  },
};