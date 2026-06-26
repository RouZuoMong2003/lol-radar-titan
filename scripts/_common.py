"""ETL 公共工具：路径常量、DB 连接、日志写表。"""
import os, sqlite3, time, contextlib
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
DB_PATH   = ROOT / "db" / "radar.db"
SCHEMA    = ROOT / "db" / "schema.sql"

# 源 CSV 解析优先级：
#   1. 环境变量 OE_CSV（推荐：export OE_CSV=/path/to/xxx.csv）
#   2. 项目内 data/ 目录下任意 *OraclesElixir*.csv
#   3. 旧的本地开发路径（仅作兜底）
_CSV_NAME = "2026_LoL_esports_match_data_from_OraclesElixir.csv"

def _resolve_csv() -> Path:
    env = os.environ.get("OE_CSV")
    if env:
        return Path(env).expanduser()
    local = ROOT / "data" / _CSV_NAME
    if local.exists():
        return local
    hits = sorted((ROOT / "data").glob("*OraclesElixir*.csv"))
    if hits:
        return hits[0]
    return Path("/workspace/data") / _CSV_NAME

CSV_PATH  = _resolve_csv()

# 仅保留四大一线赛区（用户指定）
# 注意：LPL 在本 CSV 为 partial 数据，缺 golddiffat15/csdiffat15/xpdiffat15，
#       "线上压制"维度将降级为赛区基线（见 metrics.py）
ALLOWED_LEAGUES = {"LCK","LPL","LCS","LEC"}
ALLOWED_POSITIONS = {"top","jng","mid","bot","sup","team"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

@contextlib.contextmanager
def step_log(step_name: str):
    """上下文管理器：记录 ETL 一步耗时与行数到 import_logs。"""
    t0 = time.time()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n=== [{step_name}] start at {started} ===", flush=True)
    state = {"rows_in": 0, "rows_out": 0, "status": "running", "message": ""}
    try:
        yield state
        state["status"] = "success"
    except Exception as e:
        state["status"] = "failed"
        state["message"] = repr(e)
        raise
    finally:
        dt = time.time() - t0
        finished = time.strftime("%Y-%m-%d %H:%M:%S")
        msg = state["message"] or f"{dt:.1f}s"
        print(f"=== [{step_name}] {state['status']} in {dt:.1f}s "
              f"(in={state['rows_in']}, out={state['rows_out']}) ===", flush=True)
        try:
            with db() as c:
                c.execute(
                    "INSERT INTO import_logs(step,started_at,finished_at,rows_in,rows_out,status,message) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (step_name, started, finished, state["rows_in"], state["rows_out"],
                     state["status"], msg),
                )
                c.commit()
        except Exception:
            pass  # 日志失败不影响主流程

def to_int(x, default=None):
    if x is None or x == "": return default
    try: return int(float(x))
    except: return default

def to_float(x, default=None):
    if x is None or x == "": return default
    try: return float(x)
    except: return default

def to_bool_int(x):
    """CSV 里布尔常用 0/1/'TRUE'/'FALSE'/空"""
    if x in (1,"1",True,"TRUE","true"): return 1
    if x in (0,"0",False,"FALSE","false"): return 0
    return None
