"""Step 10 · L1 直透雷达：lol_db.l1_* 视图 → web/data/season_l1/

每一维 = 1~2 个 OE 一级字段的简单公式，不做加权重构/位置职责叠加。
归一化：同 (league, season, position) 百分位拉伸（复用 metrics.percentile_stretch）。
"""
import os, sys, sqlite3, json, statistics, hashlib
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "server"))
from metrics import percentile_stretch, scores  # noqa: E402
from _common import step_log, ROOT, ALLOWED_LEAGUES, ALLOWED_POSITIONS  # noqa: E402

LOL_DB = Path(os.environ.get(
    "LOL_DB", "/sdcard/第三宇宙警备站/lol_db/lol_2026.sqlite"))
OUT = ROOT / "web" / "data" / "season_l1"

DIM_LABEL = {
    "d_lane":       ("风格化压制", "线期金币差+经验差 (gd15+xpd15, sup用@10)"),
    "d_cspm":       ("可获发育", "每分钟补刀 (cspm)"),
    "d_kills":      ("交战", "局均击杀 (kills/games)"),
    "d_assists":    ("协同助攻", "局均助攻 (assists/games)"),
    "d_kp":         ("流动性", "(kills+assists)/teamkills"),
    "d_dmg_share":  ("多头DMG", "队内伤害份额 (damageshare)"),
    "d_burst":      ("瞬时处理", "每分钟伤害 (dpm)"),
    "d_economy":    ("资源转化", "局均自赚经济 (earned_gpm)"),
    "d_tanking":    ("承伤阀值", "每分钟承伤 (damagetakenperminute)"),
    "d_mitigation": ("减伤效率", "每分钟减伤 (dmg_mitigated_per_min)"),
    "d_survival":   ("心性", "1 − 局均死亡 / 联赛峰值"),
    "d_firstblood": ("主导占比", "(firstbloodkill+firstbloodassist)/games"),
    "d_jungle":     ("野区掌控", "局均野怪击杀 (monsterkills/games)"),
    "d_vision":     ("视野压制", "每分钟视野得分 (vspm)"),
}
DIM_KEYS = list(DIM_LABEL.keys())

POS_DIMS = {
    "top": ["d_lane", "d_cspm", "d_kills", "d_kp",
            "d_dmg_share", "d_tanking", "d_survival", "d_firstblood"],
    "jng": ["d_kills", "d_assists", "d_kp", "d_tanking",
            "d_survival", "d_firstblood", "d_jungle", "d_vision"],
    "mid": ["d_lane", "d_cspm", "d_kills", "d_kp",
            "d_dmg_share", "d_burst", "d_survival", "d_firstblood"],
    "bot": ["d_lane", "d_cspm", "d_kills", "d_kp",
            "d_dmg_share", "d_burst", "d_economy", "d_survival"],
    "sup": ["d_lane", "d_assists", "d_kp", "d_mitigation",
            "d_survival", "d_firstblood", "d_vision", "d_burst"],
}
TEAM_DIMS = ["d_kills", "d_assists", "d_kp", "d_burst",
             "d_economy", "d_survival", "d_firstblood", "d_vision"]


def hash_pid(pid: str) -> str:
    return "oe:player:" + hashlib.md5(pid.encode("utf-8")).hexdigest()[:32]


def hash_tid(tid: str) -> str:
    return "oe:team:" + hashlib.md5(tid.encode("utf-8")).hexdigest()[:32]


POS_CN = {"top": "上单", "jng": "打野", "mid": "中单", "bot": "下路", "sup": "辅助"}


def tag_league(code):  return {"label": code, "color": "blue"}
def tag_pos(code):     return {"label": POS_CN.get(code, code), "color": "red"}
def tag_team(name):    return {"label": name, "color": "slate"} if name else None


def stretch(value, samples):
    return percentile_stretch(value, samples, lo=15, hi=99,
                              gamma=0.6, top_full=False, small_n=4)


# ============================================================
# 1) 聚合选手每个 (league, season, position) 的局列表 + 6 维原始值
# ============================================================
def aggregate_players(con):
    """返回 dict: (season_id, pid) -> {raw_dims, games, win_rate, team_id, name...}"""
    # season 表（白名单）
    place = ",".join("?" * len(ALLOWED_LEAGUES))
    games = {g["gameid"]: g for g in con.execute(
        f"SELECT * FROM l1_game WHERE league_code IN ({place})",
        tuple(ALLOWED_LEAGUES))}
    if not games:
        return {}, {}

    def season_of(g):
        sp = (g["split"] or "Main").strip() or "Main"
        return f"{g['league_code']}-{g['year']}-{sp}".replace(" ", "_")

    gids = tuple(games.keys())
    INQ = "(" + ",".join("?" * len(gids)) + ")"
    # 选手局
    p_rows = con.execute(
        f"SELECT * FROM l1_player_stat WHERE gameid IN {INQ}", gids
    ).fetchall()
    # 队伍局：teamkills
    t_rows = con.execute(
        f"SELECT gameid, side, team_id, teamkills FROM l1_team_stat WHERE gameid IN {INQ}", gids
    ).fetchall()
    tk_idx = {(r["gameid"], r["side"]): r["teamkills"] for r in t_rows}

    # 玩家名
    pname = {r["player_id"]: r["player_name"] for r in con.execute(
        "SELECT player_id, player_name FROM players")}
    tname = {r["team_id"]:  r["team_name"]   for r in con.execute(
        "SELECT team_id,  team_name  FROM teams")}

    bucket = defaultdict(list)   # (sid, pid) -> [game-row]
    pos_map = {}                 # (sid, pid) -> position
    team_map = {}                # (sid, pid) -> team_id（最后一局的队）
    league_map = {}              # sid -> league
    for r in p_rows:
        if r["position"] not in ALLOWED_POSITIONS: continue
        if not r["player_id"]: continue
        g = games[r["gameid"]]
        sid = season_of(g)
        league_map[sid] = g["league_code"]
        tk = tk_idx.get((r["gameid"], r["side"]))
        bucket[(sid, r["player_id"])].append({
            "result":    r["result"] or 0,
            "kills":     r["kills"] or 0,
            "deaths":    r["deaths"] or 0,
            "assists":   r["assists"] or 0,
            "teamkills": tk or 0,
            "gd15":      r["golddiffat15"],
            "gd10":      r["golddiffat10"],
            "xpd15":     r["xpdiffat15"],
            "xpd10":     r["xpdiffat10"],
            "vspm":      r["vspm"] or 0,
            "dpm":       r["dpm"] or 0,
            "champion":  r["champion_name"],
            "egpm":      r["earned_gpm"] or 0,
            "dmg_share": r["damageshare"] or 0,
            "dtpm":      r["damagetakenperminute"] or 0,
            "dmpm":      r["damagemitigatedperminute"] or 0,
            "cspm":      r["cspm"] or 0,
            "monsters":  r["monsterkills"] or 0,
            "fb_k":      r["firstbloodkill"] or 0,
            "fb_a":      r["firstbloodassist"] or 0,
        })
        pos_map[(sid, r["player_id"])] = r["position"]
        team_map[(sid, r["player_id"])] = r["team_id"]

    players = {}
    for key, games_list in bucket.items():
        sid, pid = key
        pos = pos_map[key]
        n = len(games_list)
        wins = sum(g["result"] for g in games_list)
        deaths_list = [g["deaths"] for g in games_list]
        is_sup = (pos == "sup")
        # 14 维原始局均
        avg_kills    = sum(g["kills"]     for g in games_list) / n if n else 0
        avg_assists  = sum(g["assists"]   for g in games_list) / n if n else 0
        avg_deaths   = sum(deaths_list) / n if n else 0
        avg_egpm     = sum(g["egpm"]      for g in games_list) / n if n else 0
        avg_dshare   = sum(g["dmg_share"] for g in games_list) / n if n else 0
        avg_dtpm     = sum(g["dtpm"]      for g in games_list) / n if n else 0
        avg_dmpm     = sum(g["dmpm"]      for g in games_list) / n if n else 0
        avg_cspm     = sum(g["cspm"]      for g in games_list) / n if n else 0
        avg_dpm      = sum(g["dpm"]       for g in games_list) / n if n else 0
        avg_vspm     = sum(g["vspm"]      for g in games_list) / n if n else 0
        avg_monsters = sum(g["monsters"]  for g in games_list) / n if n else 0
        fb_rate      = sum(g["fb_k"] + g["fb_a"] for g in games_list) / n if n else 0
        pool         = len({g["champion"] for g in games_list if g["champion"]})

        # 参团率（按局算后取均值）
        kp_vals  = [(g["kills"]+g["assists"])/g["teamkills"] if g["teamkills"]>0 else 0
                    for g in games_list]
        avg_kp   = sum(kp_vals) / n if n else 0

        # 对线能力：gd + xpd（辅助用@10，其它用@15）
        gd_field, xpd_field = ("gd10", "xpd10") if is_sup else ("gd15", "xpd15")
        lane_vals = [(g[gd_field] or 0) + (g[xpd_field] or 0)
                     for g in games_list
                     if g[gd_field] is not None or g[xpd_field] is not None]
        avg_lane  = sum(lane_vals) / len(lane_vals) if lane_vals else 0

        # 兼容旧字段（详情面板二级指标仍要展示）
        gd_vals  = [g[gd_field] for g in games_list if g[gd_field] is not None]
        dpm_vals = [g["dpm"]  for g in games_list]
        vspm_vals= [g["vspm"] for g in games_list]

        players[key] = {
            "player_id": pid,
            "season_id": sid,
            "league":    league_map[sid],
            "position":  pos,
            "team_id":   team_map[key],
            "name":      pname.get(pid, pid),
            "team_name": tname.get(team_map[key], team_map[key]),
            "games":     n,
            "wins":      wins,
            "losses":    n - wins,
            "win_rate":  wins / n if n else 0,
            # 给前端「二级指标详情」用的真实均值
            "raw_metrics": {
                "kp_pct":        (sum(kp_vals)/n if n else 0),       # 0..1
                "kda":           (sum(g["kills"]+g["assists"] for g in games_list)
                                  / max(1, sum(g["deaths"] for g in games_list))),
                "avg_dpm":       sum(dpm_vals)/n if n else 0,
                "avg_vspm":      sum(vspm_vals)/n if n else 0,
                "avg_gd":        sum(gd_vals)/len(gd_vals) if gd_vals else 0,
                "gd_field":      gd_field,
                "champion_pool": pool,
            },
            # 14 维 raw（生存能力为反向：deaths 越少越好，存负值）
            "raw": {
                "d_lane":       avg_lane,
                "d_cspm":       avg_cspm,
                "d_kills":      avg_kills,
                "d_assists":    avg_assists,
                "d_kp":         avg_kp,
                "d_dmg_share":  avg_dshare,
                "d_burst":      avg_dpm,
                "d_economy":    avg_egpm,
                "d_tanking":    avg_dtpm,
                "d_mitigation": avg_dmpm,
                "d_survival":   -avg_deaths,
                "d_firstblood": fb_rate,
                "d_jungle":     avg_monsters,
                "d_vision":     avg_vspm,
            },
        }
    return players, league_map


def filter_low_games(players):
    """剔除场次过少的"水花"选手。
    阈值 = max(MIN_ABS, season_median × MIN_REL_RATIO)
        - MIN_ABS=5：绝对下限
        - MIN_REL_RATIO=0.30：相对下限（赛季中位数的 30%）
    按 (league, season) 自适应，避免大/小赛季"一刀切"。
    """
    MIN_ABS, MIN_REL_RATIO = 5, 0.30
    by_ls = defaultdict(list)
    for key, p in players.items():
        by_ls[(p["league"], p["season_id"])].append(key)

    removed = 0
    for ls_key, keys in by_ls.items():
        games_arr = sorted(players[k]["games"] for k in keys)
        n = len(games_arr)
        if n == 0: continue
        median = games_arr[n // 2]
        thr = max(MIN_ABS, int(median * MIN_REL_RATIO))
        for k in keys:
            if players[k]["games"] < thr:
                del players[k]
                removed += 1
        print(f"  filter[{ls_key[0]}/{ls_key[1]}] n={n} med={median} thr={thr} "
              f"→ kept={sum(1 for k in keys if k in players)}")
    print(f"  total removed: {removed}")
    return players


# ============================================================
# 2) 归一化：同 (league, season, position) 百分位拉伸
# ============================================================
def _trimmed_weighted_mean(items, dim, trim_q=0.10):
    """修剪 + sqrt(games) 加权均值（在 raw 空间）。
    - 按 raw 值排序，去掉两端各 trim_q 比例（默认 10%）
    - 剩余样本以 sqrt(games) 为权重做加权均值
    - 返回原始空间的"典型水平"值
    """
    import math
    # 抽取 (raw_value, weight) 对
    pairs = [(p["raw"][dim], math.sqrt(max(p["games"], 1))) for p in items]
    pairs.sort(key=lambda x: x[0])
    n = len(pairs)
    if n == 0: return 0.0
    if n <= 4:  # 太少不修剪
        kept = pairs
    else:
        k = max(1, int(n * trim_q))
        kept = pairs[k:n - k] or pairs
    wsum = sum(w for _, w in kept) or 1.0
    return sum(v * w for v, w in kept) / wsum


def normalize_players(players):
    # 按 (league, season, position) 分组做选手归一化
    groups = defaultdict(list)
    # 同时按 (league, season) 分组用于"位置职责均值"
    league_groups = defaultdict(list)
    for key, p in players.items():
        groups[(p["league"], p["season_id"], p["position"])].append(p)
        league_groups[(p["league"], p["season_id"])].append(p)

    # 第一步：选手 value 用本位置组归一化
    for items in groups.values():
        for dim in DIM_KEYS:
            samples = [p["raw"][dim] for p in items]
            for p in items:
                p.setdefault("dim", {})[dim] = stretch(p["raw"][dim], samples)

    # 第二步：均值线 = 本位置 raw 加权均值，放进"全联赛（跨位置）" 分布求 stretch
    # 这样辅助的击杀均值 → 全联赛击杀分布中很低 → 雷达均值线呈现位置职责形状
    for items in groups.values():
        if not items: continue
        league_pool = league_groups[(items[0]["league"], items[0]["season_id"])]
        group_avg = {}
        for dim in DIM_KEYS:
            wmean_raw = _trimmed_weighted_mean(items, dim, trim_q=0.10)
            cross_samples = [p["raw"][dim] for p in league_pool]
            group_avg[dim] = stretch(wmean_raw, cross_samples)
        for p in items:
            p["group_avg"] = group_avg

    # 第三步：玩家分 + 排名（按位置 8 维）
    for items in groups.values():
        n = len(items)
        if not items: continue
        pos_keys = POS_DIMS.get(items[0]["position"], DIM_KEYS[:8])
        for p in items:
            d_vals = [p["dim"][k] for k in pos_keys]
            ps, sr = scores(d_vals, p["win_rate"])
            p["player_score"], p["season_rating"] = ps, sr
        ordered = sorted(items, key=lambda x: x["player_score"], reverse=True)
        for i, p in enumerate(ordered, 1):
            p["rank"], p["total"] = i, n

    # 第四步：跨位置 mean 校准（仅平移，不缩放）
    # —— 仅对齐每个位置组到全局均值，消除"辅助维度池系统性偏高"等位置间不公平；
    #    保留各位置内部分布的离散度，让真实的"面积差异"能透到全局排名上。
    import math
    by_ls = defaultdict(list)
    for p in players.values():
        by_ls[(p["league"], p["season_id"])].append(p)

    def _mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    for ls_pool in by_ls.values():
        if len(ls_pool) < 5: continue
        for field in ("player_score", "season_rating"):
            g_vals = [p[field] for p in ls_pool]
            gm = _mean(g_vals)
            by_pos = defaultdict(list)
            for p in ls_pool:
                by_pos[p["position"]].append(p)
            for pos_items in by_pos.values():
                if len(pos_items) < 3:           # 样本太少不校准
                    continue
                pm = _mean([p[field] for p in pos_items])
                shift = gm - pm
                for p in pos_items:
                    p[field] = round(p[field] + shift, 2)
        # 校准后重新计算每个位置组的排名（player_score 排名仍按位置内）
        by_pos2 = defaultdict(list)
        for p in ls_pool:
            by_pos2[p["position"]].append(p)
        for pos_items in by_pos2.values():
            ordered = sorted(pos_items, key=lambda x: x["player_score"], reverse=True)
            n = len(ordered)
            for i, p in enumerate(ordered, 1):
                p["rank"], p["total"] = i, n


# ============================================================
# 3) 队伍聚合
# ============================================================
def aggregate_teams(con, players):
    place = ",".join("?" * len(ALLOWED_LEAGUES))
    games = {g["gameid"]: g for g in con.execute(
        f"SELECT * FROM l1_game WHERE league_code IN ({place})",
        tuple(ALLOWED_LEAGUES))}
    if not games: return {}

    def season_of(g):
        sp = (g["split"] or "Main").strip() or "Main"
        return f"{g['league_code']}-{g['year']}-{sp}".replace(" ", "_")

    gids = tuple(games.keys())
    INQ = "(" + ",".join("?" * len(gids)) + ")"
    t_rows = con.execute(
        f"SELECT gameid, side, team_id, result, gspd, gpr, team_kpm "
        f"FROM l1_team_stat WHERE gameid IN {INQ}", gids).fetchall()
    tname = {r["team_id"]: r["team_name"] for r in con.execute(
        "SELECT team_id, team_name FROM teams")}

    bucket = defaultdict(list)
    league_map = {}
    for r in t_rows:
        g = games[r["gameid"]]
        sid = season_of(g)
        league_map[sid] = g["league_code"]
        bucket[(sid, r["team_id"])].append(r)

    player_by_team = defaultdict(list)
    for p in players.values():
        player_by_team[(p["season_id"], p["team_id"])].append(p["dim"])

    teams = {}
    def lin(v, lo, hi):
        t = (v - lo) / (hi - lo)
        return max(0, min(100, round(t * 100)))

    for key, rows in bucket.items():
        sid, tid = key
        n = len(rows)
        wins = sum(r["result"] or 0 for r in rows)
        gspd = sum((r["gspd"] or 0) for r in rows) / n if n else 0
        gpr  = sum((r["gpr"]  or 0) for r in rows) / n if n else 0
        ckpm = sum((r["team_kpm"] or 0) for r in rows) / n if n else 0
        pdims = player_by_team.get(key, [])
        avg_dim = {k: (sum(d[k] for d in pdims)/len(pdims) if pdims else 50)
                   for k in DIM_KEYS}
        teams[key] = {
            "team_id": tid, "season_id": sid, "league": league_map[sid],
            "name": tname.get(tid, tid),
            "games": n, "wins": wins, "win_rate": wins/n if n else 0,
            "raw_gspd": round(gspd,4), "raw_gpr": round(gpr,4), "raw_ckpm": round(ckpm,4),
            # 队伍八维 = 五选手维度均值（直接取整）
            "dim": {k: round(avg_dim[k]) for k in DIM_KEYS},
        }

    grp = defaultdict(list)
    for t in teams.values():
        grp[(t["league"], t["season_id"])].append(t)
    for items in grp.values():
        n = len(items)
        # 组内"真实世界均值"：dim 空间（0-100）→ 修剪 10/90 + sqrt(games) 加权
        import math
        group_avg = {}
        for dim in DIM_KEYS:
            pairs = [(t["dim"][dim], math.sqrt(max(t["games"], 1))) for t in items]
            pairs.sort(key=lambda x: x[0])
            if len(pairs) <= 4:
                kept = pairs
            else:
                k = max(1, int(len(pairs) * 0.10))
                kept = pairs[k:len(pairs) - k] or pairs
            wsum = sum(w for _, w in kept) or 1.0
            group_avg[dim] = round(sum(v * w for v, w in kept) / wsum)
        for t in items:
            t["group_avg"] = group_avg
            d_vals = [t["dim"][k] for k in TEAM_DIMS]
            ps, sr = scores(d_vals, t["win_rate"])
            t["player_score"], t["season_rating"] = ps, sr
        ordered = sorted(items, key=lambda x: x["player_score"], reverse=True)
        for i, t in enumerate(ordered, 1):
            t["rank"], t["total"] = i, n
    return teams


# ============================================================
# 4) build per-subject JSON
# ============================================================
def build_player_json(p):
    keys = POS_DIMS.get(p["position"], DIM_KEYS[:8])
    dims = []
    for k in keys:
        label, formula = DIM_LABEL[k]
        dims.append({
            "key": k, "label": label, "fields": formula,
            "value": p["dim"][k], "avg": p["group_avg"][k],
            "raw": round(p["raw"][k], 2),
            "rank": p["rank"], "total": p["total"],
        })
    return {
        "type": "player",
        "id":   hash_pid(p["player_id"]),
        "name": p["name"],
        "season_id": p["season_id"],
        "tags": [t for t in [tag_league(p["league"]),
                             tag_pos(p["position"]),
                             tag_team(p["team_name"])] if t],
        "top_stats": {
            "text_score":    {"value": p["player_score"],  "rank": p["rank"],
                              "total": p["total"], "subtitle": "Player Score"},
            "season_rating": {"value": p["season_rating"], "rank": p["rank"],
                              "total": p["total"], "subtitle": "Season Rating"},
        },
        "dimensions":   dims,
        "formula_note": {
            "note": "L1 直透：每维由 1~2 个 OE 原始字段构造，同 (联赛, 赛季, 位置) 内做百分位拉伸。",
            "items": [{"label": v[0], "fields": v[1], "formula": v[1]}
                      for k, v in DIM_LABEL.items()],
        },
        "raw": {
            "games":         p["games"],
            "wins":          p["wins"],
            "losses":        p["losses"],
            "win_rate":      round(p["win_rate"], 4),
            "team":          p["team_name"],
            "kp":            round(p["raw_metrics"]["kp_pct"] * 100, 1),
            "kda":           round(p["raw_metrics"]["kda"], 2),
            "avg_dpm":       round(p["raw_metrics"]["avg_dpm"], 1),
            "avg_vspm":      round(p["raw_metrics"]["avg_vspm"], 2),
            "avg_gd15":      round(p["raw_metrics"]["avg_gd"], 0),
            "gd_field":      p["raw_metrics"]["gd_field"],
            "champion_pool": p["raw_metrics"]["champion_pool"],
        },
    }


def build_team_json(t):
    dims = []
    for k in TEAM_DIMS:
        label, formula = DIM_LABEL[k]
        dims.append({
            "key": k, "label": label, "fields": formula,
            "value": t["dim"][k], "avg": t["group_avg"][k],
            "rank": t["rank"], "total": t["total"],
        })
    tid_hash = hash_tid(t["team_id"])
    return {
        "type": "team",
        "id":   tid_hash,
        "name": t["name"],
        "season_id": t["season_id"],
        "tags": [tag_league(t["league"])],
        "top_stats": {
            "text_score":    {"value": t["player_score"],  "rank": t["rank"],
                              "total": t["total"], "subtitle": "Team Score"},
            "season_rating": {"value": t["season_rating"], "rank": t["rank"],
                              "total": t["total"], "subtitle": "Season Rating"},
        },
        "dimensions":   dims,
        "formula_note": {
            "note": "L1 直透（队伍）：5 选手维度均值 + GSPD / GPR / TeamKPM 直读 + 胜率结果系数。",
            "items": [{"label": v[0], "fields": v[1], "formula": v[1]}
                      for k, v in DIM_LABEL.items()],
        },
        "raw": {
            "games":  t["games"],
            "wins":   t["wins"],
            "losses": t["games"] - t["wins"],
            "win_rate": round(t["win_rate"], 4),
            "avg_gspd": t["raw_gspd"],
            "avg_gpr":  t["raw_gpr"],
            "avg_ckpm": t["raw_ckpm"],
        },
    }


# ============================================================
# 5) main
# ============================================================
def main():
    with step_log("10_export_l1_radar") as st:
        if not LOL_DB.exists():
            raise FileNotFoundError(LOL_DB)
        OUT.mkdir(parents=True, exist_ok=True)
        for sub in OUT.glob("*"):
            if sub.is_dir():
                for f in sub.rglob("*"):
                    if f.is_file(): f.unlink()
                for d in sorted(sub.rglob("*"), reverse=True):
                    if d.is_dir(): d.rmdir()
                sub.rmdir()
            else:
                sub.unlink()

        con = sqlite3.connect(LOL_DB)
        con.row_factory = sqlite3.Row

        players, _ = aggregate_players(con)
        filter_low_games(players)
        normalize_players(players)
        teams = aggregate_teams(con, players)
        con.close()

        # 按 season 分桶
        seasons = defaultdict(lambda: {"player": [], "team": []})
        for p in players.values():
            seasons[p["season_id"]]["player"].append(p)
        for t in teams.values():
            seasons[t["season_id"]]["team"].append(t)

        n_p = n_t = 0
        seasons_index = []
        for sid in sorted(seasons.keys()):
            bag = seasons[sid]
            sdir = OUT / sid
            (sdir / "player").mkdir(parents=True, exist_ok=True)
            (sdir / "team").mkdir(parents=True, exist_ok=True)
            list_obj = {"season_id": sid, "players": [], "teams": []}

            for p in sorted(bag["player"], key=lambda x: -x["player_score"]):
                obj = build_player_json(p)
                safe = obj['id'].replace(':', '_').replace('/', '_')
                (sdir / "player" / f"{safe}.json").write_text(
                    json.dumps(obj, ensure_ascii=False, separators=(",",":")),
                    encoding="utf-8")
                list_obj["players"].append({
                    "id": obj["id"], "name": obj["name"],
                    "position":     p["position"],
                    "team_id":      hash_tid(p["team_id"]) if p["team_id"] else None,
                    "team_name":    p["team_name"],
                    "text_score":   p["player_score"],
                    "season_rating":p["season_rating"],
                    "r_position":   p["rank"],
                    "total_in_pos": p["total"],
                })
                n_p += 1

            for t in sorted(bag["team"], key=lambda x: x["rank"]):
                obj = build_team_json(t)
                safe = obj['id'].replace(':', '_').replace('/', '_')
                (sdir / "team" / f"{safe}.json").write_text(
                    json.dumps(obj, ensure_ascii=False, separators=(",",":")),
                    encoding="utf-8")
                list_obj["teams"].append({
                    "id": obj["id"], "name": obj["name"],
                    "text_score":    t["player_score"],
                    "season_rating": t["season_rating"],
                    "rank": t["rank"], "total": t["total"],
                })
                n_t += 1

            (sdir / "list.json").write_text(
                json.dumps(list_obj, ensure_ascii=False, separators=(",",":")),
                encoding="utf-8")
            seasons_index.append({
                "id": sid,
                "player_count": len(list_obj["players"]),
                "team_count":   len(list_obj["teams"]),
            })

        (OUT / "seasons.json").write_text(
            json.dumps(seasons_index, ensure_ascii=False, separators=(",",":")),
            encoding="utf-8")
        print(f"L1 雷达导出：{len(seasons_index)} 赛季 / {n_p} 选手 / {n_t} 队伍 → {OUT}")
        st["rows_out"] = n_p + n_t


if __name__ == "__main__":
    main()
