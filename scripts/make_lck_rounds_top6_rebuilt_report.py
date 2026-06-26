#!/usr/bin/env python3
"""LCK Rounds 1-2 Top6 雷达报告 v2
重构 Teamfight / Macro / Consistency 三个维度：
- 一级字段 -> 二级指标 -> 同位置分位归一化 -> 位置权重加权
- PDF 专用安全排版：雷达无大轴标签，避免文字重叠
"""
import sqlite3, math, html, statistics, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "radar.db"
SEASON = "LCK-2026-Rounds_1-2"
OUT_DIR = ROOT / "reports" / "lck_rounds_top6_rebuilt_metrics_report"
HTML_OUT = OUT_DIR / "lck_rounds_top6_rebuilt_metrics_report.html"
PDF_OUT = OUT_DIR / "lck_rounds_top6_rebuilt_metrics_report.pdf"

POSITIONS = ["top", "jng", "mid", "bot", "sup"]
POS_CN = {"top":"上单", "jng":"打野", "mid":"中单", "bot":"下路", "sup":"辅助"}
POS_EN = {"top":"TOP", "jng":"JUNGLE", "mid":"MID", "bot":"BOT", "sup":"SUPPORT"}

DIMS = [
    ("d_teamfight", "Teamfight", "团战决策"),
    ("d_laning", "Laning", "线上压制"),
    ("d_macro", "Macro", "长线运营"),
    ("d_mechanics", "Mechanics", "操作上限"),
    ("d_consistency", "Consistency", "心态稳定"),
    ("d_meta_adapt", "Adaptation", "版本适应"),
]
DIM_EN = {k:e for k,e,c in DIMS}
DIM_CN = {k:c for k,e,c in DIMS}

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

ROLE_READ = {
    "top": "上单重构后强调：线权能否转化为边线/资源压力，且用高楼层与低波动修正单纯胜率偏差。",
    "jng": "打野重构后强调：参团节奏、资源脚印、视野控制与逆风局 impact floor，而非只看队伍胜负。",
    "mid": "中单重构后强调：输出压力、对线转图、参团效率与稳定高楼层，避免纯 KDA 或胜率误判。",
    "bot": "下路重构后强调：输出兑现、经济转化与团战收割，同时用死亡可靠性约束高风险打法。",
    "sup": "辅助重构后强调：视野/控图、团战参与、承压生存与失利局韧性，弱化不适合辅助的经济/输出绝对值。",
}

# ---------- utils ----------
def esc(x): return html.escape(str(x if x is not None else ""))
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
        # empirical mid-rank percentile; top in n=10 ~=95, n=14 ~=96.4
        it[out_key]=round(100*(less+0.5*equal)/n, 1) if n else 50.0

def weighted(d, weights):
    return round(sum(d[k]*w for k,w in weights.items()))

# ---------- data + rebuilt metrics ----------
def row_metric(row):
    teamkills=safe(row['teamkills'])
    kills=safe(row['kills']); assists=safe(row['assists']); deaths=safe(row['deaths'])
    minutes=max(safe(row['game_length'])/60.0, 1e-6)
    return {
        'kp': (kills+assists)/teamkills if teamkills>0 else 0,
        'kda': (kills+assists)/max(1.0,deaths),
        'dpm': safe(row['dpm']),
        'dshare': safe(row['damageshare']),
        'mitig': safe(row['damagemitigatedperminute']),
        'vspm': safe(row['vspm']), 'wpm': safe(row['wpm']), 'wcpm': safe(row['wcpm']),
        'gd15': safe(row['golddiffat15']), 'csd15': safe(row['csdiffat15']), 'xpd15': safe(row['xpdiffat15']),
        'death_inv': -deaths,
        'deaths': deaths,
        'ka_min': (kills+assists)/minutes,
        'team_kpm': safe(row['team_kpm']),
        'obj': safe(row['firstblood']) + safe(row['firstdragon']) + safe(row['firstherald']) + safe(row['firstbaron']) + safe(row['firsttower']),
        'result': safe(row['result'])*100,
    }

def add_game_impact(rows_by_pos):
    # per-game percentile normalization inside each position
    for pos, rows in rows_by_pos.items():
        metrics=[row_metric(r) for r in rows]
        keys=['kp','kda','dpm','dshare','mitig','vspm','wpm','wcpm','gd15','csd15','xpd15','death_inv','ka_min','team_kpm','obj','result']
        for key in keys:
            vals=[m[key] for m in metrics]
            n=len(vals)
            for m in metrics:
                x=m[key]
                less=sum(1 for z in vals if z<x)
                equal=sum(1 for z in vals if z==x)
                m[key+'_p']=100*(less+0.5*equal)/n if n else 50
        for r,m in zip(rows, metrics):
            output=.55*m['dpm_p']+.45*m['dshare_p']
            lane=.45*m['gd15_p']+.30*m['csd15_p']+.25*m['xpd15_p']
            vision=.45*m['vspm_p']+.25*m['wpm_p']+.30*m['wcpm_p']
            objective=m['obj_p']
            survival=.65*m['kda_p']+.35*m['death_inv_p']
            kp=m['kp_p']; result=m['result_p']
            if pos=='top':
                impact=.25*lane+.25*output+.15*kp+.15*survival+.10*vision+.10*result
            elif pos=='jng':
                impact=.25*kp+.25*objective+.20*vision+.15*survival+.15*result
            elif pos=='mid':
                impact=.25*output+.20*lane+.20*kp+.15*survival+.10*vision+.10*result
            elif pos=='bot':
                impact=.35*output+.20*lane+.20*kp+.15*survival+.10*result
            else:  # sup
                impact=.30*vision+.25*kp+.20*survival+.15*objective+.10*result
            r['_game_impact']=impact

def fetch_and_rebuild():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    # raw match rows grouped by position
    rows_by_pos={}
    for pos in POSITIONS:
        rows=[dict(r) for r in c.execute("""
            SELECT * FROM match_rows
            WHERE season_id=? AND position=? AND player_id IS NOT NULL
        """, (SEASON,pos)).fetchall()]
        rows_by_pos[pos]=rows
    add_game_impact(rows_by_pos)

    all_by_pos={}
    for pos, rows in rows_by_pos.items():
        players={}
        for r in rows:
            pid=r['player_id']
            p=players.setdefault(pid, {'player_id':pid, 'position':pos, 'rows':[]})
            p['rows'].append(r)
        items=[]
        for pid,p in players.items():
            rs=p['rows']; games=len(rs)
            minutes=sum(max(safe(r['game_length'])/60, 1e-6) for r in rs)
            kills=sum(safe(r['kills']) for r in rs); assists=sum(safe(r['assists']) for r in rs); deaths=sum(safe(r['deaths']) for r in rs)
            teamkills=sum(safe(r['teamkills']) for r in rs)
            impacts=[r['_game_impact'] for r in rs]
            losses=[r['_game_impact'] for r in rs if safe(r['result'])<0.5]
            # join player_season for existing dims and names
            ps=c.execute("""
              SELECT ps.*, p.current_handle, t.name team_name
              FROM player_season ps JOIN players p ON p.id=ps.player_id
              LEFT JOIN teams t ON t.id=ps.team_id
              WHERE ps.player_id=? AND ps.season_id=?
            """, (pid,SEASON)).fetchone()
            if not ps: continue
            item=dict(ps)
            item['current_handle']=ps['current_handle']; item['team_name']=ps['team_name']
            item.update({
                'games': games,
                'raw_kp': (kills+assists)/teamkills if teamkills>0 else 0,
                'raw_kda': (kills+assists)/max(1.0,deaths),
                'raw_dpm': mean([safe(r['dpm']) for r in rs]),
                'raw_dshare': mean([safe(r['damageshare']) for r in rs]),
                'raw_mitig': mean([safe(r['damagemitigatedperminute']) for r in rs]),
                'raw_death_pg': deaths/games if games else 0,
                'raw_death_std': stdev([safe(r['deaths']) for r in rs]),
                'raw_multi_pg': sum(safe(r['doublekills'])+2*safe(r['triplekills'])+3*safe(r['quadrakills'])+4*safe(r['pentakills']) for r in rs)/games if games else 0,
                'raw_ka_min': (kills+assists)/minutes if minutes else 0,
                'raw_vspm': mean([safe(r['vspm']) for r in rs]),
                'raw_wpm': mean([safe(r['wpm']) for r in rs]),
                'raw_wcpm': mean([safe(r['wcpm']) for r in rs]),
                'raw_obj': mean([safe(r['firstblood']) + safe(r['firstdragon']) + safe(r['firstherald']) + safe(r['firstbaron']) + safe(r['firsttower']) for r in rs]),
                'raw_egshare': mean([safe(r['earnedgoldshare']) for r in rs]),
                'raw_cspm': mean([safe(r['cspm']) for r in rs]),
                'raw_gd15': mean([safe(r['golddiffat15']) for r in rs]),
                'raw_csd15': mean([safe(r['csdiffat15']) for r in rs]),
                'raw_xpd15': mean([safe(r['xpdiffat15']) for r in rs]),
                'raw_team_kpm': mean([safe(r['team_kpm']) for r in rs]),
                'raw_floor': quantile(impacts, .25),
                'raw_median': quantile(impacts, .50),
                'raw_iqr': quantile(impacts, .75)-quantile(impacts, .25),
                'raw_loss': mean(losses) if losses else quantile(impacts, .50),
                'raw_winrate': mean([safe(r['result']) for r in rs]),
            })
            items.append(item)

        # percentiles for player-level secondaries
        raw_keys=['kp','kda','dpm','dshare','mitig','multi_pg','ka_min','vspm','wpm','wcpm','obj','egshare','cspm','gd15','csd15','xpd15','team_kpm','floor','median','loss','winrate']
        for key in raw_keys:
            percentile_scores(items, 'raw_'+key, key+'_p')
        percentile_scores(items, 'raw_death_pg', 'death_pg_p', inverse=True)
        percentile_scores(items, 'raw_death_std', 'death_std_p', inverse=True)
        percentile_scores(items, 'raw_iqr', 'iqr_p', inverse=True)

        for it in items:
            # 1) Teamfight secondary scores
            tf_comp={
                'participation': it['kp_p'],
                'damage': .55*it['dpm_p']+.45*it['dshare_p'],
                'survival': .60*it['mitig_p']+.40*it['death_pg_p'],
                'conversion': .65*it['kda_p']+.35*it['multi_pg_p'],
                'tempo': it['ka_min_p'],
            }
            # 2) Macro secondary scores
            macro_comp={
                'vision': .45*it['vspm_p']+.25*it['wpm_p']+.30*it['wcpm_p'],
                'objective': it['obj_p'],
                'economy': .40*it['egshare_p']+.30*it['cspm_p']+.30*it['gd15_p'],
                'lane_map': .45*it['gd15_p']+.30*it['csd15_p']+.25*it['xpd15_p'],
                'tempo': .60*it['ka_min_p']+.40*it['team_kpm_p'],
            }
            # 3) Consistency secondary scores
            loss_res=.70*it['loss_p']+.30*it['winrate_p']
            death_rel=.60*it['death_pg_p']+.40*it['death_std_p']
            cons_comp={
                'floor': it['floor_p'],
                'median': it['median_p'],
                'volatility': it['iqr_p'],
                'death': death_rel,
                'loss': loss_res,
            }
            it['_tf_comp']=tf_comp; it['_macro_comp']=macro_comp; it['_cons_comp']=cons_comp
            it['old_teamfight']=it['d_teamfight']; it['old_macro']=it['d_macro']; it['old_consistency']=it['d_consistency']
            it['d_teamfight']=weighted(tf_comp, TF_WEIGHTS[pos])
            it['d_macro']=weighted(macro_comp, MACRO_WEIGHTS[pos])
            it['d_consistency']=weighted(cons_comp, CONS_WEIGHTS)
            vals=[it[k] for k,_,_ in DIMS]
            # revised report score: mean dimensions primary + modest winrate bonus; only for ordering in this report
            it['revised_score']=round(1000 + 6.5*mean(vals) + 140*it['raw_winrate'])
        items.sort(key=lambda x:(x['revised_score'], mean([x[k] for k,_,_ in DIMS])), reverse=True)
        # rerank revised position
        for idx,it in enumerate(items,1): it['revised_rank']=idx
        all_by_pos[pos]=items
    c.close()
    return all_by_pos

# ---------- charts ----------
def points(values, cx=135, cy=135, r=92):
    pts=[]
    for i,v in enumerate(values):
        ang=-math.pi/2 + 2*math.pi*i/6
        rr=r*max(0,min(100,float(v)))/100
        pts.append((cx+math.cos(ang)*rr, cy+math.sin(ang)*rr))
    return pts

def poly(pts): return ' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)

def radar_svg(vals, avgs):
    cx=cy=135; r=92
    grid=''.join(f'<polygon points="{poly(points([lv]*6,cx,cy,r))}" fill="none" stroke="#E7E1D8" stroke-width="1"/>' for lv in [20,40,60,80,100])
    axes=''.join(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#EFE8DE" stroke-width="1"/>' for x,y in points([100]*6,cx,cy,r))
    ps=points(vals,cx,cy,r); pa=points(avgs,cx,cy,r)
    dots=''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#3B5BA5" stroke="#fff" stroke-width="1"/>' for x,y in ps)
    return f'''<svg class="radar" viewBox="0 0 270 270" width="270" height="270" aria-label="radar chart">
      {grid}{axes}
      <polygon points="{poly(pa)}" fill="rgba(217,119,87,.12)" stroke="#D97757" stroke-width="2" stroke-dasharray="5 4"/>
      <polygon points="{poly(ps)}" fill="rgba(59,91,165,.20)" stroke="#3B5BA5" stroke-width="2.6"/>
      {dots}
    </svg>'''

# ---------- report text ----------
def dim_delta(it, key):
    old_key={'d_teamfight':'old_teamfight','d_macro':'old_macro','d_consistency':'old_consistency'}.get(key)
    if not old_key: return ''
    delta=it[key]-it[old_key]
    sign='+' if delta>=0 else ''
    return f"<small class='delta'>{it[old_key]} → {it[key]} ({sign}{delta})</small>"

def top_strengths(it):
    pairs=sorted([(it[k],k) for k,_,_ in DIMS], reverse=True)
    return pairs[:2], pairs[-1]

def player_analysis(it):
    st, wk = top_strengths(it)
    stxt='、'.join(f"{DIM_CN[k]} {v}" for v,k in st)
    wv,wkey=wk
    parts=[f"新版模型下，强项集中在 {stxt}。"]
    if wv<55: parts.append(f"主要短板是 {DIM_CN[wkey]}（{wv}），雷达内缩明显。")
    elif wv<70: parts.append(f"相对短板是 {DIM_CN[wkey]}（{wv}），仍有提升空间。")
    else: parts.append(f"最低维度 {DIM_CN[wkey]} 也有 {wv}，整体轮廓较完整。")
    parts.append(f"三项重构维度变化：团战 {it['old_teamfight']}→{it['d_teamfight']}，运营 {it['old_macro']}→{it['d_macro']}，稳定 {it['old_consistency']}→{it['d_consistency']}。")
    return ''.join(parts)

def position_summary(pos, items):
    top=items[0]
    leaders=[]
    for k,e,c in DIMS:
        b=max(items, key=lambda x:x[k])
        leaders.append(f"{c}: {b['current_handle']}({b[k]})")
    return f"新版排序第一为 {top['current_handle']}，修正评分 {top['revised_score']}。前六内部维度领跑：" + '；'.join(leaders[:4]) + '。'

def avg_dims(items_all):
    return {k:round(mean([it[k] for it in items_all])) for k,_,_ in DIMS}

# ---------- html ----------
def build_html(all_by_pos):
    generated=datetime.now().strftime('%Y-%m-%d %H:%M')
    nav=''.join(f'<a href="#{p}">{POS_EN[p]}</a>' for p in POSITIONS)
    sections=[]
    for pos in POSITIONS:
        items=all_by_pos[pos]
        avgs=avg_dims(items)  # top6 avg for display baseline; report explicitly says top6 baseline. Could use all position, but top6 readability.
        cards=[]
        for it in items[:6]:
            vals=[it[k] for k,_,_ in DIMS]
            avgvals=[avgs[k] for k,_,_ in DIMS]
            rows=''.join(f'''
              <tr><th>{DIM_EN[k]}<span>{DIM_CN[k]}</span></th><td class="self">{it[k]}</td><td class="avg">{avgs[k]}</td><td>{dim_delta(it,k)}</td></tr>
            ''' for k,_,_ in DIMS)
            cards.append(f'''
            <article class="player-card">
              <div class="head"><div><h3>{esc(it['current_handle'])}</h3><p>{esc(it.get('team_name') or '')} · old #{it['r_position']}/{it['total_in_pos']} · revised #{it['revised_rank']}</p></div><div class="score"><b>{it['revised_score']}</b><span>revised score</span></div></div>
              <table class="layout"><tr><td class="radar-cell">{radar_svg(vals, avgvals)}</td><td class="metric-cell"><table class="metrics"><thead><tr><th>Dimension</th><th>Self</th><th>Avg</th><th>Rebuilt Δ</th></tr></thead><tbody>{rows}</tbody></table></td></tr></table>
              <p class="comment">{esc(player_analysis(it))}</p>
            </article>
            ''')
        sections.append(f'''
        <section id="{pos}" class="pos-section">
          <h2><span>{POS_EN[pos]}</span>{POS_CN[pos]} Top 6 · Revised Radar</h2>
          <p class="role">{ROLE_READ[pos]}</p>
          <p class="summary">{position_summary(pos, items[:6])}</p>
          {''.join(cards)}
        </section>
        ''')
    formula_html = build_formula_html()
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>LCK Revised Top6 Radar Report</title>{style()}</head><body><main class="report">
      <header class="hero"><div class="kicker">LCK · ROUNDS 1-2 · REBUILT RADAR MODEL</div><h1>Top 6 Radar Report<br><span>Teamfight / Macro / Consistency Rebuilt</span></h1>
      <p>本版针对 Teamfight、Macro、Consistency 三个原始偏差较大的维度重新建模：一级字段先转为多个二级指标，再在同赛季同位置内做经验分位归一化，最后按位置职责加权。Laning / Mechanics / Adaptation 暂沿用原模型，以便观察三项修正带来的结构变化。</p>
      <div class="legend"><i class="blue"></i>Player <i class="orange"></i>Top6 Average</div><nav>{nav}</nav><p class="time">Generated: {generated}</p></header>
      {''.join(sections)}
      {formula_html}
    </main></body></html>'''

def build_formula_html():
    tf_rows=''.join(f'<tr><th>{POS_EN[p]}</th>' + ''.join(f'<td>{round(w*100)}%</td>' for w in TF_WEIGHTS[p].values()) + '</tr>' for p in POSITIONS)
    macro_rows=''.join(f'<tr><th>{POS_EN[p]}</th>' + ''.join(f'<td>{round(w*100)}%</td>' for w in MACRO_WEIGHTS[p].values()) + '</tr>' for p in POSITIONS)
    cons_row=''.join(f'<td>{round(w*100)}%</td>' for w in CONS_WEIGHTS.values())
    return f'''
    <section class="formula">
      <h2>维度计算原理 · Rebuilt Formula Disclosure</h2>
      <div class="formula-block"><h3>1. Teamfight / 团战决策</h3>
        <p>二级指标：Participation=Pct(KP)；Damage=55%Pct(DPM)+45%Pct(DamageShare)；Survival=60%Pct(DamageMitigatedPM)+40%Pct(-Deaths/Game)；Conversion=65%Pct(KDA)+35%Pct(Weighted Multikill/Game)；Tempo=Pct((Kills+Assists)/Minute)。</p>
        <table class="w"><tr><th>Role</th><th>Part.</th><th>Damage</th><th>Survival</th><th>Conv.</th><th>Tempo</th></tr>{tf_rows}</table>
      </div>
      <div class="formula-block"><h3>2. Macro / 长线运营</h3>
        <p>二级指标：Vision=45%Pct(VSPM)+25%Pct(WPM)+30%Pct(WCPM)；Objective=Pct(first blood/dragon/herald/baron/tower footprint)；Economy=40%Pct(EarnedGoldShare)+30%Pct(CSPM)+30%Pct(GD@15)；LaneMap=45%Pct(GD@15)+30%Pct(CSD@15)+25%Pct(XPD@15)；Tempo=60%Pct((K+A)/Min)+40%Pct(TeamKPM)。</p>
        <table class="w"><tr><th>Role</th><th>Vision</th><th>Obj.</th><th>Economy</th><th>LaneMap</th><th>Tempo</th></tr>{macro_rows}</table>
      </div>
      <div class="formula-block"><h3>3. Consistency / 心态稳定</h3>
        <p>先构造每局 Game Impact：按位置混合输出、对线、视野、参团、目标、存活和结果等一级字段的局内分位；再计算 High Floor(Q25)、Median Impact、Volatility Control(-IQR)、Death Reliability、Loss Resilience。这样弱化纯胜率对强队选手的偏置，更强调稳定高楼层。</p>
        <table class="w"><tr><th>Floor</th><th>Median</th><th>Volatility</th><th>Death Rel.</th><th>Loss Res.</th></tr><tr>{cons_row}</tr></table>
      </div>
      <p class="note">Pct 表示同赛季、同位置经验分位。所有维度仍为 0–100，数值只适合在同位置内部比较。PDF 图中为避免渲染重叠，雷达图只保留几何图形，维度名称与分值在右侧表格展示。</p>
    </section>'''

def style():
    return '''<style>
@page{size:A4;margin:12mm}*{box-sizing:border-box}body{margin:0;background:#F5EDE2;color:#2C2C2C;font-family:"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;font-size:12px}.report{max-width:980px;margin:0 auto;padding:22px}.hero{background:#fff;border-radius:18px;padding:24px;margin-bottom:18px}.kicker{color:#6B5BD6;font-weight:800;letter-spacing:.08em}h1{font-family:Georgia,serif;font-size:34px;line-height:1.06;margin:8px 0}h1 span{font-size:22px;color:#6B5BD6}.hero p{line-height:1.75;color:#555}.legend{margin:10px 0;color:#777}.legend i{display:inline-block;width:26px;height:10px;border-radius:6px;margin:0 6px}.blue{background:rgba(59,91,165,.20);border:2px solid #3B5BA5}.orange{background:rgba(217,119,87,.12);border:2px dashed #D97757}nav{display:flex;gap:8px;flex-wrap:wrap}nav a{background:#EDE8FF;color:#6B5BD6;text-decoration:none;padding:6px 12px;border-radius:999px;font-weight:800}.time{font-size:10px;color:#999}.pos-section{break-before:page;page-break-before:always}h2{font-size:22px;margin:10px 0}h2 span{font-family:Georgia,serif;color:#6B5BD6;font-size:25px;margin-right:8px}.role,.summary{background:rgba(255,255,255,.7);border-left:4px solid #6B5BD6;border-radius:12px;padding:10px 12px;line-height:1.7;color:#555}.player-card{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;margin:12px 0;padding:14px;break-inside:avoid;page-break-inside:avoid}.head{display:flex;justify-content:space-between;border-bottom:1px solid rgba(0,0,0,.08);padding-bottom:8px;margin-bottom:10px}.head h3{font-family:Georgia,serif;font-size:26px;margin:0}.head p{margin:3px 0 0;color:#777}.score{text-align:right;color:#3B5BA5}.score b{font-size:26px;display:block}.score span{font-size:10px;color:#777}.layout{width:100%;border-collapse:collapse;table-layout:fixed}.radar-cell{width:300px;text-align:center;vertical-align:middle}.metric-cell{vertical-align:middle;padding-left:12px}.radar{display:block;margin:auto}.metrics{width:100%;border-collapse:separate;border-spacing:0 5px}.metrics th,.metrics td{text-align:left;padding:6px 7px;background:#F8F6F2}.metrics thead th{background:#ECE7DF;color:#555}.metrics th span{display:block;color:#999;font-weight:400;font-size:10px}.metrics .self{color:#3B5BA5;font-weight:900}.metrics .avg{color:#D97757;font-weight:800}.delta{color:#777;font-size:10px}.comment{margin:9px 0 0;line-height:1.7;color:#555;background:#FBFAF7;border-radius:10px;padding:8px 10px}.formula{break-before:page;page-break-before:always;background:#fff;border-radius:18px;padding:20px}.formula h2{margin-top:0}.formula-block{border-top:1px solid rgba(0,0,0,.1);padding:12px 0}.formula h3{color:#6B5BD6;margin:0 0 6px}.formula p{line-height:1.75;color:#555}.w{width:100%;border-collapse:collapse;margin:8px 0}.w th,.w td{border:1px solid #E5DED4;padding:6px;text-align:center}.w th{background:#F3EFE8}.note{font-size:11px;color:#777}
@media print{.report{padding:0}.hero,.player-card,.formula{box-shadow:none}.pos-section{margin-top:0}}
</style>'''

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_by_pos=fetch_and_rebuild()
    html_doc=build_html(all_by_pos)
    HTML_OUT.write_text(html_doc, encoding='utf-8')
    from weasyprint import HTML
    HTML(filename=str(HTML_OUT)).write_pdf(str(PDF_OUT))
    print(HTML_OUT)
    print(PDF_OUT)

if __name__ == '__main__':
    main()
