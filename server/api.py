"""REST API · 契约见 docs/SPEC.md §3

ID 兼容层：DB 存原始 ID（31 字符 md5[:31]），静态导出做了二次 md5（32 字符）。
为让 Flask 模式与 Wasmer/GitHub Pages 静态部署的 list.json 完全兼容：
  · 入口：接受 raw / hashed 两种 ID
  · 出口：统一输出 hashed ID
"""
import hashlib
import sqlite3
from pathlib import Path
from flask import Blueprint, jsonify, request, g

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "radar.db"
api = Blueprint("api", __name__, url_prefix="/api")

# 维度标签映射（唯一定义，导出给 08_export_static.py 使用）
DIM_LABELS = {
    "d_teamfight":   "团战决策",
    "d_laning":      "线上压制",
    "d_macro":       "长线运营",
    "d_mechanics":   "操作上限",
    "d_consistency": "心态稳定",
    "d_meta_adapt":  "版本适应",
}

# 维度 key 白名单（防止 SQL 注入）
_VALID_DIM_KEYS = frozenset(DIM_LABELS.keys())

POSITION_LABELS = {
    "top": "上单", "jng": "打野", "mid": "中单",
    "bot": "下路", "sup": "辅助", "team": "队伍",
}


# --- DB 连接管理（请求级生命周期） ---

def get_db():
    """获取当前请求的 DB 连接（懒初始化）"""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@api.teardown_app_request
def close_db(exc):
    """请求结束时关闭连接"""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- ID 兼容层（与 scripts/10_export_l1_radar.py 中的 hash 函数等价） ---

def _hash_pid(raw_id: str) -> str:
    return "oe:player:" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:32]


def _hash_tid(raw_id: str) -> str:
    return "oe:team:" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:32]


# 进程级缓存（DB 不变就一次构建即可）
_ID_MAP_CACHE = {"player_h2r": None, "player_r2h": None,
                 "team_h2r": None,   "team_r2h": None}


def _ensure_id_maps():
    """懒构建 ID 映射表。第一次调用时一次性扫表。"""
    if _ID_MAP_CACHE["player_h2r"] is not None:
        return _ID_MAP_CACHE
    conn = sqlite3.connect(DB_PATH)
    try:
        p_h2r, p_r2h = {}, {}
        for (raw,) in conn.execute("SELECT id FROM players"):
            h = _hash_pid(raw)
            p_h2r[h] = raw
            p_r2h[raw] = h
        t_h2r, t_r2h = {}, {}
        for (raw,) in conn.execute("SELECT id FROM teams"):
            h = _hash_tid(raw)
            t_h2r[h] = raw
            t_r2h[raw] = h
    finally:
        conn.close()
    _ID_MAP_CACHE.update(player_h2r=p_h2r, player_r2h=p_r2h,
                         team_h2r=t_h2r,   team_r2h=t_r2h)
    return _ID_MAP_CACHE


def _resolve_player_id(any_id: str) -> str:
    """入口：raw/hashed 都接受 → 返回 raw"""
    m = _ensure_id_maps()
    if any_id in m["player_r2h"]:
        return any_id
    return m["player_h2r"].get(any_id, any_id)


def _resolve_team_id(any_id: str) -> str:
    m = _ensure_id_maps()
    if any_id in m["team_r2h"]:
        return any_id
    return m["team_h2r"].get(any_id, any_id)


def _public_pid(raw_id: str) -> str:
    """出口：raw → hashed（与 list.json 对齐）"""
    return _ensure_id_maps()["player_r2h"].get(raw_id, raw_id)


def _public_tid(raw_id: str) -> str:
    return _ensure_id_maps()["team_r2h"].get(raw_id, raw_id)


# --- 字典类 ---

@api.get("/leagues")
def list_leagues():
    rows = get_db().execute("SELECT * FROM leagues ORDER BY tier, id").fetchall()
    return jsonify([dict(r) for r in rows])


@api.get("/seasons")
def list_seasons():
    league = request.args.get("league_id")
    sql = "SELECT * FROM seasons"
    args = ()
    if league:
        sql += " WHERE league_id=?"
        args = (league,)
    sql += " ORDER BY year DESC, split"
    rows = get_db().execute(sql, args).fetchall()
    return jsonify([dict(r) for r in rows])


@api.get("/teams")
def list_teams():
    sid = request.args.get("season_id")
    db = get_db()
    if sid:
        rows = db.execute("""
          SELECT t.id, t.name, ts.text_score, ts.r_league, ts.total_in_league
          FROM teams t
          JOIN team_season ts ON ts.team_id=t.id
          WHERE ts.season_id=?
          ORDER BY ts.text_score DESC
        """, (sid,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM teams ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if "id" in d and d["id"]:
            d["id"] = _public_tid(d["id"])
        out.append(d)
    return jsonify(out)


@api.get("/players")
def list_players():
    sid = request.args.get("season_id")
    pos = request.args.get("position")
    sql = """
      SELECT p.id, p.current_handle, ps.position, ps.team_id, t.name team_name,
             ps.text_score, ps.r_position, ps.total_in_pos
      FROM player_season ps
      JOIN players p ON p.id=ps.player_id
      LEFT JOIN teams t ON t.id=ps.team_id
      WHERE 1=1
    """
    args = []
    if sid:
        sql += " AND ps.season_id=?"
        args.append(sid)
    if pos:
        sql += " AND ps.position=?"
        args.append(pos)
    sql += " ORDER BY ps.text_score DESC"
    rows = get_db().execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # 与静态 list.json 一致：id 用 hashed，并补 name 字段
        if d.get("id"):
            d["id"] = _public_pid(d["id"])
        if d.get("team_id"):
            d["team_id"] = _public_tid(d["team_id"])
        d["name"] = d.get("current_handle")
        out.append(d)
    return jsonify(out)


# --- RadarSubject 构造 ---

def build_dims(record, avg_record):
    """两条记录都是 sqlite3.Row，含 d_* 列。生成 dimensions 数组。"""
    out = []
    for key, label in DIM_LABELS.items():
        out.append({
            "key":   key,
            "label": label,
            "value": record[key] if record[key] is not None else 0,
            "avg":   round(avg_record[key]) if avg_record and avg_record[key] is not None else 60,
        })
    return out


def _dim_rank_sql(col, entity_col, table, where_clause):
    """构造维度排名 SQL（安全版：col 已通过白名单校验）"""
    return f"""
      WITH r AS (
        SELECT {entity_col},
               RANK() OVER (ORDER BY {col} DESC) rk,
               COUNT(*) OVER () cnt
        FROM {table}
        WHERE {where_clause} AND {col} IS NOT NULL
      )
      SELECT rk, cnt FROM r WHERE {entity_col}=?
    """


@api.get("/player/<player_id>")
def player_radar(player_id):
    sid = request.args.get("season_id")
    if not sid:
        return jsonify(error="season_id required", code=400), 400

    # 兼容 hashed / raw 两种 ID
    raw_pid = _resolve_player_id(player_id)

    db = get_db()
    ps = db.execute(
        "SELECT ps.*, p.current_handle, t.name team_name "
        "FROM player_season ps "
        "JOIN players p ON p.id=ps.player_id "
        "LEFT JOIN teams t ON t.id=ps.team_id "
        "WHERE ps.player_id=? AND ps.season_id=?",
        (raw_pid, sid)
    ).fetchone()

    if not ps:
        return jsonify(error="not found", code=404), 404

    league_id = sid.split("-", 1)[0]
    avg = db.execute(
        "SELECT * FROM league_average WHERE league_id=? AND season_id=? AND position=?",
        (league_id, sid, ps["position"])
    ).fetchone()

    dims = build_dims(ps, avg)

    # 各维度同位置排名（白名单校验 dim key）
    for d in dims:
        if d["key"] not in _VALID_DIM_KEYS:
            continue
        sql = _dim_rank_sql(
            d["key"], "player_id", "player_season",
            "season_id=? AND position=?"
        )
        r = db.execute(sql, (sid, ps["position"], raw_pid)).fetchone()
        if r:
            d["rank"] = r["rk"]
            d["total"] = r["cnt"]

    pos_label = POSITION_LABELS.get(ps["position"], ps["position"])
    return jsonify({
        "type": "player",
        "id": _public_pid(raw_pid),
        "name": ps["current_handle"],
        "season_id": sid,
        "tags": [
            {"label": league_id, "color": "blue"},
            {"label": pos_label, "color": "red"},
        ],
        "top_stats": {
            "text_score": {
                "value": ps["text_score"],
                "rank": ps["r_position"],
                "total": ps["total_in_pos"],
                "subtitle": "Player Score",
            },
            "season_rating": {
                "value": ps["season_rating"],
                "rank": ps["r_position"],
                "total": ps["total_in_pos"],
                "subtitle": "Season Rating",
            },
        },
        "dimensions": dims,
        "raw": {
            "team_name": ps["team_name"],
            "games": ps["games"],
            "wins": ps["wins"],
            "losses": ps["losses"],
            "win_rate": round(ps["win_rate"] or 0, 3),
            "kda": round(ps["kda"] or 0, 2),
            "avg_dpm": round(ps["avg_dpm"] or 0, 1),
            "avg_vspm": round(ps["avg_vspm"] or 0, 2),
            "avg_cspm": round(ps["avg_cspm"] or 0, 2),
            "avg_gd15": round(ps["avg_gd15"] or 0, 1),
            "avg_csd15": round(ps["avg_csd15"] or 0, 2),
            "champion_pool": ps["champion_pool"],
        },
    })


@api.get("/team/<path:team_id>")
def team_radar(team_id):
    sid = request.args.get("season_id")
    if not sid:
        return jsonify(error="season_id required", code=400), 400

    # 兼容 hashed / raw 两种 ID
    raw_tid = _resolve_team_id(team_id)

    db = get_db()
    ts = db.execute(
        "SELECT ts.*, t.name team_name FROM team_season ts "
        "JOIN teams t ON t.id=ts.team_id "
        "WHERE ts.team_id=? AND ts.season_id=?",
        (raw_tid, sid)
    ).fetchone()

    if not ts:
        return jsonify(error="not found", code=404), 404

    league_id = ts["league_id"]
    avg = db.execute(
        "SELECT * FROM league_average WHERE league_id=? AND season_id=? AND position='team'",
        (league_id, sid)
    ).fetchone()

    dims = build_dims(ts, avg)

    for d in dims:
        if d["key"] not in _VALID_DIM_KEYS:
            continue
        sql = _dim_rank_sql(
            d["key"], "team_id", "team_season",
            "season_id=?"
        )
        r = db.execute(sql, (sid, raw_tid)).fetchone()
        if r:
            d["rank"] = r["rk"]
            d["total"] = r["cnt"]

    return jsonify({
        "type": "team",
        "id": _public_tid(raw_tid),
        "name": ts["team_name"],
        "season_id": sid,
        "tags": [
            {"label": league_id, "color": "blue"},
            {"label": "队伍", "color": "red"},
        ],
        "top_stats": {
            "text_score": {
                "value": ts["text_score"],
                "rank": ts["r_league"],
                "total": ts["total_in_league"],
                "subtitle": "Team Power",
            },
            "season_rating": {
                "value": ts["season_rating"],
                "rank": ts["r_league"],
                "total": ts["total_in_league"],
                "subtitle": "Season Rating",
            },
        },
        "dimensions": dims,
        "raw": {
            "games": ts["games"],
            "wins": ts["wins"],
            "losses": ts["losses"],
            "win_rate": round(ts["win_rate"] or 0, 3),
            "avg_game_length": round((ts["avg_game_length"] or 0) / 60, 1),
            "avg_gspd": round(ts["avg_gspd"] or 0, 3),
            "avg_gpr": round(ts["avg_gpr"] or 0, 3),
            "avg_ckpm": round(ts["avg_ckpm"] or 0, 2),
            "avg_dragons": round(ts["avg_dragons"] or 0, 2),
            "avg_barons": round(ts["avg_barons"] or 0, 2),
            "first_blood_rate": round(ts["first_blood_rate"] or 0, 3),
            "first_tower_rate": round(ts["first_tower_rate"] or 0, 3),
        },
    })
