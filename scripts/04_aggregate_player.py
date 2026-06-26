"""Step 04 · match_rows → player_season（聚合 + 6 维度原始值，原料保留在内存供 05 用）
仅写入 player_season 的"原值列"（games/wins/avg_*/kda 等），d_*/rank 留空。
中间产物（每行一个 raw dict）用 pickle 序列化到 db/_stage_player_raw.pkl，
供 05 步读取做 z-score。
"""
import sys, statistics, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from _common import db, step_log, ROOT
import metrics as M

STAGE_FILE = ROOT / "db" / "_stage_player_raw.pkl"

def main():
    with step_log("04_aggregate_player") as st:
        c = db()
        c.execute("DELETE FROM player_season")

        rows = c.execute("""
          SELECT
            player_id, season_id, MAX(team_id) team_id, MAX(position) position,
            COUNT(*) games, SUM(result) wins,
            SUM(kills) sum_kills, SUM(deaths) sum_deaths, SUM(assists) sum_assists,
            SUM(teamkills) sum_teamkills,
            SUM(doublekills) sum_double, SUM(triplekills) sum_triple,
            SUM(quadrakills) sum_quad,   SUM(pentakills)  sum_penta,
            AVG(kills) avg_kills, AVG(deaths) avg_deaths, AVG(assists) avg_assists,
            AVG(dpm) avg_dpm, AVG(damageshare) avg_damageshare,
            AVG(damagemitigatedperminute) avg_mitig,
            AVG(vspm) avg_vspm, AVG(wcpm) avg_wcpm, AVG(cspm) avg_cspm,
            AVG(earnedgoldshare) avg_egshare,
            AVG(golddiffat10) avg_gd10, AVG(golddiffat15) avg_gd15,
            AVG(csdiffat10)  avg_csd10, AVG(csdiffat15)  avg_csd15,
            AVG(xpdiffat15)  avg_xpd15,
            COUNT(DISTINCT champion) champion_pool
          FROM match_rows
          WHERE position!='team' AND player_id IS NOT NULL
          GROUP BY player_id, season_id
        """).fetchall()

        # 预取该选手出场场次的 game_id 列表 → 用于关联 team 行 first_*
        # 一次取全表的 player + team 行，避免 N+1
        all_player_games = c.execute("""
          SELECT player_id, season_id, game_id, team_id, result, deaths,
                 goldat15, opp_goldat15, patch
          FROM match_rows WHERE position!='team' AND player_id IS NOT NULL
        """).fetchall()
        team_rows_all = c.execute("""
          SELECT game_id, team_id, firstdragon, firstherald, firstbaron, firsttower
          FROM match_rows WHERE position='team'
        """).fetchall()
        team_idx = {(t["game_id"], t["team_id"]): t for t in team_rows_all}

        # 把 player_games 按 (pid,sid) 分桶
        from collections import defaultdict
        bucket = defaultdict(list)
        for g in all_player_games:
            bucket[(g["player_id"], g["season_id"])].append(g)

        raw_list = []
        for r in rows:
            pid, sid = r["player_id"], r["season_id"]
            games = bucket.get((pid, sid), [])
            n = len(games)
            fr = ft = 0
            comeback_n = comeback_w = 0
            deaths_list = []
            patch_results = []
            for g in games:
                t = team_idx.get((g["game_id"], g["team_id"]))
                if t:
                    fr += int(bool(t["firstdragon"])) + int(bool(t["firstherald"])) + int(bool(t["firstbaron"]))
                    ft += int(bool(t["firsttower"]))
                gd = (g["goldat15"] or 0) - (g["opp_goldat15"] or 0)
                if gd < -1000:
                    comeback_n += 1
                    if g["result"]: comeback_w += 1
                deaths_list.append(g["deaths"] or 0)
                if g["patch"]: patch_results.append((g["patch"], g["result"]))

            first_resource_rate = fr / (n * 3) if n else 0
            first_tower_rate    = ft / n if n else 0
            comeback_rate       = (comeback_w / comeback_n) if comeback_n else 0
            if deaths_list and statistics.mean(deaths_list) > 0:
                cv = statistics.pstdev(deaths_list) / statistics.mean(deaths_list)
                death_stability = max(0, min(1, 1 - cv))
            else:
                death_stability = 0.5
            if patch_results:
                latest = sorted({p for p,_ in patch_results}, reverse=True)[:2]
                lp = [w for p,w in patch_results if p in latest]
                latest_patch_winrate = (sum(lp)/len(lp)) if lp else 0
            else:
                latest_patch_winrate = 0

            kda = (r["sum_kills"] + r["sum_assists"]) / max(r["sum_deaths"], 1)
            win_rate = (r["wins"] or 0) / r["games"]

            # 写 player_season 原值（d_*/rank 留 NULL）
            c.execute("""
              INSERT OR REPLACE INTO player_season
                (player_id, season_id, team_id, position,
                 games, wins, losses, win_rate, kda,
                 avg_kills, avg_deaths, avg_assists,
                 avg_dpm, avg_damageshare, avg_vspm, avg_wcpm, avg_cspm,
                 avg_egshare, avg_gd15, avg_csd15, avg_xpd15, champion_pool)
              VALUES (?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?,?,?, ?,?,?,?,?)
            """, (
                pid, sid, r["team_id"], r["position"],
                r["games"], r["wins"], r["games"]-r["wins"], win_rate, kda,
                r["avg_kills"], r["avg_deaths"], r["avg_assists"],
                r["avg_dpm"], r["avg_damageshare"], r["avg_vspm"], r["avg_wcpm"], r["avg_cspm"],
                r["avg_egshare"], r["avg_gd15"], r["avg_csd15"], r["avg_xpd15"],
                r["champion_pool"],
            ))

            # 准备 z-score 原料（dict）
            raw = dict(r)
            raw.update({
                "first_resource_rate": first_resource_rate,
                "first_tower_rate":    first_tower_rate,
                "comeback_rate":       comeback_rate,
                "death_stability":     death_stability,
                "latest_patch_winrate":latest_patch_winrate,
                "new_champ_score":     0,
                "kda":                 kda,
                "win_rate":            win_rate,
            })
            # 用 metrics 的 player_dimensions 计算"维度原料"
            raw["_dim_inputs"] = M.player_dimensions(raw)
            raw_list.append(raw)

        c.commit()
        c.close()

        # 落盘给 step05 用
        with open(STAGE_FILE, "wb") as f:
            pickle.dump(raw_list, f)
        print(f"player_season rows: {len(raw_list)}; stage saved to {STAGE_FILE.name}")
        st["rows_out"] = len(raw_list)

if __name__ == "__main__":
    main()
