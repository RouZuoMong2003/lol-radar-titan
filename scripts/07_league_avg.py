"""Step 07 · league_average（橙色基线）
- 选手雷达基线：同 (league, season, position) 同位置选手 d_* 平均
- 队伍雷达基线：同 (league, season) 全队伍 d_* 平均（position='team'）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from _common import db, step_log

def main():
    with step_log("07_league_avg") as st:
        c = db()
        c.execute("DELETE FROM league_average")
        # 选手维度
        c.execute("""
          INSERT INTO league_average
          SELECT
            substr(season_id, 1, instr(season_id,'-')-1) league_id,
            season_id, position,
            AVG(d_teamfight), AVG(d_laning), AVG(d_macro),
            AVG(d_mechanics), AVG(d_consistency), AVG(d_meta_adapt)
          FROM player_season
          WHERE d_teamfight IS NOT NULL
          GROUP BY season_id, position
        """)
        # 队伍维度（position='team'）
        c.execute("""
          INSERT INTO league_average
          SELECT league_id, season_id, 'team',
            AVG(d_teamfight), AVG(d_laning), AVG(d_macro),
            AVG(d_mechanics), AVG(d_consistency), AVG(d_meta_adapt)
          FROM team_season
          WHERE d_teamfight IS NOT NULL
          GROUP BY league_id, season_id
        """)
        c.commit()
        n = c.execute("SELECT COUNT(*) c FROM league_average").fetchone()["c"]
        st["rows_out"] = n
        print(f"league_average rows: {n}")
        c.close()

if __name__ == "__main__":
    main()
