"""Step 03 · 由 match_rows 生成字典表 leagues/seasons/teams/players。"""
from _common import db, step_log

REGION_MAP = {
    "LPL":"CN","LCK":"KR","LCKC":"KR","LJL":"JP","LEC":"EU",
    "LCS":"NA","LCP":"APAC","CBLOL":"BR","VCS":"VN","PCS":"APAC","LLA":"LATAM",
}
TIER1 = {"LPL","LCK","LEC","LCS","LCP"}

def main():
    with step_log("03_build_dims") as st:
        c = db()
        # 先删 seasons，再删 leagues；seasons.league_id 有外键指向 leagues
        c.execute("DELETE FROM seasons")
        c.execute("DELETE FROM leagues")
        rows = c.execute("SELECT DISTINCT league_id FROM match_rows").fetchall()
        for r in rows:
            lid = r["league_id"]
            c.execute("INSERT OR REPLACE INTO leagues(id,name,region,tier) VALUES(?,?,?,?)",
                      (lid, lid, REGION_MAP.get(lid, "UNK"), 1 if lid in TIER1 else 2))
        st["rows_out"] += len(rows)
        # seasons
        c.execute("DELETE FROM seasons")
        rows = c.execute(
            "SELECT DISTINCT season_id, league_id FROM match_rows"
        ).fetchall()
        for r in rows:
            sid = r["season_id"]
            # 解析 'LPL-2026-Spring' → year/split
            parts = sid.split("-", 2)
            year = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else 0
            split = parts[2] if len(parts) >= 3 else ""
            c.execute("INSERT OR REPLACE INTO seasons(id,league_id,year,split) VALUES(?,?,?,?)",
                      (sid, r["league_id"], year, split))
        st["rows_out"] += len(rows)
        # teams: 名称取最近一次出现的 teamname（CSV 里 teamname 我们没存，
        # 改为：teams 的 name 暂时和 id 一致；导入层若有 teams.json 再覆盖）
        # 这里我们临时再读一次 CSV 抽 teamname → 略繁琐；先用一个折中：
        # teamname 没存进 match_rows，先让 name = team_id 的尾段。
        c.execute("DELETE FROM teams")
        rows = c.execute(
            "SELECT team_id, MAX(league_id) lg FROM match_rows "
            "WHERE team_id IS NOT NULL GROUP BY team_id"
        ).fetchall()
        for r in rows:
            tid = r["team_id"]
            nm = c.execute(
                "SELECT team_name FROM match_rows WHERE team_id=? AND team_name IS NOT NULL "
                "ORDER BY date DESC LIMIT 1", (tid,)).fetchone()
            name = nm["team_name"] if nm else tid
            short = (name.split()[0] if name else tid)[:8]
            c.execute("INSERT OR REPLACE INTO teams(id,name,short_name,current_league) "
                      "VALUES(?,?,?,?)", (tid, name, short, r["lg"]))
        st["rows_out"] += len(rows)
        # players（同上：current_handle 暂用 player_id 尾段，等后续 02b 步补 handle）
        c.execute("DELETE FROM players")
        rows = c.execute(
            "SELECT player_id, MAX(team_id) tm, MAX(position) pos FROM match_rows "
            "WHERE player_id IS NOT NULL AND position!='team' GROUP BY player_id"
        ).fetchall()
        for r in rows:
            pid = r["player_id"]
            nm = c.execute(
                "SELECT player_name FROM match_rows WHERE player_id=? AND player_name IS NOT NULL "
                "ORDER BY date DESC LIMIT 1", (pid,)).fetchone()
            handle = nm["player_name"] if nm else pid
            c.execute("INSERT OR REPLACE INTO players(id,current_handle,current_team,current_position) "
                      "VALUES(?,?,?,?)", (pid, handle, r["tm"], r["pos"]))
        st["rows_out"] += len(rows)
        c.commit()
        # 概览
        for t in ("leagues","seasons","teams","players"):
            n = c.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            print(f"  {t}: {n}")
        c.close()

if __name__ == "__main__":
    main()
