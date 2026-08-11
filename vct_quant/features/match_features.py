"""vct_quant.features.match_features — 比赛硬指标滚动特征 + 状态动量 + 对手强度调整。"""
from __future__ import annotations

import statistics

from .. import config


def player_match_features(conn, player_name: str, window: int = config.ROLL_WINDOW_MAPS):
    """返回选手近 window 张图的滚动特征；无数据返回 None。"""
    rows = conn.execute(
        """SELECT ps.*, m.winner, m.map_name, mt.team_a, mt.team_b, mt.date
           FROM player_stats ps
           JOIN maps m ON m.id = ps.map_id
           JOIN matches mt ON mt.id = ps.match_id
           WHERE ps.player_name = ?
           ORDER BY mt.date DESC, ps.rowid DESC LIMIT ?""",
        (player_name, window * 3),
    ).fetchall()
    if not rows:
        return None

    recent = rows[:window]
    acs = [r["acs"] for r in recent if r["acs"] is not None]
    kast = [r["kast"] for r in recent if r["kast"] is not None]
    fk = [r["fk"] for r in recent]
    fd = [r["fd"] for r in recent]
    adr = [r["adr"] for r in recent if r["adr"] is not None]
    hs = [r["hs_pct"] for r in recent if r["hs_pct"] is not None]

    wins = sum(1 for r in recent if r["winner"] == r["team"])
    win_rate = wins / len(recent)

    # 状态动量：近半 vs 远半 ACS 差
    half = max(1, len(acs) // 2)
    acs_recent = statistics.mean(acs[:half]) if len(acs) >= half else (statistics.mean(acs) if acs else 0)
    acs_old = statistics.mean(acs[half:]) if len(acs) > half else acs_recent
    form_momentum = acs_recent - acs_old

    # 对手强度：用历史评分表均值，缺失给中性默认
    opp_strength = _opponent_strength(conn, player_name, recent)

    return {
        "player_name": player_name,
        "team": recent[0]["team"],
        "n_maps": len(recent),
        "acs": round(statistics.mean(acs), 1) if acs else 0.0,
        "kast": round(statistics.mean(kast), 3) if kast else 0.0,
        "fk_avg": round(statistics.mean(fk), 2) if fk else 0.0,
        "fd_avg": round(statistics.mean(fd), 2) if fd else 0.0,
        "adr": round(statistics.mean(adr), 1) if adr else 0.0,
        "hs_pct": round(statistics.mean(hs), 1) if hs else 0.0,
        "win_rate": round(win_rate, 3),
        "form_momentum": round(form_momentum, 2),
        "opp_strength": round(opp_strength, 1),
    }


def _opponent_strength(conn, player_name, recent_rows) -> float:
    """对手队伍平均评分（来自 player_ratings，缺失用默认 1500）。"""
    own_team = recent_rows[0]["team"]
    row0 = recent_rows[0]
    opp_team = row0["team_b"] if row0["team_a"] == own_team else row0["team_a"]
    if not opp_team:
        return config.GLICKO2_DEFAULT_RATING
    rows = conn.execute(
        """SELECT AVG(rating) AS a FROM player_ratings
           WHERE player_name IN (SELECT DISTINCT player_name FROM player_stats WHERE team=?)""",
        (opp_team,),
    ).fetchone()
    val = rows["a"] if rows and rows["a"] is not None else config.GLICKO2_DEFAULT_RATING
    return float(val)


def team_map_features(conn, team: str) -> dict:
    """战队地图胜率与阵容偏好。"""
    rows = conn.execute(
        """SELECT m.map_name, m.winner FROM maps m
           JOIN matches mt ON mt.id=m.match_id
           WHERE mt.team_a=? OR mt.team_b=?""",
        (team, team),
    ).fetchall()
    if not rows:
        return {"team": team, "n_maps": 0, "win_rate": 0.0, "map_winrate": {}}
    total = len(rows)
    wins = sum(1 for r in rows if r["winner"] == team)
    per_map: dict[str, dict] = {}
    for r in rows:
        m = r["map_name"]
        d = per_map.setdefault(m, {"win": 0, "n": 0})
        d["n"] += 1
        d["win"] += 1 if r["winner"] == team else 0
    map_winrate = {m: round(d["win"] / d["n"], 3) for m, d in per_map.items()}
    return {"team": team, "n_maps": total, "win_rate": round(wins / total, 3), "map_winrate": map_winrate}
