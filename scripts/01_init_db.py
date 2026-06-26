"""Step 01 · 初始化 SQLite：执行 db/schema.sql。
重跑安全：所有 CREATE 都是 IF NOT EXISTS。
如需彻底重建，删除 db/radar.db 后再跑。
"""
import sys
from _common import db, SCHEMA, DB_PATH, step_log

def main():
    with step_log("01_init_db") as st:
        sql = SCHEMA.read_text(encoding="utf-8")
        with db() as c:
            c.executescript(sql)
        st["message"] = f"db at {DB_PATH}"
        # 列出表确认
        with db() as c:
            tables = [r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        print("tables:", ", ".join(tables))
        st["rows_out"] = len(tables)

if __name__ == "__main__":
    main()
