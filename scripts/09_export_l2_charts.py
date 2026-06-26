"""Step 09 · L2 多维数据导出：lol_db.sqlite → web/data/charts/

从 lol_db 直接读：
  - chart_render_spec  → web/data/charts/index.json   （26 张图清单 + 渲染契约）
  - 每张图 primary_view → web/data/charts/{chart_id}.json （数据数组 + 列定义）

输出格式（每张图）：
{
  "chart_id": "CH01",
  "chart_type": "C1",
  "title": "英雄性价比 pickrate × winrate",
  "slots": {...},
  "operators": "...",
  "sample_min": 10,
  "primary_view": "l2_champion_overall",
  "columns": ["champion_name","games_played",...],
  "rows": [[...], [...], ...]    // 二维数组，省体积
}
"""
import os, sys, json, sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import ROOT, step_log

LOL_DB = Path(os.environ.get(
    "LOL_DB",
    "/sdcard/第三宇宙警备站/lol_db/lol_2026.sqlite"
))
OUT = ROOT / "web" / "data" / "charts"

# 业务领域分类（从图表语义反推，符合用户认知）
#   hero=英雄视角，team=战队视角，player=选手视角，
#   game=单局/版本节奏视角，scan=横扫式 KPI 矩阵
DOMAIN_MAP = {
    "CH01": "hero",   "CH02": "hero",   "CH03": "team",
    "CH04": "player", "CH05": "player",
    "CH06": "hero",   "CH07": "hero",   "CH08": "game",
    "CH09": "game",   "CH10": "game",   "CH11": "game",
    "CH12": "team",   "CH13": "player", "CH14": "hero",
    "CH15": "game",   "CH16": "team",   "CH17": "team",
    "CH18": "player", "CH19": "team",
    "CH20": "team",   "CH21": "hero",   "CH22": "player",
    "CH23": "scan",   "CH24": "scan",   "CH25": "scan", "CH26": "scan",
}
DOMAIN_LABEL = {
    "hero":   "英雄",
    "team":   "战队",
    "player": "选手",
    "game":   "比赛节奏",
    "scan":   "横扫矩阵",
}

# 用户友好副标题：一句中文描述「这张图回答什么问题」，不暴露任何数据库 / 视图 / 列名特征
SUBTITLE_MAP = {
    "CH01": "高出场率英雄的胜率分布，定位版本最具性价比的选择",
    "CH02": "高禁用率英雄的胜率表现，识别真正值得 ban 的对象",
    "CH03": "战队节奏（团战频率）与经济压制力的两维定位",
    "CH04": "选手的伤害产出与队内伤害承担，看核心输出位的硬指标",
    "CH05": "选手个人经济与 KDA 的关系，衡量发育与稳定性",
    "CH06": "各版本中热门英雄的出场占比变化",
    "CH07": "各版本中关键英雄的禁用占比变化",
    "CH08": "各版本里先拿小龙 / 先拿峡谷先锋 / 先拿一血等资源的概率走势",
    "CH09": "蓝方胜率随版本的变化，观察阵营平衡",
    "CH10": "比赛平均时长随版本的变化，观察节奏快慢",
    "CH11": "蓝红方在关键时间点的经济差曲线",
    "CH12": "战队在多个维度上的能力画像",
    "CH13": "选手在多个维度上的能力画像",
    "CH14": "英雄在多个维度上的能力画像",
    "CH15": "比赛时长分布，观察整体节奏偏快还是偏慢",
    "CH16": "战队单局控龙数的分布",
    "CH17": "战队拿到不同数量早期资源后的胜率",
    "CH18": "选手 KDA 区间的人数分布",
    "CH19": "15 分钟经济差对最终胜率的影响",
    "CH20": "顶级战队的版本表现趋势，分赛区对比",
    "CH21": "顶级英雄的版本热度趋势，分位置对比",
    "CH22": "顶级选手的版本表现趋势，分位置对比",
    "CH23": "各赛区的比赛体量与节奏概览",
    "CH24": "各位置的整体输出与稳定性概览",
    "CH25": "各版本的核心节奏与热门英雄概览",
    "CH26": "蓝方与红方在胜率 / 击杀 / 经济上的整体差异",
}


def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return p.stat().st_size


def main():
    with step_log("09_export_l2_charts") as st:
        if not LOL_DB.exists():
            raise FileNotFoundError(LOL_DB)

        OUT.mkdir(parents=True, exist_ok=True)
        # 清空旧导出
        for p in OUT.glob("*.json"):
            p.unlink()

        src = sqlite3.connect(LOL_DB)
        src.row_factory = sqlite3.Row

        specs = list(src.execute("""
            SELECT chart_id, chart_type, title, slot1, slot2, slot3, slot4,
                   operators, sample_min, note, primary_view, secondary_view,
                   primary_columns, secondary_columns
            FROM chart_render_spec ORDER BY chart_id
        """))

        # index.json：所有图的元数据
        index = []
        n_rows_total = 0
        for r in specs:
            primary_view = r["primary_view"]
            cols = json.loads(r["primary_columns"]) if r["primary_columns"] else []

            # 取数据
            rows = []
            if primary_view and cols:
                try:
                    rows = [list(row) for row in src.execute(
                        f"SELECT {','.join(cols)} FROM {primary_view}"
                    )]
                except sqlite3.Error as e:
                    print(f"  ⚠️ {r['chart_id']} 读 {primary_view} 失败: {e}")
                    rows = []

            # 副数据源（仅 chart_type=C6 这种复合图会用到）
            secondary = None
            if r["secondary_view"] and r["secondary_columns"]:
                sec_cols = json.loads(r["secondary_columns"])
                try:
                    sec_rows = [list(row) for row in src.execute(
                        f"SELECT {','.join(sec_cols)} FROM {r['secondary_view']}"
                    )]
                    secondary = {"view": r["secondary_view"],
                                 "columns": sec_cols, "rows": sec_rows}
                except sqlite3.Error as e:
                    print(f"  ⚠️ {r['chart_id']} 副视图 {r['secondary_view']} 失败: {e}")

            payload = {
                "chart_id": r["chart_id"],
                "chart_type": r["chart_type"],
                "domain": DOMAIN_MAP.get(r["chart_id"], "scan"),
                "title": r["title"],
                "subtitle": SUBTITLE_MAP.get(r["chart_id"], ""),
                "slots": {"s1": r["slot1"], "s2": r["slot2"],
                          "s3": r["slot3"], "s4": r["slot4"]},
                "operators": r["operators"],
                "sample_min": r["sample_min"],
                "note": r["note"],
                "primary_view": primary_view,
                "columns": cols,
                "rows": rows,
            }
            if secondary:
                payload["secondary"] = secondary

            size = write(f"{r['chart_id']}.json", payload)
            n_rows_total += len(rows)
            index.append({
                "chart_id": r["chart_id"],
                "chart_type": r["chart_type"],
                "domain": payload["domain"],
                "domain_label": DOMAIN_LABEL[payload["domain"]],
                "title": r["title"],
                "subtitle": payload["subtitle"],
                "slots": payload["slots"],
                "operators": r["operators"],
                "sample_min": r["sample_min"],
                "note": r["note"],
                "primary_view": primary_view,
                "n_rows": len(rows),
                "size_bytes": size,
            })

        src.close()

        write("index.json", {
            "version": 2,
            "count": len(index),
            "domains": [{"key": k, "label": v,
                         "count": sum(1 for c in index if c["domain"] == k)}
                        for k, v in DOMAIN_LABEL.items()],
            "charts": index,
        })

        total = sum(p.stat().st_size for p in OUT.glob("*.json"))
        st["rows_out"] = len(index)
        print(f"导出 {len(index)} 张图 / {n_rows_total} 行数据 / 总体积 {total/1024:.1f} KB")


if __name__ == "__main__":
    main()