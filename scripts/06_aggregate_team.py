"""Step 06 · team_season 聚合
- 队伍 6 维度 = 选手加权平均 + 队伍 team 行二级数据（gspd / gpr / ckpm）混合
  详见 SPEC §4.2
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from _common import db, step_log
import metrics as M

def main():
    with step_log("06_aggregate_team") as st:
        c = db()
        c.execute("DELETE FROM team_season")

        # 1. 选手 d_* 加权（按 games）
        player_avg = {r["k"]: r for r in c.execute("""
          SELECT team_id||'|'||season_id k, team_id, season_id,
                 SUM(d_teamfight*games)*1.0/SUM(games)   d_teamfight,
                 SUM(d_laning*games)*1.0/SUM(games)      d_laning,
                 SUM(d_macro*games)*1.0/SUM(games)       d_macro,
                 SUM(d_mechanics*games)*1.0/SUM(games)   d_mechanics,
                 SUM(d_consistency*games)*1.0/SUM(games) d_consistency,
                 SUM(d_meta_adapt*games)*1.0/SUM(games)  d_meta_adapt
          FROM player_season
          WHERE team_id IS NOT NULL AND d_teamfight IS NOT NULL
          GROUP BY team_id, season_id
        """).fetchall()}

        # 2. 队伍 team 行聚合（gspd/gpr/ckpm 等 — EGR 类直读）
        team_aggs = c.execute("""
          SELECT team_id, season_id, league_id,
                 COUNT(*) games,
                 SUM(result) wins,
                 AVG(game_length) avg_game_length,
                 AVG(gspd) avg_gspd, AVG(gpr) avg_gpr,
                 AVG(ckpm) avg_ckpm, AVG(team_kpm) avg_team_kpm,
                 AVG(dragons) avg_dragons, AVG(barons) avg_barons,
                 AVG(firstblood) first_blood_rate,
                 AVG(firsttower) first_tower_rate
          FROM match_rows
          WHERE position='team' AND team_id IS NOT NULL
          GROUP BY team_id, season_id
        """).fetchall()

        n = 0
        # 收集所有队伍的 raw 维度分，按赛季分组后做分位拉伸
        from collections import defaultdict
        rows_buf = []          # 每个元素: (ta, agg, raw_dims)
        season_dims = defaultdict(lambda: defaultdict(list))  # season -> dim -> [raw]
        DIMS = ["d_teamfight","d_laning","d_macro","d_mechanics","d_consistency","d_meta_adapt"]

        for ta in team_aggs:
            key = f"{ta['team_id']}|{ta['season_id']}"
            pa = player_avg.get(key)
            if not pa:
                continue
            agg = dict(ta)
            agg["win_rate"] = (ta["wins"] or 0) / ta["games"] if ta["games"] else 0
            raw_dims = M.team_dimensions(agg, dict(pa))   # raw 维度分（未拉伸）
            rows_buf.append((ta, agg, raw_dims))
            for dk in DIMS:
                season_dims[ta["season_id"]][dk].append(raw_dims[dk])

        # 对每个赛季每个维度做组内分位拉伸 → 队伍第一名也满格
        for ta, agg, raw_dims in rows_buf:
            sid = ta["season_id"]
            dims = {}
            for dk in DIMS:
                dims[dk] = M.percentile_stretch(raw_dims[dk], season_dims[sid][dk])
            text, sr = M.scores(dims.values(), agg["win_rate"])

            c.execute("""
              INSERT OR REPLACE INTO team_season
                (team_id, season_id, league_id,
                 d_teamfight, d_laning, d_macro, d_mechanics, d_consistency, d_meta_adapt,
                 games, wins, losses, win_rate, avg_game_length,
                 avg_gspd, avg_gpr, avg_ckpm, avg_team_kpm,
                 avg_dragons, avg_barons, first_blood_rate, first_tower_rate,
                 text_score, season_rating)
              VALUES (?,?,?, ?,?,?,?,?,?,
                      ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?)
            """, (
                ta["team_id"], ta["season_id"], ta["league_id"],
                dims["d_teamfight"], dims["d_laning"], dims["d_macro"],
                dims["d_mechanics"], dims["d_consistency"], dims["d_meta_adapt"],
                ta["games"], ta["wins"], ta["games"]-ta["wins"], agg["win_rate"], ta["avg_game_length"],
                ta["avg_gspd"], ta["avg_gpr"], ta["avg_ckpm"], ta["avg_team_kpm"],
                ta["avg_dragons"], ta["avg_barons"], ta["first_blood_rate"], ta["first_tower_rate"],
                text, sr,
            ))
            n += 1

        # 联赛内排名
        c.execute("""
          WITH ranked AS (
            SELECT team_id, season_id,
                   RANK() OVER (PARTITION BY season_id ORDER BY text_score DESC) rk,
                   COUNT(*) OVER (PARTITION BY season_id) cnt
            FROM team_season
          )
          UPDATE team_season SET
            r_league = (SELECT rk FROM ranked r WHERE r.team_id=team_season.team_id AND r.season_id=team_season.season_id),
            total_in_league = (SELECT cnt FROM ranked r WHERE r.team_id=team_season.team_id AND r.season_id=team_season.season_id)
        """)
        c.commit()
        st["rows_out"] = n

        print("\n--- LCK Cup team_season Top ---")
        for r in c.execute("""
          SELECT t.name, ts.text_score, ts.r_league, ts.total_in_league,
                 ts.d_teamfight, ts.d_laning, ts.d_macro, ts.d_mechanics, ts.d_consistency, ts.d_meta_adapt,
                 ROUND(ts.avg_gspd,3) gspd, ROUND(ts.avg_gpr,3) gpr
          FROM team_season ts JOIN teams t ON t.id=ts.team_id
          WHERE ts.season_id='LCK-2026-Cup' ORDER BY ts.text_score DESC LIMIT 6
        """):
            print(f"  {r['name'][:18]:<18} score={r['text_score']:>4} #{r['r_league']}/{r['total_in_league']} "
                  f"gspd={r['gspd']:>5} gpr={r['gpr']:>5} "
                  f"d=[{r['d_teamfight']},{r['d_laning']},{r['d_macro']},{r['d_mechanics']},{r['d_consistency']},{r['d_meta_adapt']}]")
        c.close()

if __name__ == "__main__":
    main()
