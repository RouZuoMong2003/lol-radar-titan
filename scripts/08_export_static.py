"""Step 08 · 把整个数据库导出成静态 JSON，给 GitHub Pages 用
- 输出到 ../web/data/ 下
- 前端会切换到"先看 /data/*.json，没有再 fetch /api/*"
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from _common import db, step_log, ROOT
import metrics as M

OUT = ROOT / "web" / "data"
DIM_LABELS = {
    "d_teamfight":"团战决策","d_laning":"线上压制","d_macro":"长线运营",
    "d_mechanics":"操作上限","d_consistency":"心态稳定","d_meta_adapt":"版本适应",
}
POS_LABELS = {"top":"上单","jng":"打野","mid":"中单","bot":"下路","sup":"辅助","team":"队伍"}

def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",",":"))
    return p.stat().st_size

def build_dims(rec, avg, ranks, is_team=False, position="mid"):
    pos_meta = M.dim_meta_for(position) if not is_team else M.DIM_META
    out = []
    for key, label in DIM_LABELS.items():
        meta = pos_meta.get(key, {})
        fields = M.TEAM_DIM_FIELDS.get(key) if is_team else meta.get("fields", "")
        d = {"key":key, "label":label, "fields":fields,
             "value": rec[key] if rec[key] is not None else 0,
             "avg":   round(avg[key]) if avg and avg[key] is not None else 60}
        if key in ranks:
            d["rank"], d["total"] = ranks[key]
        out.append(d)
    return out

def formula_block(is_team=False, position="mid"):
    """第 7 点：维度计算原理，导出到每个 RadarSubject。按位置差异化 fields。"""
    pos_meta = M.dim_meta_for(position) if not is_team else M.DIM_META
    items = []
    for key, meta in pos_meta.items():
        items.append({
            "label": meta["label"],
            "fields": (M.TEAM_DIM_FIELDS.get(key) if is_team else meta["fields"]),
            "formula": meta["formula"],
        })
    return {"items": items, "note": M.NORMALIZE_NOTE}

def main():
    with step_log("08_export_static") as st:
        c = db()
        OUT.mkdir(parents=True, exist_ok=True)

        # === 索引：seasons ===
        seasons = [dict(r) for r in c.execute(
            "SELECT s.id, s.league_id, s.year, s.split, "
            "(SELECT COUNT(*) FROM player_season WHERE season_id=s.id) AS players, "
            "(SELECT COUNT(*) FROM team_season   WHERE season_id=s.id) AS teams "
            "FROM seasons s ORDER BY s.league_id, s.year DESC, s.split"
        )]
        write("seasons.json", seasons)

        # === 每个赛季：选手列表 + 队伍列表 ===
        for s in seasons:
            sid = s["id"]
            players = [dict(r) for r in c.execute(
                "SELECT ps.player_id id, p.current_handle name, ps.position, "
                "       ps.team_id, t.name team_name, "
                "       ps.text_score, ps.season_rating, ps.r_position, ps.total_in_pos "
                "FROM player_season ps JOIN players p ON p.id=ps.player_id "
                "LEFT JOIN teams t ON t.id=ps.team_id "
                "WHERE ps.season_id=? ORDER BY ps.text_score DESC", (sid,))]
            teams = [dict(r) for r in c.execute(
                "SELECT ts.team_id id, t.name name, ts.text_score, ts.season_rating, "
                "       ts.r_league, ts.total_in_league, ts.win_rate "
                "FROM team_season ts JOIN teams t ON t.id=ts.team_id "
                "WHERE ts.season_id=? ORDER BY ts.text_score DESC", (sid,))]
            safe = sid.replace("/", "_")
            write(f"season/{safe}/list.json", {"players": players, "teams": teams})

        # === 每个 player_season / team_season 的完整 RadarSubject ===
        # 准备：维度排名查询缓存（同 season+position 内）
        n_p = n_t = 0
        for ps in c.execute("SELECT * FROM player_season").fetchall():
            sid, pid, pos = ps["season_id"], ps["player_id"], ps["position"]
            league = sid.split("-",1)[0]
            avg = c.execute(
                "SELECT * FROM league_average WHERE league_id=? AND season_id=? AND position=?",
                (league, sid, pos)).fetchone()
            ranks = {}
            for k in DIM_LABELS:
                r = c.execute(
                    f"WITH r AS (SELECT player_id, RANK() OVER (ORDER BY {k} DESC) rk, "
                    f" COUNT(*) OVER () cnt FROM player_season "
                    f" WHERE season_id=? AND position=? AND {k} IS NOT NULL) "
                    f"SELECT rk,cnt FROM r WHERE player_id=?",
                    (sid, pos, pid)).fetchone()
                if r: ranks[k] = (r["rk"], r["cnt"])
            handle = c.execute("SELECT current_handle FROM players WHERE id=?",(pid,)).fetchone()["current_handle"]
            tname = c.execute("SELECT name FROM teams WHERE id=?",(ps["team_id"],)).fetchone()
            tname = tname["name"] if tname else None
            obj = {
                "type":"player","id":pid,"name":handle,"season_id":sid,
                "tags":[{"label":league,"color":"blue"},
                        {"label":POS_LABELS.get(pos,pos),"color":"red"}],
                "top_stats":{
                    "text_score":{"value":ps["text_score"],"rank":ps["r_position"],
                                  "total":ps["total_in_pos"],"subtitle":"Player Score"},
                    "season_rating":{"value":ps["season_rating"],"rank":ps["r_position"],
                                     "total":ps["total_in_pos"],"subtitle":"Season Rating"},
                },
                "dimensions": build_dims(ps, avg, ranks, position=pos),
                "formula_note": formula_block(is_team=False, position=pos),
                "raw":{
                    "team_name": tname,
                    "games":ps["games"],"wins":ps["wins"],"losses":ps["losses"],
                    "win_rate": round(ps["win_rate"] or 0,3),
                    "kda": round(ps["kda"] or 0,2),
                    "avg_dpm":  round(ps["avg_dpm"] or 0,1),
                    "avg_vspm": round(ps["avg_vspm"] or 0,2),
                    "avg_cspm": round(ps["avg_cspm"] or 0,2),
                    "avg_gd15": round(ps["avg_gd15"] or 0,1),
                    "avg_csd15":round(ps["avg_csd15"] or 0,2),
                    "champion_pool": ps["champion_pool"],
                }
            }
            safe_pid = pid.replace(":","_")
            write(f"season/{sid.replace('/','_')}/player/{safe_pid}.json", obj)
            n_p += 1

        for ts in c.execute("SELECT * FROM team_season").fetchall():
            sid, tid = ts["season_id"], ts["team_id"]
            league = ts["league_id"]
            avg = c.execute(
                "SELECT * FROM league_average WHERE league_id=? AND season_id=? AND position='team'",
                (league, sid)).fetchone()
            ranks = {}
            for k in DIM_LABELS:
                r = c.execute(
                    f"WITH r AS (SELECT team_id, RANK() OVER (ORDER BY {k} DESC) rk, "
                    f"COUNT(*) OVER () cnt FROM team_season WHERE season_id=? AND {k} IS NOT NULL) "
                    f"SELECT rk,cnt FROM r WHERE team_id=?", (sid, tid)).fetchone()
                if r: ranks[k] = (r["rk"], r["cnt"])
            tname = c.execute("SELECT name FROM teams WHERE id=?",(tid,)).fetchone()["name"]
            obj = {
                "type":"team","id":tid,"name":tname,"season_id":sid,
                "tags":[{"label":league,"color":"blue"},
                        {"label":"队伍","color":"red"}],
                "top_stats":{
                    "text_score":{"value":ts["text_score"],"rank":ts["r_league"],
                                  "total":ts["total_in_league"],"subtitle":"Team Power"},
                    "season_rating":{"value":ts["season_rating"],"rank":ts["r_league"],
                                     "total":ts["total_in_league"],"subtitle":"Season Rating"},
                },
                "dimensions": build_dims(ts, avg, ranks, is_team=True),
                "formula_note": formula_block(is_team=True),
                "raw":{
                    "games":ts["games"],"wins":ts["wins"],"losses":ts["losses"],
                    "win_rate":round(ts["win_rate"] or 0,3),
                    "avg_game_length": round((ts["avg_game_length"] or 0)/60,1),
                    "avg_gspd": round(ts["avg_gspd"] or 0,3),
                    "avg_gpr":  round(ts["avg_gpr"]  or 0,3),
                    "avg_ckpm": round(ts["avg_ckpm"] or 0,2),
                    "avg_dragons": round(ts["avg_dragons"] or 0,2),
                    "avg_barons":  round(ts["avg_barons"]  or 0,2),
                    "first_blood_rate": round(ts["first_blood_rate"] or 0,3),
                    "first_tower_rate": round(ts["first_tower_rate"] or 0,3),
                }
            }
            safe_tid = tid.replace(":","_")
            write(f"season/{sid.replace('/','_')}/team/{safe_tid}.json", obj)
            n_t += 1

        c.close()
        st["rows_out"] = n_p + n_t
        print(f"导出 {len(seasons)} 个赛季 / {n_p} 个 player JSON / {n_t} 个 team JSON")
        # 总大小
        total = sum(p.stat().st_size for p in OUT.rglob("*.json"))
        print(f"总体积: {total/1024:.1f} KB")

if __name__ == "__main__":
    main()
