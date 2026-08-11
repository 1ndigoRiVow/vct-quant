"""vct_quant.models.glicko2 — Glicko-2 选手真实实力评分 V*。

完整实现 Glickman(2013) Glicko-2，含波动率迭代。每个比赛日为一个 rating period。
选手 vs 对手队伍平均评分；胜=1/负=0。online 按 date 顺序更新，period 内对手用快照评分。
"""
from __future__ import annotations

import math
import statistics

from .. import config

_SCALE = 173.7178
_EPS = 1e-6


class Glicko2:
    def __init__(self, tau: float = config.GLICKO2_TAU):
        self.tau = tau

    def default_state(self) -> dict:
        return {
            "rating": config.GLICKO2_DEFAULT_RATING,
            "rd": config.GLICKO2_DEFAULT_RD,
            "vol": config.GLICKO2_DEFAULT_VOL,
        }

    def update(self, state: dict, opponents: list[tuple[float, float, float]]) -> dict:
        """opponents: [(opp_rating, opp_rd, score), ...]。无对手时仅 RD 增长。"""
        mu = (state["rating"] - 1500) / _SCALE
        phi = state["rd"] / _SCALE
        sigma = state["vol"]

        if not opponents:
            phi_new = math.sqrt(phi * phi + sigma * sigma)
            return {"rating": state["rating"], "rd": phi_new * _SCALE, "vol": sigma}

        g_vals, e_vals, scores = [], [], []
        for opp_r, opp_rd, s in opponents:
            mu_j = (opp_r - 1500) / _SCALE
            phi_j = opp_rd / _SCALE
            g = 1.0 / math.sqrt(1 + 3 * phi_j * phi_j / (math.pi * math.pi))
            e = 1.0 / (1 + math.exp(-g * (mu - mu_j)))
            e = min(max(e, 1e-4), 1 - 1e-4)  # 防止确定性退化致 v→∞
            g_vals.append(g)
            e_vals.append(e)
            scores.append(s)

        v_inv = sum(g * g * e * (1 - e) for g, e in zip(g_vals, e_vals))
        v = 1.0 / v_inv if v_inv > 1e-9 else 1e6
        v = min(v, 1e6)
        delta = v * sum(g * (s - e) for g, e, s in zip(g_vals, e_vals, scores))
        delta = max(min(delta, 1e3), -1e3)

        sigma_new = self._new_volatility(sigma, phi, v, delta)
        phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
        phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
        mu_new = mu + phi_new * phi_new * sum(
            g * (s - e) for g, e, s in zip(g_vals, e_vals, scores)
        )
        return {
            "rating": round(mu_new * _SCALE + 1500, 2),
            "rd": round(phi_new * _SCALE, 2),
            "vol": round(sigma_new, 5),
        }

    def _new_volatility(self, sigma, phi, v, delta) -> float:
        a = math.log(sigma * sigma)
        phi2 = phi * phi

        def f(x: float) -> float:
            xc = max(min(x, 30.0), -30.0)  # 夹紧防 exp 溢出
            ex = math.exp(xc)
            denom = 2 * (phi2 + v + ex) ** 2
            num = ex * (delta * delta - phi2 - v - ex)
            return num / denom - (x - a) / (self.tau * self.tau)

        # 初始区间端点
        A = a
        if delta * delta > phi2 + v:
            B = math.log(max(delta * delta - phi2 - v, 1e-12))
        else:
            k = 1
            while f(a - k * self.tau) < 0 and k < 100:
                k += 1
            B = a - k * self.tau

        fa, fb = f(A), f(B)
        # 退化兜底：端点同号则不动波动率
        if not math.isfinite(fa) or not math.isfinite(fb) or fa * fb > 0:
            return max(min(sigma, 0.1), 1e-4)

        # 有界二分，保证解始终在 [lo, hi] 内
        lo, hi = (A, B) if A < B else (B, A)
        flo = fa if lo == A else fb
        for _ in range(200):
            mid = (lo + hi) / 2
            if abs(hi - lo) < _EPS:
                break
            fm = f(mid)
            if fm == 0:
                break
            if flo * fm < 0:
                hi = mid
            else:
                lo, flo = mid, fm
        return max(min(math.exp(mid / 2), 0.1), 1e-4)


def rate_all_players(conn, up_to_date: str | None = None) -> dict[str, dict]:
    """按比赛日顺序在线更新全部选手 Glicko-2 评分，写回 player_ratings，返回快照。

    up_to_date: 仅用 <= 该日期的比赛评分（回测时避免前视偏差）。
    """
    g = Glicko2()
    states: dict[str, dict] = {}

    # 按日期升序取所有比赛
    if up_to_date:
        matches = conn.execute(
            "SELECT id, date, team_a, team_b FROM matches WHERE date<=? ORDER BY date ASC, id ASC",
            (up_to_date,),
        ).fetchall()
    else:
        matches = conn.execute(
            "SELECT id, date, team_a, team_b FROM matches ORDER BY date ASC, id ASC"
        ).fetchall()
    for m in matches:
        maps = conn.execute(
            "SELECT id, winner FROM maps WHERE match_id=? ORDER BY rowid", (m["id"],)
        ).fetchall()
        if not maps:
            continue
        # 该场涉及的选手及其每图胜负
        team_players = {m["team_a"]: [], m["team_b"]: []}
        for mp in maps:
            rows = conn.execute(
                "SELECT DISTINCT player_name, team FROM player_stats WHERE map_id=?", (mp["id"],)
            ).fetchall()
            for r in rows:
                if r["player_name"] not in team_players.setdefault(r["team"], []):
                    team_players.setdefault(r["team"], []).append(r["player_name"])

        # 初始化未登场选手
        for team, pls in team_players.items():
            for p in pls:
                states.setdefault(p, g.default_state())

        # 快照对手队伍平均评分
        snapshot = {p: dict(s) for p, s in states.items()}

        for team, pls in team_players.items():
            opp_team = m["team_b"] if team == m["team_a"] else m["team_a"]
            opp_pls = [p for p in team_players.get(opp_team, []) if p in snapshot]
            if not opp_pls:
                continue
            opp_rating = statistics.mean(snapshot[p]["rating"] for p in opp_pls)
            opp_rd = statistics.mean(snapshot[p]["rd"] for p in opp_pls)
            for p in pls:
                opp_list = []
                for mp in maps:
                    played = conn.execute(
                        "SELECT 1 FROM player_stats WHERE map_id=? AND player_name=? LIMIT 1",
                        (mp["id"], p),
                    ).fetchone()
                    if not played:
                        continue
                    s = 1.0 if mp["winner"] == team else 0.0
                    opp_list.append((opp_rating, opp_rd, s))
                if opp_list:
                    states[p] = g.update(states[p], opp_list)

    # 写回
    from ..storage import repo
    for p, s in states.items():
        repo.upsert_rating(conn, {"player_name": p, **s})
    conn.commit()
    return states
