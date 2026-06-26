"""Step 00 · 数据库直通：lol_db.sqlite → radar.db.match_rows

替代 02_import_csv：从 lol_db 反向重构 OE 行结构，灌进 radar-engine 的 match_rows。
"""
import os, sys, sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "server"))
from _common import db, step_log, ALLOWED_LEAGUES, ALLOWED_POSITIONS

LOL_DB = Path(os.environ.get(
    "LOL_DB",
    "/sdcard/第三宇宙警备站/lol_db/lol_2026.sqlite"
))

COLS = ("game_id, side, position, league_id, season_id, date, patch, playoffs, "
        "datacompleteness, player_id, player_name, team_id, team_name, champion, "
        "game_length, result, kills, deaths, assists, teamkills, doublekills, "
        "triplekills, quadrakills, pentakills, firstblood, firstdragon, "
        "firstherald, firstbaron, firsttower, dragons, barons, dpm, damageshare, "
        "damagemitigatedperminute, vspm, wpm, wcpm, cspm, ckpm, team_kpm, "
        "earnedgoldshare, gspd, gpr, goldat10, goldat15, opp_goldat10, "
        "opp_goldat15, golddiffat10, golddiffat15, csdiffat10, csdiffat15, "
        "xpdiffat15")
N = len(COLS.split(","))
INSERT_SQL = f"INSERT OR REPLACE INTO match_rows ({COLS}) VALUES ({','.join('?'*N)})"


def season_id(league, year, split):
    sp = (split or "Main").strip() or "Main"
    return f"{league}-{year}-{sp}".replace(" ", "_")


def player_row(p, g, t):
    """build one player-position row tuple (52 cols, order = COLS)"""
    sid = season_id(g["league_code"], g["year"], g["split"])
    return (
        p["gameid"], p["side"], p["position"],
        g["league_code"], sid, g["game_date"], g["patch"],
        1 if g["playoffs"] else 0, g["datacompleteness"],
        p["player_id"], p.get("player_name") if isinstance(p, dict) else None,
        p["team_id"], None, p["champion_name"], g["gamelength_sec"], p["result"],
        p["kills"], p["deaths"], p["assists"],
        t["teamkills"] if t else None,
        p["doublekills"], p["triplekills"], p["quadrakills"], p["pentakills"],
        p["firstbloodkill"],
        t["firstdragon"] if t else None,
        t["firstherald"] if t else None,
        t["firstbaron"]  if t else None,
        t["firsttower"]  if t else None,
        t["dragons"] if t else None, t["barons"] if t else None,
        p["dpm"], p["damageshare"], p["damagemitigatedperminute"],
        p["vspm"], p["wpm"], p["wcpm"], p["cspm"],
        t["ckpm"] if t else None,
        t["team_kpm"] if t else None,
        p["earnedgoldshare"], None, None,  # gspd/gpr 选手行无
        p["goldat10"], p["goldat15"], p["opp_goldat10"], p["opp_goldat15"],
        p["golddiffat10"], p["golddiffat15"],
        p["csdiffat10"], p["csdiffat15"], p["xpdiffat15"],
    )


def team_row(t, g):
    sid = season_id(g["league_code"], g["year"], g["split"])
    return (
        t["gameid"], t["side"], "team",
        g["league_code"], sid, g["game_date"], g["patch"],
        1 if g["playoffs"] else 0, g["datacompleteness"],
        None, None, t["team_id"], None, None,
        g["gamelength_sec"], t["result"],
        None, None, None, t["teamkills"],
        None, None, None, None,
        t["firstblood"], t["firstdragon"], t["firstherald"],
        t["firstbaron"], t["firsttower"],
        t["dragons"], t["barons"],
        t["dpm"], None, t["damagemitigatedperminute"],
        t["vspm"], t["wpm"], t["wcpm"], t["cspm"], t["ckpm"], t["team_kpm"],
        None, t["gspd"], t["gpr"],
        t["goldat10"], t["goldat15"], t["opp_goldat10"], t["opp_goldat15"],
        t["golddiffat10"], t["golddiffat15"],
        t["csdiffat10"], t["csdiffat15"], t["xpdiffat15"],
    )


def main():
    with step_log("00_seed_from_lol_db") as st:
        if not LOL_DB.exists():
            raise FileNotFoundError(LOL_DB)

        src = sqlite3.connect(LOL_DB)
        src.row_factory = sqlite3.Row

        place = ",".join("?" * len(ALLOWED_LEAGUES))
        games = {g["gameid"]: g for g in src.execute(
            f"SELECT * FROM games WHERE league_code IN ({place})",
            tuple(ALLOWED_LEAGUES))}
        st["rows_in"] = len(games)
        print(f"games (ALLOWED_LEAGUES): {len(games)}")
        if not games:
            src.close()
            return

        gids = tuple(games.keys())
        IN = "(" + ",".join("?" * len(gids)) + ")"
        team_rows_all = src.execute(
            f"SELECT * FROM game_team_stats WHERE gameid IN {IN}", gids).fetchall()
        team_idx = {(r["gameid"], r["side"]): r for r in team_rows_all}
        player_rows_all = src.execute(
            f"SELECT * FROM game_player_stats WHERE gameid IN {IN}", gids).fetchall()
        # 名字字典
        p_name = {r["player_id"]: r["player_name"] for r in src.execute(
            "SELECT player_id, player_name FROM players")}
        t_name = {r["team_id"]: r["team_name"] for r in src.execute(
            "SELECT team_id, team_name FROM teams")}
        src.close()

        conn = db()
        try:
            conn.execute("DELETE FROM match_rows")
            batch = []
            rows_out = 0

            for p in player_rows_all:
                if p["position"] not in ALLOWED_POSITIONS:
                    continue
                g = games[p["gameid"]]
                t = team_idx.get((p["gameid"], p["side"]))
                d = dict(p); d["player_name"] = p_name.get(p["player_id"])
                row = list(player_row(d, g, t))
                row[10] = d["player_name"]            # player_name
                row[12] = t_name.get(p["team_id"])    # team_name
                batch.append(tuple(row))
                if len(batch) >= 500:
                    conn.executemany(INSERT_SQL, batch); rows_out += len(batch); batch.clear()

            for t in team_rows_all:
                if "team" not in ALLOWED_POSITIONS:
                    break
                g = games[t["gameid"]]
                row = list(team_row(t, g))
                row[12] = t_name.get(t["team_id"])
                batch.append(tuple(row))
                if len(batch) >= 500:
                    conn.executemany(INSERT_SQL, batch); rows_out += len(batch); batch.clear()

            if batch:
                conn.executemany(INSERT_SQL, batch); rows_out += len(batch)
            conn.commit()
            st["rows_out"] = rows_out
            print(f"match_rows inserted: {rows_out}")
            # 抽样
            r = conn.execute(
                "SELECT COUNT(*) c, COUNT(DISTINCT season_id) s, "
                "COUNT(DISTINCT player_id) p, COUNT(DISTINCT team_id) t FROM match_rows"
            ).fetchone()
            print(f"summary: rows={r[0]} seasons={r[1]} players={r[2]} teams={r[3]}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
