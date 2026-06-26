/**
 * LoL Radar · 应用入口
 *
 * 数据流（严格单向）：
 *   UI 事件 → Router.navigate() → hashchange → syncRoute() → AppState.set() → render()
 *
 * 这样所有状态变化都经过 URL，刷新 / 前进后退 / 分享 = 状态精确还原。
 */
(function () {
  'use strict';

  // ───── 路由 → 状态同步 ─────

  /** 当 URL 变化时调用 */
  /**
   * 原子化路由同步：
   *   - 所有 fetch 结果先累积到本地 patch
   *   - URL 自动回填用 replaceSilent（不重入 syncRoute）
   *   - 全部就绪后只 set() 一次 → render() 只跑一次 → 杜绝中间态爆闪
   * 并发保护：如果上一次 syncRoute 还没结束就有新路由进来，旧的会被 _routeSeq 作废。
   */
  let _routeSeq = 0;

  async function syncRoute(route) {
    const seq = ++_routeSeq;
    const stale = () => seq !== _routeSeq;

    const prev = { type: AppState.type, seasonId: AppState.seasonId, entityId: AppState.entityId };
    const typeChanged   = prev.type !== route.type;
    const seasonChanged = prev.seasonId !== route.seasonId;
    const entityChanged = prev.entityId !== route.entityId;

    // 本次流程要写入的累积 patch（最后统一 set）
    const patch = {
      type: route.type,
      seasonId: route.seasonId,
      entityId: route.entityId,
      error: null,
      notFound: false,
      isLoading: false,
      rankQuery: (typeChanged || seasonChanged) ? '' : AppState.rankQuery,
      posFilter: (typeChanged || seasonChanged) ? 'all' : AppState.posFilter,
    };

    try {
      // ── 1. 赛季列表（仅首次） ──
      let seasons = AppState.seasons;
      if (seasons.length === 0) {
        UI.setLoading(true);
        seasons = await API.getSeasons();
        if (stale()) return;
        patch.seasons = seasons;
        if (seasons.length === 0) {
          patch.entities = [];
          patch.currentData = null;
          AppState.set(patch);
          UI.setLoading(false);
          return;
        }
      }

      // ── 2. 没选赛季 → 锁定最新；URL 静默回填后继续在本次流程内推进 ──
      let seasonId = route.seasonId;
      if (!seasonId) {
        const latest = seasons.slice().sort((a, b) => (b.id > a.id ? 1 : -1))[0];
        if (!latest) {
          patch.entities = [];
          patch.currentData = null;
          AppState.set(patch);
          UI.setLoading(false);
          return;
        }
        seasonId = latest.id;
        patch.seasonId = seasonId;
        Router.replaceSilent({ seasonId, entityId: null });
      }

      // ── 3. 列表加载（赛季/类型变化或缓存空） ──
      let entities = AppState.entities;
      const listKey = `${route.type}|${seasonId}`;
      const listMissing = typeChanged || seasonChanged || entities.length === 0
                       || AppState._lastListKey !== listKey;
      if (listMissing) {
        UI.setLoading(true);
        entities = await API.getEntities(seasonId, route.type);
        if (stale()) return;
        patch.entities = entities;
        patch._lastListKey = listKey;
      }

      // ── 4. 没选实体 → 自动选列表首位 ──
      let entityId = route.entityId;
      if (!entityId) {
        const first = entities && entities[0];
        if (!first) {
          patch.currentData = null;
          AppState.set(patch);
          UI.setLoading(false);
          return;
        }
        entityId = first.id;
        patch.entityId = entityId;
        Router.replaceSilent({ entityId });
      }

      // ── 5. 详情加载 ──
      const cacheKey = `${seasonId}|${route.type}|${entityId}`;
      const needFetchEntity = entityChanged || typeChanged || seasonChanged
                            || !AppState.currentData
                            || AppState._lastEntityKey !== cacheKey;
      if (needFetchEntity) {
        const data = await API.getEntityData(seasonId, route.type, entityId);
        if (stale()) return;
        if (!data) {
          // 当前 entityId 在新数据集中已不存在 → fallback 到首位
          const first = entities && entities[0];
          if (first && first.id !== entityId) {
            entityId = first.id;
            patch.entityId = entityId;
            Router.replaceSilent({ entityId });
            const data2 = await API.getEntityData(seasonId, route.type, entityId);
            if (stale()) return;
            if (!data2) {
              patch.currentData = null;
              patch.notFound = true;
              AppState.set(patch);
              UI.setLoading(false);
              return;
            }
            patch.currentData = data2;
            patch._lastEntityKey = `${seasonId}|${route.type}|${entityId}`;
          } else {
            patch.currentData = null;
            patch.notFound = true;
            AppState.set(patch);
            UI.setLoading(false);
            return;
          }
        } else {
          patch.currentData = data;
          patch._lastEntityKey = cacheKey;
        }
      }

      // ── 6. 原子提交：唯一一次 render ──
      AppState.set(patch);
      UI.setLoading(false);
    } catch (err) {
      if (stale()) return;
      console.error('[App]', err);
      patch.error = err.message;
      patch.currentData = null;
      AppState.set(patch);
      UI.setLoading(false);
      UI.showError('加载失败：' + (err.message || '未知错误'));
    }
  }

  // ───── 渲染（响应 AppState） ─────

  function render() {
    UI.setLoading(AppState.isLoading);
    UI.updateThemeIcon(AppState.theme);
    UI.setActiveTab(AppState.type);
    UI.renderSeasons(AppState.seasons, AppState.seasonId);

    UI.renderView(AppState.viewState, {
      type: AppState.type,
      seasonId: AppState.seasonId,
      seasons: AppState.seasons,
      entities: AppState.entities,
      entityId: AppState.entityId,
      currentData: AppState.currentData,
      notFound: AppState.notFound,
      rankQuery: AppState.rankQuery,
      posFilter: AppState.posFilter,
    });

    if (AppState.viewState === 'detail' && AppState.currentData?.dimensions) {
      RadarChart.update(AppState.currentData.dimensions, AppState.type);
    } else {
      RadarChart.clear();
    }
  }

  // ───── 事件 Handler（只调 Router） ─────

  const handlers = {
    onTypeChange(type) {
      // 切换类型：清空 entityId（不同类型 id 不通用，syncRoute 会自动锁第一个）
      Router.navigate({ type, entityId: null });
    },
    onSeasonChange(seasonId) {
      // 切换赛季：清空 entityId，syncRoute 会自动锁第一个
      Router.navigate({ seasonId: seasonId || null, entityId: null });
    },
    onEntityChange(entityId) {
      Router.navigate({ entityId });
    },
    onSearchChange(q) {
      AppState.set({ rankQuery: q || '' });
    },
    onPosFilterChange(pos) {
      const next = (pos === 'all' || ['top','jng','mid','bot','sup'].includes(pos)) ? pos : 'all';
      AppState.set({ posFilter: next });
    },
    onThemeToggle() {
      AppState.toggleTheme();
    },
    onRetry() {
      API.clearCache();
      AppState.set({ seasons: [], entities: [], currentData: null });
      syncRoute(Router.parse());
    },
  };

  // ───── 启动 ─────

  document.addEventListener('DOMContentLoaded', () => {
    AppState.restoreTheme();
    AppState.subscribe(render);
    UI.bindEvents(handlers);
    RadarChart.init('radar', 'radar-fx');

    // 启动路由：监听 + 立刻 dispatch 一次
    Router.start(route => syncRoute(route));
    syncRoute(Router.parse());
  });
})();