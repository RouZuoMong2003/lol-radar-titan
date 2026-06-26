"""6 维度公式 · 唯一实现（ETL 与 API 都从这里 import）。
契约见 docs/SPEC.md §4。
"""
from __future__ import annotations
import math
from statistics import mean, pstdev
from typing import Iterable, Sequence

# --- 工具 ---

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def normalize_range(v, lo, hi):
    """线性映射 [lo,hi] → [0,100]，超出夹紧。"""
    if v is None: return 50
    return clamp(round((v - lo) / (hi - lo) * 100))

def zscore_to_100(value, samples: Sequence[float]) -> int:
    """同组 z-score → 60 + z*15 → clamp[0,100]（旧版，保留兼容）"""
    if value is None or not samples: return 60
    samples = [s for s in samples if s is not None]
    if not samples: return 60
    m = mean(samples)
    s = pstdev(samples) or 1.0
    return clamp(round(60 + (value - m) / s * 15))


def percentile_stretch(value, samples: Sequence[float],
                       lo=15, hi=99, gamma=0.6,
                       top_full=False, small_n=4) -> int:
    """分位数拉伸：组内百分位排名 → pow 增益曲线 → [lo,hi]。
    - 顶尖(分位≈1)自然落到 ~96-99，不强制满格(保留维度形状差异)。
    - 弱项可低至 lo(~15-30)，强弱拉开 → 雷达呈清晰多边形。
    - gamma<1 让中上段更舒展、强者更突出。
    - 小样本组退化为 min-max 线性拉伸到 [40,95]。
    详见 docs/PROMPT-radar-optimize.md
    """
    if value is None: return 60
    vals = sorted(s for s in samples if s is not None)
    n = len(vals)
    if n == 0: return 60
    if n == 1: return hi

    vmin, vmax = vals[0], vals[-1]
    # 小样本：线性拉伸，避免分位极端
    if n < small_n:
        if vmax == vmin: return 70
        t = (value - vmin) / (vmax - vmin)
        return clamp(round(40 + (95 - 40) * t))

    # 百分位排名 p ∈ [0,1]：严格小于的数量 + 一半相等的数量
    less = sum(1 for v in vals if v < value)
    equal = sum(1 for v in vals if v == value)
    p = (less + 0.5 * equal) / n  # 中位排名法
    p_score = lo + (hi - lo) * (p ** gamma)

    # min-max 绝对位置分量：即便同为第一名，raw 更高的维度更突出，
    # 让"全维度第一"的统治级选手也呈现自身强弱形状。
    if vmax > vmin:
        t = (value - vmin) / (vmax - vmin)
    else:
        t = 0.5
    mm_score = lo + (hi - lo) * t

    # 混合：分位为主(70%) + 绝对位置(30%)
    score = 0.7 * p_score + 0.3 * mm_score
    # 组内最强者强制满格（仅当显式开启）
    if top_full and value >= vmax:
        score = 100
    return clamp(round(score))

# --- 选手维度（接收聚合后的 raw dict，返回原始分） ---
# raw 内字段命名见 SPEC §1.1 + scripts/04 输出

def player_dimensions(raw: dict) -> dict:
    """返回 6 个维度的"原始分"（未 z-score），后续在 05 步统一标准化。"""
    def g0(key, d=0):
        """安全取数：键不存在或值为 None 都返回默认值。"""
        v = raw.get(key)
        return d if v is None else v
    g = max(g0("games", 0), 1)
    K = g0("sum_kills"); D = g0("sum_deaths"); A = g0("sum_assists")
    TK = g0("sum_teamkills")
    kp_rate = (K + A) / TK if TK else 0
    kda     = (K + A) / max(D, 1)
    multikill = (g0("sum_double") + 2*g0("sum_triple")
                 + 3*g0("sum_quad") + 5*g0("sum_penta")) / g

    win_rate = g0("wins") / g
    comeback = g0("comeback_rate")
    death_stab = g0("death_stability")
    pool_breadth = min(g0("champion_pool") / 12.0, 1.0)
    latest_wr = raw.get("latest_patch_winrate")
    latest_wr = win_rate if latest_wr is None else latest_wr
    new_champ = g0("new_champ_score")

    is_sup = raw.get("position") == "sup"
    gd_field = raw.get("avg_gd10") if is_sup else raw.get("avg_gd15")
    cd_field = raw.get("avg_csd10") if is_sup else raw.get("avg_csd15")
    xpd_field = g0("avg_xpd15")

    first_resource = g0("first_resource_rate")
    first_tower    = g0("first_tower_rate")

    # LPL(partial) 缺分段差值字段，标记 laning 数据是否可用
    laning_available = gd_field is not None

    # 这些是要做 z-score 的"二级原始值"，返给 05 步分组标准化
    return {
        # 团战
        "_kp": kp_rate * 100,
        "_mitig": g0("avg_mitig"),        # damagemitigatedperminute
        "_first_res": first_resource * 100,
        # 线上（缺失时给 None，05 步会用赛区基线兜底）
        "_gd": gd_field if gd_field is not None else 0,
        "_csd": cd_field if cd_field is not None else 0,
        "_xpd": xpd_field,
        "_laning_ok": laning_available,
        # 长线
        "_vspm": g0("avg_vspm"),
        "_wcpm": g0("avg_wcpm"),
        "_egshare": g0("avg_egshare"),
        "_first_tow": first_tower * 100,
        # 操作
        "_kda": min(kda, 10),                       # 截顶避免极值
        "_dpm": g0("avg_dpm"),
        "_dshare": g0("avg_damageshare"),
        "_multi": multikill,
        # 心态
        "_winrate": win_rate * 100,
        "_comeback": comeback * 100,
        "_dstab": death_stab * 100,
        # 版本
        "_pool": pool_breadth * 100,
        "_latest": latest_wr * 100,
        "_newchamp": new_champ * 100,
    }

# 新版重构三维权重：一级字段 -> 二级指标 -> 同位置分位 -> 位置职责加权
# 用于 Teamfight / Macro / Consistency，详见报告与 DIM_META 公开说明。
REBUILT_DIMS = {"d_teamfight", "d_macro", "d_consistency"}

TF_WEIGHTS = {
    "top": {"participation":.20,"damage":.25,"survival":.25,"conversion":.15,"tempo":.15},
    "jng": {"participation":.30,"damage":.15,"survival":.15,"conversion":.15,"tempo":.25},
    "mid": {"participation":.23,"damage":.32,"survival":.10,"conversion":.20,"tempo":.15},
    "bot": {"participation":.20,"damage":.42,"survival":.05,"conversion":.23,"tempo":.10},
    "sup": {"participation":.38,"damage":.07,"survival":.25,"conversion":.10,"tempo":.20},
}

MACRO_WEIGHTS = {
    "top": {"vision":.15,"objective":.15,"economy":.25,"lane_map":.30,"tempo":.15},
    "jng": {"vision":.25,"objective":.35,"economy":.05,"lane_map":.10,"tempo":.25},
    "mid": {"vision":.20,"objective":.18,"economy":.22,"lane_map":.25,"tempo":.15},
    "bot": {"vision":.10,"objective":.15,"economy":.45,"lane_map":.20,"tempo":.10},
    "sup": {"vision":.45,"objective":.30,"economy":.03,"lane_map":.02,"tempo":.20},
}

CONS_WEIGHTS = {"floor":.30,"median":.20,"volatility":.20,"death":.15,"loss":.15}

def role_weights(kind: str, position: str):
    if kind == "teamfight":
        return TF_WEIGHTS.get(position, TF_WEIGHTS["mid"])
    if kind == "macro":
        return MACRO_WEIGHTS.get(position, MACRO_WEIGHTS["mid"])
    return CONS_WEIGHTS
POSITION_DIM_FORMULA = {
    # 上单：线上压制、操作、抗压(心态)为主；团战中等
    "top": {
        "d_teamfight":   [(0.45,"_kp"),(0.35,"_mitig_n"),(0.20,"_first_res")],
        "d_laning":      [(0.55,"_gd_n"),(0.30,"_csd_n"),(0.15,"_xpd_n")],
        "d_macro":       [(0.30,"_vspm_n"),(0.20,"_wcpm_n"),(0.20,"_egshare_n"),(0.30,"_first_tow")],
        "d_mechanics":   [(0.45,"_kda_n"),(0.30,"_dpm_n"),(0.15,"_dshare_n"),(0.10,"_multi_n")],
        "d_consistency": [(0.45,"_winrate"),(0.35,"_comeback"),(0.20,"_dstab")],
        "d_meta_adapt":  [(0.50,"_pool"),(0.30,"_latest"),(0.20,"_newchamp")],
    },
    # 打野：团战节奏、运营(视野/资源)、版本为主；线上弱化
    "jng": {
        "d_teamfight":   [(0.40,"_kp"),(0.25,"_mitig_n"),(0.35,"_first_res")],
        "d_laning":      [(0.40,"_gd_n"),(0.30,"_csd_n"),(0.30,"_xpd_n")],
        "d_macro":       [(0.40,"_vspm_n"),(0.30,"_wcpm_n"),(0.10,"_egshare_n"),(0.20,"_first_tow")],
        "d_mechanics":   [(0.45,"_kda_n"),(0.25,"_dpm_n"),(0.15,"_dshare_n"),(0.15,"_multi_n")],
        "d_consistency": [(0.50,"_winrate"),(0.30,"_comeback"),(0.20,"_dstab")],
        "d_meta_adapt":  [(0.45,"_pool"),(0.35,"_latest"),(0.20,"_newchamp")],
    },
    # 中单：操作、线上、团战均衡carry型
    "mid": {
        "d_teamfight":   [(0.40,"_kp"),(0.30,"_mitig_n"),(0.30,"_first_res")],
        "d_laning":      [(0.50,"_gd_n"),(0.30,"_csd_n"),(0.20,"_xpd_n")],
        "d_macro":       [(0.35,"_vspm_n"),(0.25,"_wcpm_n"),(0.20,"_egshare_n"),(0.20,"_first_tow")],
        "d_mechanics":   [(0.35,"_kda_n"),(0.35,"_dpm_n"),(0.20,"_dshare_n"),(0.10,"_multi_n")],
        "d_consistency": [(0.50,"_winrate"),(0.30,"_comeback"),(0.20,"_dstab")],
        "d_meta_adapt":  [(0.50,"_pool"),(0.30,"_latest"),(0.20,"_newchamp")],
    },
    # 下路：输出、线上、经济占比为主；视野弱化
    "bot": {
        "d_teamfight":   [(0.45,"_kp"),(0.20,"_mitig_n"),(0.35,"_first_res")],
        "d_laning":      [(0.50,"_gd_n"),(0.35,"_csd_n"),(0.15,"_xpd_n")],
        "d_macro":       [(0.20,"_vspm_n"),(0.15,"_wcpm_n"),(0.45,"_egshare_n"),(0.20,"_first_tow")],
        "d_mechanics":   [(0.30,"_kda_n"),(0.40,"_dpm_n"),(0.20,"_dshare_n"),(0.10,"_multi_n")],
        "d_consistency": [(0.50,"_winrate"),(0.30,"_comeback"),(0.20,"_dstab")],
        "d_meta_adapt":  [(0.50,"_pool"),(0.30,"_latest"),(0.20,"_newchamp")],
    },
    # 辅助：团战、运营(视野/控眼)、心态为主；操作/线上弱化
    "sup": {
        "d_teamfight":   [(0.50,"_kp"),(0.30,"_mitig_n"),(0.20,"_first_res")],
        "d_laning":      [(0.50,"_gd_n"),(0.20,"_csd_n"),(0.30,"_xpd_n")],
        "d_macro":       [(0.45,"_vspm_n"),(0.40,"_wcpm_n"),(0.05,"_egshare_n"),(0.10,"_first_tow")],
        "d_mechanics":   [(0.55,"_kda_n"),(0.10,"_dpm_n"),(0.10,"_dshare_n"),(0.25,"_multi_n")],
        "d_consistency": [(0.45,"_winrate"),(0.35,"_comeback"),(0.20,"_dstab")],
        "d_meta_adapt":  [(0.50,"_pool"),(0.30,"_latest"),(0.20,"_newchamp")],
    },
}

def dim_formula_for(position: str):
    """按位置返回维度权重表，未知位置回退 mid。"""
    return POSITION_DIM_FORMULA.get(position, POSITION_DIM_FORMULA["mid"])

# 哪些"原始项"需要做组内 z-score（标记 _n 后缀）
ZSCORE_FIELDS = ["_mitig", "_gd", "_csd", "_xpd", "_vspm", "_wcpm",
                 "_egshare", "_kda", "_dpm", "_dshare", "_multi"]

# --- 队伍维度 ---
# 按 SPEC §4.2：双源混合，gspd/gpr 直读

def team_dimensions(team_agg: dict, players_avg: dict) -> dict:
    """
    team_agg: 来自 position='team' 行的聚合（avg_gspd / avg_gpr / avg_ckpm / win_rate ...）
    players_avg: 该队 5 选手 d_* 的加权平均字典
    返回 6 个维度的最终 0-100 分（不再做 z-score；队伍间数据量小且 gspd 已是相对量）。
    """
    gspd = team_agg.get("avg_gspd") or 0     # 一般在 [-0.2, 0.2]
    gpr  = team_agg.get("avg_gpr")  or 0     # 一般在 [-1, 1]
    ckpm = team_agg.get("avg_ckpm") or 0     # 击杀节奏

    return {
        "d_teamfight":   round(0.5 * players_avg.get("d_teamfight",60)
                               + 0.5 * normalize_range(ckpm, 0.4, 0.9)),
        "d_laning":      round(players_avg.get("d_laning", 60)),
        # ★ 队伍长线运营 = 直接用 EGR 类 gspd + gpr + 选手 wcpm 加权
        "d_macro":       round(0.6 * normalize_range(gspd, -0.10, 0.10)
                               + 0.2 * normalize_range(gpr,  -0.50, 0.50)
                               + 0.2 * players_avg.get("d_macro", 60)),
        "d_mechanics":   round(players_avg.get("d_mechanics", 60)),
        "d_consistency": round(0.5 * (team_agg.get("win_rate", 0.5) * 100)
                               + 0.5 * players_avg.get("d_consistency", 60)),
        "d_meta_adapt":  round(players_avg.get("d_meta_adapt", 60)),
    }

# --- 综合评分 ---

def scores(d_values: Iterable[float], win_rate: float) -> tuple[int, int]:
    """v2 版顶部双评分（面积主导）。

    Player Score：以"雷达图面积百分比"为主导，配少量上限/短板/胜率修正。
      - area_pct：实际八边形面积 / 满分面积 × 100 —— 真正的"图形最广"
      - ceiling：top2 均值，上限信号
      - floor：最弱项，弱惩罚（避免一项极差被放大）
      - win_rate：小幅赛季结果修正

    Season Rating：在 Player Score 基础上加入胜率系数 + Consistency 稳定性。
    """
    vals = [float(v) for v in d_values]
    n = len(vals)
    if n < 3:
        return 0, 0

    # 雷达图实际面积（正 n 边形相邻顶点夹角 2π/n）
    ang = 2 * math.pi / n
    s_sin = math.sin(ang)
    raw_area = 0.5 * s_sin * sum(vals[i] * vals[(i + 1) % n] for i in range(n))
    max_area = 0.5 * s_sin * n * 100.0 * 100.0
    area_pct = (raw_area / max_area) * 100.0 if max_area > 0 else 0.0

    top2 = sorted(vals, reverse=True)[:2]
    ceiling = sum(top2) / len(top2)
    floor = min(vals)
    consistency = vals[4] if n >= 5 else (sum(vals) / n)

    player_score = round(
        1000
        + 9.0 * area_pct      # 主导：图形面积
        + 1.2 * ceiling       # 上限信号
        + 0.3 * floor         # 弱短板惩罚（原 0.8 过重）
        + 50.0 * win_rate     # 小幅胜率修正
    )
    season_rating = round(player_score * (0.92 + 0.16 * win_rate) + 1.6 * (consistency - 60))
    return player_score, season_rating


# ============================================================
# 维度展示元数据（前端字段名 + 计算原理）
# 第 3 点：六维图加上具体字段名
# 第 7 点：雷达图维度端点计算原理
# ============================================================
DIM_META = {
    "d_teamfight": {
        "label": "团战决策",
        "fields": "参与 · 输出 · 生存 · 转化 · 节奏",
        "formula": "新版：先构造 Participation=KP分位、Damage=0.55×DPM分位+0.45×输出占比分位、Survival=0.60×承伤/减伤分位+0.40×低死亡分位、Conversion=0.65×KDA分位+0.35×多杀分位、Tempo=(K+A)/分钟分位；再按分路职责加权。",
    },
    "d_laning": {
        "label": "线上压制",
        "fields": "金差@15 · 补刀差 · 经验差",
        "formula": "0.5×金币差@15(golddiffat15) + 0.3×补刀差@15(csdiffat15) + 0.2×经验差@15(xpdiffat15)",
    },
    "d_macro": {
        "label": "长线运营",
        "fields": "视野 · 目标 · 经济 · 线转图 · 节奏",
        "formula": "新版：Vision=0.45×VSPM分位+0.25×WPM分位+0.30×WCPM分位；Objective=首血/小龙/先锋/大龙/一塔脚印分位；Economy=0.40×经济占比分位+0.30×CSPM分位+0.30×GD@15分位；LaneMap=0.45×GD@15+0.30×CSD@15+0.25×XPD@15 分位；Tempo=0.60×(K+A)/分钟分位+0.40×TeamKPM分位；再按分路职责加权。",
    },
    "d_mechanics": {
        "label": "操作上限",
        "fields": "KDA · DPM · 输出占比",
        "formula": "0.4×KDA + 0.3×每分钟伤害(dpm) + 0.15×伤害占比(damageshare) + 0.15×多杀分",
    },
    "d_consistency": {
        "label": "心态稳定",
        "fields": "高下限 · 中位影响 · 波动控制 · 死亡可靠 · 逆风韧性",
        "formula": "新版：先按每局一级字段构造 Game Impact（位置内混合输出、对线、视野、参团、目标、存活与结果分位），再计算 HighFloor=Q25、MedianImpact=Q50、VolatilityControl=低IQR分位、DeathReliability=0.60×低死亡分位+0.40×死亡波动低分位、LossResilience=0.70×失利局Impact分位+0.30×胜率分位；最终 0.30×HighFloor+0.20×Median+0.20×Volatility+0.15×Death+0.15×Loss。",
    },
    "d_meta_adapt": {
        "label": "版本适应",
        "fields": "英雄池 · 新版本胜率",
        "formula": "0.5×英雄池广度(champion) + 0.3×最近2补丁胜率(patch) + 0.2×新英雄使用分",
    },
}

# 队伍维度的字段名（部分直读 team 行二级数据）
TEAM_DIM_FIELDS = {
    "d_teamfight": "选手均值 · 击杀节奏(ckpm)",
    "d_laning":    "五人线上均值",
    "d_macro":     "经济差GSPD · 黄金比率GPR · 控眼",
    "d_mechanics": "五人操作均值",
    "d_consistency":"胜率 · 选手均值",
    "d_meta_adapt": "五人版本均值",
}

def dim_meta_for(position: str):
    """按位置返回维度展示元数据(label+fields)，体现差异化侧重。
    fields 文案随位置变化，让用户直观看到不同定位的评判侧重。"""
    base = {k: dict(v) for k, v in DIM_META.items()}
    overrides = {
        "top": {
            "d_laning":    "金差@15 · 补刀差(强权重)",
            "d_teamfight": "参与 · 输出 · 生存 · 转化",
            "d_macro":     "线转图 · 经济 · 视野",
            "d_consistency":"高下限 · 低波动 · 死亡可靠",
        },
        "jng": {
            "d_teamfight": "参团节奏 · 资源团 · 生存",
            "d_macro":     "目标脚印 · 视野 · 节奏",
            "d_laning":    "Gank前期差@15",
            "d_consistency":"Impact下限 · 失利局韧性",
        },
        "bot": {
            "d_mechanics": "DPM · 输出占比(强权重)",
            "d_teamfight": "输出 · 转化 · 参团",
            "d_macro":     "经济转化 · 线转图 · 节奏",
            "d_consistency":"死亡可靠 · 高下限",
        },
        "sup": {
            "d_macro":     "视野 · 控眼 · 目标脚印(强权重)",
            "d_teamfight": "KP · 生存 · 节奏",
            "d_mechanics": "KDA · 参团(弱化输出)",
            "d_consistency":"低死亡波动 · 失利局韧性",
        },
    }
    for dk, txt in overrides.get(position, {}).items():
        base[dk]["fields"] = txt
    return base

NORMALIZE_NOTE = (
    "新版模型：Teamfight、Macro、Consistency 三维已升级为『一级字段 → 二级指标 → 同赛季同位置经验分位 → 分路职责权重』；"
    "Laning、Mechanics、Adaptation 仍沿用同位置分位拉伸模型。所有端点为 0–100，同位置内部可比。"
    "顶部 Player Score = 新版六维均值 + 最强两项上限 + 最低项下限 + 小幅胜率校正；"
    "Season Rating 在 Player Score 基础上加入赛季胜率结果系数与 Consistency 稳定性修正。"
)
