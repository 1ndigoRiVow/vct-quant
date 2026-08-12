"""vct_quant.models.player_profile — 选手多维画像 + 选手-战队映射 + 战队地图胜率。

画像字段（VCT 真实统计，聚合自 player_stats）：
  - rounds_by_agent : 选手使用每个特工的上场回合数（round 次数）
  - kda / adr / acs / fk / fd : 击杀死亡助攻、每回合均伤、均分、首杀、首死
  - 常用位置 : 由特工池按回合占比投票出 决斗/先锋/控场/哨卫

配套两张表：
  - player_teams      : 选手 → 当前所属战队（由最近比赛推断）
  - team_map_winrate  : 战队 × 地图 × 对手 的胜率与回合数据
"""
from __future__ import annotations

import json
from datetime import datetime

from ..collectors.vlr_collector import AGENT_ROLES, ROLE_CN
from ..storage import repo

ROLES = ("duelist", "initiator", "controller", "sentinel")


def _kda(kills: int, deaths: int, assists: int) -> float:
    """KDA = (kills + assists) / deaths；零死亡按全击杀+助攻计。"""
    if deaths <= 0:
        return float(kills + assists)
    return round((kills + assists) / deaths, 2)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def build_player_profiles(conn) -> list[dict]:
    """聚合全部选手画像，写回 player_profiles，按 total_rounds 降序返回。"""
    rows = conn.execute(
        """SELECT player_name, team, agent, rounds,
                  kills, deaths, assists, acs, adr, fk, fd, map_id
           FROM player_stats"""
    ).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        p = agg.setdefault(r["player_name"], {
            "player_name": r["player_name"],
            "team": r["team"],
            "rounds_by_agent": {},
            "kills": 0, "deaths": 0, "assists": 0,
            "acs": [], "adr": [], "fk": 0, "fd": 0,
            "maps": set(),
        })
        p["team"] = r["team"] or p["team"]
        rnd = int(r["rounds"] or 0)
        agent = r["agent"] or "Unknown"
        p["rounds_by_agent"][agent] = p["rounds_by_agent"].get(agent, 0) + rnd
        p["kills"] += int(r["kills"] or 0)
        p["deaths"] += int(r["deaths"] or 0)
        p["assists"] += int(r["assists"] or 0)
        p["acs"].append(float(r["acs"] or 0))
        p["adr"].append(float(r["adr"] or 0))
        p["fk"] += int(r["fk"] or 0)
        p["fd"] += int(r["fd"] or 0)
        if r["map_id"]:
            p["maps"].add(r["map_id"])

    profiles = []
    for name, p in agg.items():
        top_agents = sorted(p["rounds_by_agent"].items(), key=lambda kv: kv[1], reverse=True)
        total_rounds = sum(p["rounds_by_agent"].values())

        # 常用位置：按特工回合占比加权投票
        role_rounds: dict[str, int] = {}
        for agent, rnd in p["rounds_by_agent"].items():
            role = AGENT_ROLES.get(agent)
            if role:
                role_rounds[role] = role_rounds.get(role, 0) + rnd
        main_role = max(role_rounds, key=role_rounds.get) if role_rounds else None
        role_share = {
            role: round(rnd / total_rounds, 3) if total_rounds else 0.0
            for role, rnd in sorted(role_rounds.items(), key=lambda kv: kv[1], reverse=True)
        }

        prof = {
            "player_name": name,
            "team": p["team"] or "",
            "main_role": main_role or "unknown",
            "role_share": json.dumps(role_share, ensure_ascii=False),
            "total_rounds": total_rounds,
            "rounds_by_agent": json.dumps(dict(top_agents), ensure_ascii=False),
            "top_agents": json.dumps([
                {"agent": a, "rounds": r,
                 "role": AGENT_ROLES.get(a) or "unknown",
                 "role_cn": ROLE_CN.get(AGENT_ROLES.get(a), "") if AGENT_ROLES.get(a) else "未知"}
                for a, r in top_agents[:5]
            ], ensure_ascii=False),
            "kills": p["kills"],
            "deaths": p["deaths"],
            "assists": p["assists"],
            "kda": _kda(p["kills"], p["deaths"], p["assists"]),
            "acs": _mean(p["acs"]),
            "adr": _mean(p["adr"]),
            "fk": p["fk"],
            "fd": p["fd"],
            "n_maps": len(p["maps"]),
        }
        repo.upsert_player_profile(conn, prof)
        profiles.append(prof)
    conn.commit()
    profiles.sort(key=lambda x: x["total_rounds"], reverse=True)
    return profiles


def build_player_team_map(conn) -> list[dict]:
    """由最近比赛推断选手当前所属战队，写回 player_teams。

    证据：选手近 5 场出场记录的战队归属，取占多数者；归属冲突时保留最近一场。
    """
    rows = conn.execute(
        """SELECT ps.player_name, ps.team, m.date
           FROM player_stats ps
           JOIN matches m ON ps.match_id = m.id
           ORDER BY m.date DESC, ps.player_name"""
    ).fetchall()

    latest: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    for r in rows:
        pn, team, date = r["player_name"], r["team"], r["date"]
        if pn not in latest:
            latest[pn] = team
        ev = evidence.setdefault(pn, {"team": team, "n": 0, "window": []})
        if len(ev["window"]) < 5:
            ev["window"].append(team)
    out = []
    for pn, ev in evidence.items():
        window = ev["window"]
        majority = max(set(window), key=window.count) if window else latest.get(pn, "")
        out.append({
            "player_name": pn,
            "team": majority,
            "evidence": f"近{len(window)}场归属 {dict((t, window.count(t)) for t in set(window))}",
        })
        repo.upsert_player_team(conn, out[-1])
    conn.commit()
    return out


def build_team_map_winrate(conn) -> list[dict]:
    """聚合 战队 × 地图 × 对手 的胜率与回合数，写回 team_map_winrate。

    数据源：maps（每图比分/胜者）+ matches（双方队名）。
    """
    rows = conn.execute(
        """SELECT mp.map_name, mp.team_a_score, mp.team_b_score, mp.winner,
                  m.team_a, m.team_b
           FROM maps mp
           JOIN matches m ON mp.match_id = m.id"""
    ).fetchall()

    agg: dict[tuple, dict] = {}
    for r in rows:
        for side, (team, score, opp, opp_score) in {
            r["team_a"]: (r["team_a"], r["team_a_score"], r["team_b"], r["team_b_score"]),
            r["team_b"]: (r["team_b"], r["team_b_score"], r["team_a"], r["team_a_score"]),
        }.items():
            key = (team, r["map_name"], opp)
            cell = agg.setdefault(key, {"wins": 0, "losses": 0, "rounds_won": 0, "rounds_lost": 0, "n": 0})
            if r["winner"] == team:
                cell["wins"] += 1
            else:
                cell["losses"] += 1
            cell["rounds_won"] += int(score or 0)
            cell["rounds_lost"] += int(opp_score or 0)
            cell["n"] += 1

    out = []
    for (team, map_name, opponent), cell in agg.items():
        rec = {
            "team": team,
            "map_name": map_name,
            "opponent": opponent,
            "wins": cell["wins"],
            "losses": cell["losses"],
            "rounds_won": cell["rounds_won"],
            "rounds_lost": cell["rounds_lost"],
            "n_maps": cell["n"],
            "win_rate": round(cell["wins"] / cell["n"], 3) if cell["n"] else 0.0,
        }
        repo.upsert_team_map_winrate(conn, rec)
        out.append(rec)
    conn.commit()
    out.sort(key=lambda x: (x["team"], x["map_name"], x["opponent"]))
    return out


def build_all(conn) -> dict:
    """一步构建三张表，返回统计摘要。"""
    profiles = build_player_profiles(conn)
    teams = build_player_team_map(conn)
    map_wr = build_team_map_winrate(conn)
    return {
        "profiles": len(profiles),
        "player_teams": len(teams),
        "team_map_winrate": len(map_wr),
    }
