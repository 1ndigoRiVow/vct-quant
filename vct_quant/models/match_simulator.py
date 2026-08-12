"""vct_quant.models.match_simulator — FPS 回合制蒙特卡洛比赛模拟器（VCT 版）。

定位：双层预测模型第一层的关键补强。在 Glicko-2 实力评分（内在价值 V*）之外，
额外输出**赛前胜率预测 p̂**——p̂ 是第二层"惊喜度 s = 实际结果 − 赛前预测概率"的核心输入。

引擎思路借鉴 esports-manager（github.com/esports-manager/esports-manager）的
事件驱动 + 加权随机 + 实时胜率框架，改造为无畏契约回合制（BO1 13 胜 / BO3）：

    队伍实力（Glicko-2 队员均值 + 该图历史胜率修正）
      → 逻辑斯蒂映射为单回合胜率 p_round
      → 逐回合随机模拟到 13 胜（领先≥2，12:12 进加时）
      → 蒙特卡洛重复 N 次 → p̂ = A 队胜率 + 95% 置信区间

本模块只"读"数据库取评分/名单/地图胜率，纯模拟计算，不写库；结果去向由调用方决定。
蒙特卡洛内层只算内存（roster/评分/地图修正均在循环外取好），避免每轮重复查 SQL。
"""
from __future__ import annotations

import math
import random

from .. import config
from ..collectors.vlr_collector import TEAMS
from ..storage import repo

# --- 可调超参（优先读 config，缺省用默认值） ---
LOGISTIC_SCALE = getattr(config, "SIM_LOGISTIC_SCALE", 90.0)   # 实力差 → 单回合胜率敏感度
MAP_WEIGHT = getattr(config, "SIM_MAP_WEIGHT", 160.0)          # 地图胜率修正强度
MIN_MAP_SAMPLE = getattr(config, "SIM_MIN_MAP_SAMPLE", 2)      # 地图修正所需最小场次
DEFAULT_RATING = getattr(config, "GLICKO2_DEFAULT_RATING", 1500.0)
N_SIMS = getattr(config, "SIM_N_SIMS", 2000)                   # 蒙特卡洛次数
RD_FLOOR = 25.0      # rd 采样下限：防止过窄
RD_CAP = 70.0        # rd 采样上限：防止初始 rd=350 导致实力方差爆炸
WIN_TARGET = 13      # 单图胜场目标
ROUND_CAP = 30       # 单图回合上限，防加时死循环


def _logistic(x: float, scale: float = LOGISTIC_SCALE) -> float:
    return 1.0 / (1.0 + math.exp(-x / scale))


def _roster(conn, team: str) -> list[str]:
    """队伍现役名单：优先 player_teams 表，回退 TEAMS 常量。"""
    try:
        rows = conn.execute(
            "SELECT player_name FROM player_teams WHERE team=?", (team,)
        ).fetchall()
        names = [r["player_name"] for r in rows]
        if names:
            return names
    except Exception:  # noqa: BLE001
        pass
    return list(TEAMS.get(team, []))


def _map_adjustment(conn, team: str, map_name: str) -> float:
    """该队在该图的历史胜率修正（跨对手聚合，样本不足则 0）。"""
    pool = repo.get_map_pool(conn, team)
    info = pool.get(map_name)
    if not info or (info.get("n_maps") or 0) < MIN_MAP_SAMPLE:
        return 0.0
    return (info["win_rate"] - 0.5) * MAP_WEIGHT


def _base_strength(roster: list[str], ratings: dict, rng, sample_rd: bool) -> float:
    """队员 Glicko-2 均值；sample_rd=True 时按各自 rd 做高斯采样体现评分不确定性。"""
    vals = []
    for p in roster:
        r = ratings.get(p)
        if r is None:
            vals.append(DEFAULT_RATING)
        elif sample_rd and rng is not None:
            spread = max(RD_FLOOR, min(float(r.get("rd", RD_CAP)), RD_CAP))
            vals.append(rng.gauss(r["rating"], spread))
        else:
            vals.append(r["rating"])
    return sum(vals) / max(1, len(vals))


def team_strength(conn, team: str, map_name: str, ratings: dict | None = None,
                  rng=None, sample_rd: bool = False) -> float:
    """队伍回合实力 = 队员 Glicko-2 均值（可选 rd 采样） + 地图胜率修正。"""
    if ratings is None:
        ratings = repo.get_ratings(conn)
    roster = _roster(conn, team)
    return _base_strength(roster, ratings, rng, sample_rd) + _map_adjustment(conn, team, map_name)


def simulate_map(p_round_a: float, rng: random.Random, win_target: int = WIN_TARGET) -> tuple[int, int, bool]:
    """单图模拟：先到 13 且领先≥2 才结束（12:12 进加时）；cap 防死循环。
    返回 (score_a, score_b, a_won)。"""
    a = b = 0
    while True:
        if a >= win_target and a - b >= 2:
            return a, b, True
        if b >= win_target and b - a >= 2:
            return a, b, False
        if a + b >= ROUND_CAP:
            return a, b, a >= b
        if rng.random() < p_round_a:
            a += 1
        else:
            b += 1


def simulate_match(conn, team_a: str, team_b: str, map_name: str,
                   n_sims: int = N_SIMS, seed: int | None = None,
                   best_of: int = 1, sample_rd: bool = True) -> dict:
    """蒙特卡洛模拟一场比赛，返回 A 队胜率 p̂ 与置信区间等。"""
    rng = random.Random(seed)
    ratings = repo.get_ratings(conn)
    roster_a = _roster(conn, team_a)
    roster_b = _roster(conn, team_b)
    map_adj_a = _map_adjustment(conn, team_a, map_name)
    map_adj_b = _map_adjustment(conn, team_b, map_name)
    # 参考实力（不采样），用于展示与基准回合胜率
    sa_ref = _base_strength(roster_a, ratings, None, False) + map_adj_a
    sb_ref = _base_strength(roster_b, ratings, None, False) + map_adj_b
    p_round_ref = _logistic(sa_ref - sb_ref)

    wins_a = 0
    rounds_a = rounds_total = 0
    for _ in range(n_sims):
        sa = _base_strength(roster_a, ratings, rng, sample_rd) + map_adj_a
        sb = _base_strength(roster_b, ratings, rng, sample_rd) + map_adj_b
        pr = _logistic(sa - sb)
        if best_of == 1:
            score_a, score_b, a_won = simulate_map(pr, rng)
            wins_a += 1 if a_won else 0
            rounds_a += score_a
            rounds_total += score_a + score_b
        else:
            need = best_of // 2 + 1
            maps_won = 0
            played = 0
            for _ in range(best_of):
                _, _, a_won = simulate_map(pr, rng)
                played += 1
                if a_won:
                    maps_won += 1
                if maps_won >= need or (maps_won + (best_of - played)) < need:
                    break
            wins_a += 1 if maps_won >= need else 0

    p_win_a = wins_a / n_sims
    se = math.sqrt(p_win_a * (1 - p_win_a) / n_sims)
    return {
        "team_a": team_a, "team_b": team_b, "map_name": map_name,
        "p_win_a": round(p_win_a, 4),
        "ci_low": round(max(0.0, p_win_a - 1.96 * se), 4),
        "ci_high": round(min(1.0, p_win_a + 1.96 * se), 4),
        "n_sims": n_sims, "best_of": best_of,
        "strength_a": round(sa_ref, 1), "strength_b": round(sb_ref, 1),
        "p_round_a": round(p_round_ref, 4),
        "avg_round_share_a": round(rounds_a / rounds_total, 4) if rounds_total else None,
    }


def evaluate_calibration(conn, n_sims: int = 400, seed: int = 7) -> dict:
    """用历史比赛回测模拟器排序能力：逐场预测 p̂，对比实际胜者。

    输出 Brier 分数 / log-loss / 胜负命中率 + 每场明细。
    注意：此处用全量评分预测历史，存在前视偏差，仅验证模拟器区分强弱的能力；
    真正的 out-of-sample 校准需 walk-forward（按赛前数据重算评分），留给 Phase 2 配真实数据。
    """
    matches = conn.execute(
        "SELECT id,team_a,team_b,score_a,score_b FROM matches"
    ).fetchall()
    brier = logloss = correct = 0.0
    n = 0
    details: list[dict] = []
    for i, m in enumerate(matches):
        mp = conn.execute(
            "SELECT map_name FROM maps WHERE match_id=? LIMIT 1", (m["id"],)
        ).fetchone()
        map_name = mp["map_name"] if mp else "Bind"
        res = simulate_match(conn, m["team_a"], m["team_b"], map_name,
                             n_sims=n_sims, seed=(seed or 0) + i, sample_rd=True)
        p = res["p_win_a"]
        actual_a_won = 1.0 if (m["score_a"] or 0) > (m["score_b"] or 0) else 0.0
        brier += (p - actual_a_won) ** 2
        eps = 1e-9
        logloss += -(actual_a_won * math.log(p + eps) + (1 - actual_a_won) * math.log(1 - p + eps))
        correct += 1 if (p > 0.5) == bool(actual_a_won) else 0
        n += 1
        details.append({
            "match_id": m["id"], "team_a": m["team_a"], "team_b": m["team_b"],
            "map": map_name, "p_win_a": p,
            "actual_winner": m["team_a"] if actual_a_won else m["team_b"],
            "hit": bool((p > 0.5) == bool(actual_a_won)),
        })
    return {
        "n_matches": n,
        "brier": round(brier / n, 4) if n else None,
        "logloss": round(logloss / n, 4) if n else None,
        "accuracy": round(correct / n, 4) if n else None,
        "details": details,
    }


if __name__ == "__main__":
    from ..storage import db as dbmod

    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        demo = simulate_match(conn, "EDG", "FPX", "Bind", n_sims=2000, seed=1)
        print("[sim] demo EDG vs FPX @Bind:", demo)
        cal = evaluate_calibration(conn, n_sims=400)
        print(f"[sim] calibration: n={cal['n_matches']} brier={cal['brier']} "
              f"logloss={cal['logloss']} acc={cal['accuracy']}")
    finally:
        conn.close()
