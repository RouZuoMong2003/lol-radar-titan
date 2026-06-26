"""Step 05 · 同 (league, season, position) 分组归一化 + 新版三维重构 + 排名

新版正式合入原版雷达：
- Laning / Mechanics / Adaptation：沿用原 ETL 位置权重 + 分位拉伸。
- Teamfight / Macro / Consistency：从更多一级字段构造二级指标，先做同赛季同位置经验分位，
  再按位置职责加权。
- text_score / season_rating：基于新版 6 维 + 胜率重算。
"""
import sys, pickle, math, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from collections import defaultdict
from _common import db, step_log, ROOT
import metrics as M

STAGE = ROOT / "db" / "_stage_player_raw.pkl"
DIMS = ["d_teamfight","d_laning","d_macro","d_mechanics","d_consistency","d_meta_adapt"]
REBUILT = {"d_teamfight", "d_macro", "d_consistency"}

# ---------- small math helpers ----------
def safe(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except Exception:
        return default

def mean(xs):
    xs=[x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else 0.0

def stdev(xs):
    xs=[x for x in xs if x is not None]
    return statistics.pstdev(xs) if len(xs)>1 else 0.0

def quantile(xs, q):
    xs=sorted([x for x in xs if x is not None])
    if not xs: return 0.0
    if len(xs)==1: return xs[0]
    pos=(len(xs)-1)*q
    lo=math.floor(pos); hi=math.ceil(pos)
    if lo==hi: return xs[lo]
    return xs[lo]*(hi-pos)+xs[hi]*(pos-lo)

def percentile_scores(items, raw_key, out_key, inverse=False):
    vals=[]
    for it in items:
        v=it.get(raw_key)
        vals.append(-v if inverse else v)
    n=len(vals)
    for it in items:
        v=it.get(raw_key)
        x=-v if inverse else v
        less=sum(1 for z in vals if z < x)
        equal=sum(1 for z in vals if z == x)
        it[out_key]=100*(less+0.5*equal)/n if n else 50.0

def weighted(comp, weights):
    return round(sum(comp[k]*w for k,w in weights.items()))

# ---------- rebuilt per-game / per-player metrics ----------
def row_metric(row):
    teamkills=safe(row["teamkills"])
    kills=safe(row["kills"]); assists=safe(row["assists"]); deaths=safe(row["deaths"])
    minutes=max(safe(row["game_length"])/60.0, 1e-6)
    return {
        "kp": (kills+assists)/teamkills if teamkills>0 else 0,
        "kda": (kills+assists)/max(1.0,deaths),
        "dpm": safe(row["dpm"]),
        "dshare": safe(row["damageshare"]),
        "mitig": safe(row["damagemitigatedperminute"]),
        "vspm": safe(row["vspm"]), "wpm": safe(row["wpm"]), "wcpm": safe(row["wcpm"]),
        "gd15": safe(row["golddiffat15"]), "csd15": safe(row["csdiffat15"]), "xpd15": safe(row["xpdiffat15"]),
        "death_inv": -deaths,
        "deaths": deaths,
        "ka_min": (kills+assists)/minutes,
        "team_kpm": safe(row["team_kpm"]),
        "obj": safe(row["firstblood"]) + safe(row["firstdragon"]) + safe(row["firstherald"]) + safe(row["firstbaron"]) + safe(row["firsttower"]),
        "result": safe(row["result"])*100,
    }

def add_game_impact(rows, pos):
    metrics=[row_metric(r) for r in rows]
    keys=["kp","kda","dpm","dshare","mitig","vspm","wpm","wcpm","gd15","csd15","xpd15","death_inv","ka_min","team_kpm","obj","result"]
    for key in keys:
        vals=[m[key] for m in metrics]
        n=len(vals)
        for m in metrics:
            x=m[key]
            less=sum(1 for z in vals if z<x)
            equal=sum(1 for z in vals if z==x)
            m[key+"_p"]=100*(less+0.5*equal)/n if n else 50
    for r,m in zip(rows, metrics):
        output=.55*m["dpm_p"]+.45*m["dshare_p"]
        lane=.45*m["gd15_p"]+.30*m["csd15_p"]+.25*m["xpd15_p"]
        vision=.45*m["vspm_p"]+.25*m["wpm_p"]+.30*m["wcpm_p"]
        objective=m["obj_p"]
        survival=.65*m["kda_p"]+.35*m["death_inv_p"]
        kp=m["kp_p"]; result=m["result_p"]
        if pos=="top":
            impact=.25*lane+.25*output+.15*kp+.15*survival+.10*vision+.10*result
        elif pos=="jng":
            impact=.25*kp+.25*objective+.20*vision+.15*survival+.15*result
        elif pos=="mid":
            impact=.25*output+.20*lane+.20*kp+.15*survival+.10*vision+.10*result
        elif pos=="bot":
            impact=.35*output+.20*lane+.20*kp+.15*survival+.10*result
        else:  # sup
            impact=.30*vision+.25*kp+.20*survival+.15*objective+.10*result
        r["_game_impact"]=impact

def build_rebuilt_dims_for_group(conn, items):
    """返回 player_id -> {d_teamfight,d_macro,d_consistency}。"""
    if not items:
        return {}
    sid=items[0]["season_id"]; pos=items[0]["position"]
    pids={it["player_id"] for it in items}
    rows=[dict(r) for r in conn.execute("""
        SELECT * FROM match_rows
        WHERE season_id=? AND position=? AND player_id IS NOT NULL
    """, (sid,pos)).fetchall()]
    rows=[r for r in rows if r["player_id"] in pids]
    if not rows:
        return {}
    add_game_impact(rows, pos)

    by_player=defaultdict(list)
    for r in rows:
        by_player[r["player_id"]].append(r)

    agg_items=[]
    for it in items:
        pid=it["player_id"]
        rs=by_player.get(pid, [])
        if not rs:
            continue
        games=len(rs)
        minutes=sum(max(safe(r["game_length"])/60,1e-6) for r in rs)
        kills=sum(safe(r["kills"]) for r in rs)
        assists=sum(safe(r["assists"]) for r in rs)
        deaths=sum(safe(r["deaths"]) for r in rs)
        teamkills=sum(safe(r["teamkills"]) for r in rs)
        impacts=[r["_game_impact"] for r in rs]
        losses=[r["_game_impact"] for r in rs if safe(r["result"])<0.5]
        agg={"player_id":pid, "position":pos,
            "raw_kp": (kills+assists)/teamkills if teamkills>0 else 0,
            "raw_kda": (kills+assists)/max(1.0,deaths),
            "raw_dpm": mean([safe(r["dpm"]) for r in rs]),
            "raw_dshare": mean([safe(r["damageshare"]) for r in rs]),
            "raw_mitig": mean([safe(r["damagemitigatedperminute"]) for r in rs]),
            "raw_death_pg": deaths/games if games else 0,
            "raw_death_std": stdev([safe(r["deaths"]) for r in rs]),
            "raw_multi_pg": sum(safe(r["doublekills"])+2*safe(r["triplekills"])+3*safe(r["quadrakills"])+4*safe(r["pentakills"]) for r in rs)/games if games else 0,
            "raw_ka_min": (kills+assists)/minutes if minutes else 0,
            "raw_vspm": mean([safe(r["vspm"]) for r in rs]),
            "raw_wpm": mean([safe(r["wpm"]) for r in rs]),
            "raw_wcpm": mean([safe(r["wcpm"]) for r in rs]),
            "raw_obj": mean([safe(r["firstblood"])+safe(r["firstdragon"])+safe(r["firstherald"])+safe(r["firstbaron"])+safe(r["firsttower"]) for r in rs]),
            "raw_egshare": mean([safe(r["earnedgoldshare"]) for r in rs]),
            "raw_cspm": mean([safe(r["cspm"]) for r in rs]),
            "raw_gd15": mean([safe(r["golddiffat15"]) for r in rs]),
            "raw_csd15": mean([safe(r["csdiffat15"]) for r in rs]),
            "raw_xpd15": mean([safe(r["xpdiffat15"]) for r in rs]),
            "raw_team_kpm": mean([safe(r["team_kpm"]) for r in rs]),
            "raw_floor": quantile(impacts,.25),
            "raw_median": quantile(impacts,.50),
            "raw_iqr": quantile(impacts,.75)-quantile(impacts,.25),
            "raw_loss": mean(losses) if losses else quantile(impacts,.50),
            "raw_winrate": mean([safe(r["result"]) for r in rs]),
        }
        agg_items.append(agg)

    raw_keys=["kp","kda","dpm","dshare","mitig","multi_pg","ka_min","vspm","wpm","wcpm","obj","egshare","cspm","gd15","csd15","xpd15","team_kpm","floor","median","loss","winrate"]
    for key in raw_keys:
        percentile_scores(agg_items, "raw_"+key, key+"_p")
    percentile_scores(agg_items, "raw_death_pg", "death_pg_p", inverse=True)
    percentile_scores(agg_items, "raw_death_std", "death_std_p", inverse=True)
    percentile_scores(agg_items, "raw_iqr", "iqr_p", inverse=True)

    out={}
    for it in agg_items:
        tf={
            "participation": it["kp_p"],
            "damage": .55*it["dpm_p"]+.45*it["dshare_p"],
            "survival": .60*it["mitig_p"]+.40*it["death_pg_p"],
            "conversion": .65*it["kda_p"]+.35*it["multi_pg_p"],
            "tempo": it["ka_min_p"],
        }
        macro={
            "vision": .45*it["vspm_p"]+.25*it["wpm_p"]+.30*it["wcpm_p"],
            "objective": it["obj_p"],
            "economy": .40*it["egshare_p"]+.30*it["cspm_p"]+.30*it["gd15_p"],
            "lane_map": .45*it["gd15_p"]+.30*it["csd15_p"]+.25*it["xpd15_p"],
            "tempo": .60*it["ka_min_p"]+.40*it["team_kpm_p"],
        }
        cons={
            "floor": it["floor_p"],
            "median": it["median_p"],
            "volatility": it["iqr_p"],
            "death": .60*it["death_pg_p"]+.40*it["death_std_p"],
            "loss": .70*it["loss_p"]+.30*it["winrate_p"],
        }
        out[it["player_id"]]={
            "d_teamfight": weighted(tf, M.role_weights("teamfight", pos)),
            "d_macro": weighted(macro, M.role_weights("macro", pos)),
            "d_consistency": weighted(cons, M.role_weights("consistency", pos)),
        }
    return out

# ---------- main ----------
def main():
    with step_log("05_normalize") as st:
        if not STAGE.exists():
            raise FileNotFoundError("先运行 04_aggregate_player.py")
        with open(STAGE, "rb") as f:
            raw_list = pickle.load(f)

        groups = defaultdict(list)
        for r in raw_list:
            league = r["season_id"].split("-", 1)[0]
            r["_league"] = league
            groups[(league, r["season_id"], r["position"])].append(r)

        conn = db()

        for grp_key, items in groups.items():
            # 1) 旧模型分量标准化：供未重构三维继续使用
            for fld in M.ZSCORE_FIELDS:
                samples = [it["_dim_inputs"][fld] for it in items]
                for it in items:
                    v = it["_dim_inputs"][fld]
                    it["_dim_inputs"][fld + "_n"] = M.zscore_to_100(v, samples)

            for it in items:
                di = it["_dim_inputs"]
                pos = it.get("position", "mid")
                formula = M.dim_formula_for(pos)
                it["_dim_raw"] = {}
                for dim_key, terms in formula.items():
                    it["_dim_raw"][dim_key] = sum(w * di[k] for w, k in terms)
                if not di.get("_laning_ok", True):
                    it["_dim_raw"]["d_laning"] = None

            for dim_key in DIMS:
                samples = [it["_dim_raw"][dim_key] for it in items
                           if it["_dim_raw"].get(dim_key) is not None]
                for it in items:
                    rawv = it["_dim_raw"].get(dim_key)
                    it["_dim_raw"][dim_key + "_final"] = 55 if rawv is None else M.percentile_stretch(rawv, samples)

            # 2) 新版三维：覆盖 teamfight / macro / consistency
            rebuilt = build_rebuilt_dims_for_group(conn, items)
            for it in items:
                rb = rebuilt.get(it["player_id"])
                if not rb:
                    continue
                for dk in REBUILT:
                    it["_dim_raw"][dk + "_final"] = rb[dk]

        # 写回 player_season + 新版评分
        for r in raw_list:
            dr = r["_dim_raw"]
            d = {k: dr[k + "_final"] for k in DIMS}
            text, season_rating = M.scores(d.values(), r["win_rate"])
            conn.execute("""
              UPDATE player_season SET
                d_teamfight=?, d_laning=?, d_macro=?, d_mechanics=?,
                d_consistency=?, d_meta_adapt=?,
                text_score=?, season_rating=?
              WHERE player_id=? AND season_id=?
            """, (
                d["d_teamfight"], d["d_laning"], d["d_macro"], d["d_mechanics"],
                d["d_consistency"], d["d_meta_adapt"], text, season_rating,
                r["player_id"], r["season_id"],
            ))

        conn.execute("""
          WITH ranked AS (
            SELECT player_id, season_id,
                   RANK() OVER (PARTITION BY season_id, position ORDER BY text_score DESC) rk,
                   COUNT(*) OVER (PARTITION BY season_id, position) cnt
            FROM player_season
          )
          UPDATE player_season SET
            r_position = (SELECT rk  FROM ranked r
                          WHERE r.player_id=player_season.player_id AND r.season_id=player_season.season_id),
            total_in_pos = (SELECT cnt FROM ranked r
                            WHERE r.player_id=player_season.player_id AND r.season_id=player_season.season_id)
        """)
        conn.commit()
        st["rows_out"] = len(raw_list)

        print("\n--- LCK Rounds 1-2 新版模型各位置 Top3 ---")
        for row in conn.execute("""
          SELECT ps.position, p.current_handle, ps.text_score, ps.season_rating, ps.r_position,
                 ps.d_teamfight, ps.d_laning, ps.d_macro, ps.d_mechanics, ps.d_consistency, ps.d_meta_adapt
          FROM player_season ps JOIN players p ON p.id=ps.player_id
          WHERE ps.season_id='LCK-2026-Rounds_1-2' AND ps.r_position<=3
          ORDER BY ps.position, ps.r_position
        """):
            print(f"  {row['position']:<3} #{row['r_position']} {row['current_handle']:<10} "
                  f"score={row['text_score']} sr={row['season_rating']} "
                  f"d=[{row['d_teamfight']},{row['d_laning']},{row['d_macro']},{row['d_mechanics']},{row['d_consistency']},{row['d_meta_adapt']}]")
        conn.close()

if __name__ == "__main__":
    main()
