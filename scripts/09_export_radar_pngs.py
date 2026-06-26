#!/usr/bin/env python3
"""Export radar PNGs directly from static JSON data.

Why this exists:
- Previous image exports were produced by browser screenshots.
- The browser flow can get stuck on the default entity (e.g. Kiin)
  if the async UI state has not fully updated before capture.
- This script bypasses the browser entirely and renders each radar image
  from the exported JSON payload, so every PNG is guaranteed to match the
  intended subject.

Outputs:
- PNG files under a chosen output directory (default: /workspace/data/radar_exports_png)
- Filenames use the same readable convention as the old screenshot batch.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WEB_DATA = ROOT / "web" / "data" / "season"
DEFAULT_OUT = Path("/workspace/data/radar_exports_png")

ROLE_ORDER = ["top", "jng", "mid", "bot", "sup"]
ROLE_CN = {"top": "上单", "jng": "打野", "mid": "中单", "bot": "下路", "sup": "辅助"}

LEAGUE_ALIASES = {
    "LCK-2026-Rounds_1-2": "LCK-2026-Rounds_1-2",
    "LPL-2026-Split_2": "LPL-2026-Split_2",
}


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_season_dir(season_id: str) -> Path:
    return WEB_DATA / season_id


def iter_subject_files(season_id: str, kind: str):
    base = get_season_dir(season_id) / kind
    if not base.exists():
        return []
    return sorted(base.glob("*.json"))


def extract_rank_from_list(list_data: dict, entity_id: str, kind: str):
    key = "players" if kind == "player" else "teams"
    for row in list_data.get(key, []):
        if row.get("id") == entity_id:
            return row.get("r_position") or row.get("r_league") or row.get("rank")
    return None


def read_subject(json_path: Path):
    data = load_json(json_path)
    return data


def make_radar_png(subject: dict, out_path: Path):
    dims = subject.get("dimensions", [])
    if not dims:
        raise ValueError(f"No dimensions in {subject.get('name')}")

    labels = [d["label"] for d in dims]
    values = np.array([float(d.get("value", 0)) for d in dims], dtype=float)
    avgs = np.array([float(d.get("avg", 60)) for d in dims], dtype=float)

    # Close the loop.
    labels_c = labels + [labels[0]]
    values_c = np.append(values, values[0])
    avgs_c = np.append(avgs, avgs[0])
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
    angles_c = np.append(angles, angles[0])

    # Colors: match current UI vibe.
    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor("#0f1117")
    ax = plt.subplot(111, polar=True)
    ax.set_facecolor("#111827")

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlim(0, 100)
    ax.set_rticks([20, 40, 60, 80, 100])
    ax.set_yticklabels([])
    ax.set_xticks(angles)
    ax.set_xticklabels([])
    ax.grid(color=(0.58, 0.64, 0.72, 0.10), linewidth=1)

    # Main / avg polygons.
    ax.plot(angles_c, values_c, color="#4f7cff", linewidth=2.5)
    ax.fill(angles_c, values_c, color="#4f7cff", alpha=0.15)
    ax.plot(angles_c, avgs_c, color="#f59e0b", linewidth=2.0, linestyle=(0, (6, 4)))
    ax.fill(angles_c, avgs_c, color="#f59e0b", alpha=0.10)

    # Axis label + numbers.
    label_radius = 107
    for i, (ang, label, v, a) in enumerate(zip(angles, labels, values, avgs)):
        # label placement
        ax.text(
            ang, label_radius,
            label,
            fontsize=15,
            fontweight="bold",
            color="#eef2ff",
            ha="center",
            va="center",
        )
        ax.text(
            ang, 98,
            f"{int(round(v))} / {int(round(a))}",
            fontsize=11,
            color=(0.75, 0.79, 0.85, 1.0),
            ha="center",
            va="center",
        )

    # Title block.
    title = subject.get("name", "—")
    season_id = subject.get("season_id", "")
    tags = subject.get("tags", [])
    tag_text = " · ".join([t.get("label", "") for t in tags if t.get("label")])
    subtitle = f"{tag_text}" if tag_text else season_id
    fig.text(0.05, 0.96, title, color="#ffffff", fontsize=22, fontweight="bold")
    fig.text(0.05, 0.93, subtitle, color="#b6bfd0", fontsize=12)

    # Left stats.
    top_stats = subject.get("top_stats", {})
    ts = top_stats.get("text_score", {})
    sr = top_stats.get("season_rating", {})
    fig.text(0.05, 0.84, top_stats.get("text_score", {}).get("subtitle", "Player Score"), color="#bfc5d2", fontsize=11)
    fig.text(0.05, 0.80, f"{ts.get('value', '—')}", color="#ffffff", fontsize=30, fontweight="bold")
    fig.text(0.05, 0.76, f"#{ts.get('rank', '—')}/{ts.get('total', '—')}", color="#c9a46b", fontsize=12)
    fig.text(0.05, 0.68, top_stats.get("season_rating", {}).get("subtitle", "Season Rating"), color="#bfc5d2", fontsize=11)
    fig.text(0.05, 0.64, f"{sr.get('value', '—')}", color="#ffffff", fontsize=30, fontweight="bold")
    fig.text(0.05, 0.60, f"#{sr.get('rank', '—')}/{sr.get('total', '—')}", color="#c9a46b", fontsize=12)

    # Bottom raw stats.
    raw = subject.get("raw", {})
    raw_lines = []
    if subject.get("type") == "player":
        raw_lines = [
            f"Team: {raw.get('team_name', '—')}",
            f"Games: {raw.get('games', '—')}  W/L: {raw.get('wins', '—')}-{raw.get('losses', '—')}",
            f"Win rate: {round(raw.get('win_rate', 0) * 100):.0f}%",
            f"KDA: {raw.get('kda', '—')}  DPM: {raw.get('avg_dpm', '—')}",
            f"Pool: {raw.get('champion_pool', '—')}  GD@15: {raw.get('avg_gd15', '—')}",
        ]
    else:
        raw_lines = [
            f"Games: {raw.get('games', '—')}  W/L: {raw.get('wins', '—')}-{raw.get('losses', '—')}",
            f"Win rate: {round(raw.get('win_rate', 0) * 100):.0f}%",
            f"Game length: {raw.get('avg_game_length', '—')} min",
            f"GSPD: {raw.get('avg_gspd', '—')}  GPR: {raw.get('avg_gpr', '—')}",
            f"Dragons: {raw.get('avg_dragons', '—')}  Barons: {raw.get('avg_barons', '—')}",
        ]
    y = 0.14
    for line in raw_lines:
        fig.text(0.05, y, line, color="#d7dce7", fontsize=11)
        y -= 0.03

    # Clean polar frame.
    ax.spines["polar"].set_color((1, 1, 1, 0.0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def export_season(season_id: str, out_root: Path):
    season_dir = get_season_dir(season_id)
    list_path = season_dir / "list.json"
    list_data = load_json(list_path)
    out_season = out_root / safe_name(season_id)
    out_season.mkdir(parents=True, exist_ok=True)

    # players
    for item in sorted(list_data.get("players", []), key=lambda x: (x.get("position", ""), -x.get("text_score", 0), x.get("name", ""))):
        pid = item["id"]
        src = season_dir / "player" / f"{safe_name(pid)}.json"
        if not src.exists():
            continue
        subject = read_subject(src)
        pos = item.get("position", "")
        rank = item.get("r_position") or item.get("rank") or ""
        team = item.get("team_name", "")
        name = item.get("name", "")
        # readable filename similar to old screenshot exports
        fn = f"{season_id}__player__rank{int(rank):02d}__{safe_name(team)}__{pos.upper()}__{safe_name(name)}__{safe_name(pid[-8:])}.png"
        make_radar_png(subject, out_season / "player" / fn)

    # teams
    for item in sorted(list_data.get("teams", []), key=lambda x: (-x.get("text_score", 0), x.get("name", ""))):
        tid = item["id"]
        src = season_dir / "team" / f"{safe_name(tid)}.json"
        if not src.exists():
            continue
        subject = read_subject(src)
        rank = item.get("r_league") or item.get("rank") or ""
        name = item.get("name", "")
        fn = f"{season_id}__team__rank{int(rank):02d}__{safe_name(name)}__{safe_name(tid[-8:])}.png"
        make_radar_png(subject, out_season / "team" / fn)

    return out_season


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", action="append", help="Season id to export; repeatable")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    seasons = args.season or ["LCK-2026-Rounds_1-2", "LPL-2026-Split_2"]
    out_root = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    for sid in seasons:
        export_season(sid, out_root)
        print(f"exported {sid}")


if __name__ == "__main__":
    main()
