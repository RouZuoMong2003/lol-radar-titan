"""Step 02 · CSV → match_rows
- 流式 csv.DictReader，500 行一个事务
- 过滤：datacompleteness=complete + league ∈ ALLOWED + position ∈ ALLOWED
- 重跑安全：先 DELETE 已存在的赛季再插
"""
import csv, sys
from _common import (db, CSV_PATH, ALLOWED_LEAGUES, ALLOWED_POSITIONS,
                     step_log, to_int, to_float, to_bool_int)

# DB 列 ← CSV 列 映射（DB 列在前，CSV 列在后）
COL_MAP = [
    # 标识
    ("game_id",      "gameid",       str),
    ("side",         "side",         str),
    ("position",     "position",     str),
    ("league_id",    "league",       str),
    ("date",         "date",         str),
    ("patch",        "patch",        str),
    ("playoffs",     "playoffs",     to_bool_int),
    ("datacompleteness","datacompleteness", str),
    ("player_id",    "playerid",     lambda x: x or None),
    ("player_name",  "playername",   lambda x: x or None),
    ("team_id",      "teamid",       lambda x: x or None),
    ("team_name",    "teamname",     lambda x: x or None),
    ("champion",     "champion",     str),
    ("game_length",  "gamelength",   to_int),
    ("result",       "result",       to_bool_int),
    # 一级
    ("kills",        "kills",        to_int),
    ("deaths",       "deaths",       to_int),
    ("assists",      "assists",      to_int),
    ("teamkills",    "teamkills",    to_int),
    ("doublekills",  "doublekills",  to_int),
    ("triplekills",  "triplekills",  to_int),
    ("quadrakills",  "quadrakills",  to_int),
    ("pentakills",   "pentakills",   to_int),
    ("firstblood",   "firstblood",   to_bool_int),
    ("firstdragon",  "firstdragon",  to_bool_int),
    ("firstherald",  "firstherald",  to_bool_int),
    ("firstbaron",   "firstbaron",   to_bool_int),
    ("firsttower",   "firsttower",   to_bool_int),
    ("dragons",      "dragons",      to_int),
    ("barons",       "barons",       to_int),
    # 二级
    ("dpm",          "dpm",          to_float),
    ("damageshare",  "damageshare",  to_float),
    ("damagemitigatedperminute","damagemitigatedperminute", to_float),
    ("vspm",         "vspm",         to_float),
    ("wpm",          "wpm",          to_float),
    ("wcpm",         "wcpm",         to_float),
    ("cspm",         "cspm",         to_float),
    ("ckpm",         "ckpm",         to_float),
    ("team_kpm",     "team kpm",     to_float),
    ("earnedgoldshare","earnedgoldshare", to_float),
    ("gspd",         "gspd",         to_float),
    ("gpr",          "gpr",          to_float),
    # 时间分段
    ("goldat10",     "goldat10",     to_int),
    ("goldat15",     "goldat15",     to_int),
    ("opp_goldat10", "opp_goldat10", to_int),
    ("opp_goldat15", "opp_goldat15", to_int),
    ("golddiffat10", "golddiffat10", to_int),
    ("golddiffat15", "golddiffat15", to_int),
    ("csdiffat10",   "csdiffat10",   to_int),
    ("csdiffat15",   "csdiffat15",   to_int),
    ("xpdiffat15",   "xpdiffat15",   to_int),
]

DB_COLS = [m[0] for m in COL_MAP]
PLACEHOLDERS = ",".join("?" * (len(DB_COLS) + 1))   # +1: season_id 单独算
INSERT_SQL = (f"INSERT OR REPLACE INTO match_rows "
              f"({','.join(DB_COLS)}, season_id) VALUES ({PLACEHOLDERS})")

def make_season_id(league: str, year: str, split: str) -> str:
    return f"{league}-{year}-{split}".replace(" ", "_")

def main():
    with step_log("02_import_csv") as st:
        if not CSV_PATH.exists():
            raise FileNotFoundError(CSV_PATH)

        # 先把目标赛季的旧数据清掉（重跑安全）
        # 这里直接清空（46MB 全量重导成本可控，约 90s）
        with db() as c:
            c.execute("DELETE FROM match_rows")
            c.commit()

        rows_in = rows_out = 0
        batch = []
        BATCH_SIZE = 500
        conn = db()
        try:
            with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
                rdr = csv.DictReader(f)
                for row in rdr:
                    rows_in += 1
                    # LPL 全为 partial，但关键二级字段(dpm/vspm/egshare/gspd)有值，
                    # 故放开此过滤，仅排除完全无数据的行；完整度记入 datacompleteness 列。
                    dc = row.get("datacompleteness")
                    if dc not in ("complete", "partial"): continue
                    if row.get("league") not in ALLOWED_LEAGUES: continue
                    if row.get("position") not in ALLOWED_POSITIONS: continue
                    if not row.get("year") or not row.get("split"): continue

                    values = []
                    for db_col, csv_col, conv in COL_MAP:
                        try: v = conv(row.get(csv_col, ""))
                        except Exception: v = None
                        values.append(v)
                    season_id = make_season_id(row["league"], row["year"], row["split"])
                    values.append(season_id)
                    batch.append(values)

                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(INSERT_SQL, batch)
                        rows_out += len(batch)
                        batch.clear()
                if batch:
                    conn.executemany(INSERT_SQL, batch)
                    rows_out += len(batch)
                conn.commit()
        finally:
            conn.close()

        st["rows_in"]  = rows_in
        st["rows_out"] = rows_out
        # 抽样校验
        with db() as c:
            r = c.execute(
                "SELECT COUNT(*) c, COUNT(DISTINCT season_id) s, "
                "COUNT(DISTINCT team_id) t, COUNT(DISTINCT player_id) p FROM match_rows"
            ).fetchone()
            print(f"match_rows: total={r['c']}, seasons={r['s']}, teams={r['t']}, players={r['p']}")

if __name__ == "__main__":
    main()
