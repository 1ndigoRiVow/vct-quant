"""vct_quant.models.backtest — walk-forward 回测与策略绩效。

简化逻辑：按比赛日推进，每个时点用"截至当日"数据重算 Δ，生成信号；
以"下一时点选手 ACS 变化"作为收益代理，评估信号方向命中率与组合回撤。
"""
from __future__ import annotations

from datetime import datetime

from .. import config
from ..features.match_features import player_match_features
from ..features.sentiment_features import player_sentiment_features
from ..features.fusion import classify_delta
from ..models.glicko2 import rate_all_players
from ..models.sentiment_pricing import market_price


def walk_forward(conn) -> dict:
    """对历史每个比赛日重算信号并评估。返回绩效指标。"""
    dates = [r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM matches ORDER BY date ASC"
    ).fetchall()]
    if len(dates) < 2:
        return {"n_dates": len(dates), "hit_rate": 0.0, "max_drawdown": 0.0, "trades": 0}

    trades = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0

    for i in range(len(dates) - 1):
        d = dates[i]
        d_next = dates[i + 1]
        # 用截至 d 的数据重算评分（避免前视偏差）
        ratings = rate_all_players(conn, up_to_date=d)
        # 取该日有数据的选手
        players = [r["player_name"] for r in conn.execute(
            """SELECT DISTINCT player_name FROM player_stats ps
               JOIN matches m ON m.id=ps.match_id WHERE m.date<=?""", (d,)
        ).fetchall()]
        for p in players:
            mf = player_match_features(conn, p)
            sf = player_sentiment_features(conn, p)
            if not mf:
                continue
            v_star = ratings.get(p, {}).get("rating", 1500.0)
            p_market = market_price(sf, mf)
            delta = p_market - v_star
            label, _ = classify_delta(delta)
            if label == "均衡":
                continue
            # 下一时点收益代理：选手 ACS 变化方向
            next_acs = _next_acs(conn, p, d_next)
            cur_acs = mf["acs"]
            ret = (next_acs - cur_acs) / max(cur_acs, 1.0) if next_acs else 0.0
            # 信号方向：BUY 期望 ret>0, SELL 期望 ret<0
            sig = 1 if label == "洼地" else -1
            hit = (sig * ret) > 0
            trades.append({"date": d, "player": p, "label": label, "ret": round(ret, 4), "hit": hit})
            # 组合等权 PnL
            equity *= (1 + 0.1 * sig * ret)  # 10% 仓位
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)

    hits = sum(1 for t in trades if t["hit"])
    hit_rate = hits / len(trades) if trades else 0.0
    return {
        "n_dates": len(dates),
        "trades": len(trades),
        "hit_rate": round(hit_rate, 3),
        "equity_curve_end": round(equity, 3),
        "max_drawdown": round(max_dd, 3),
    }


def _next_acs(conn, player_name: str, date: str) -> float:
    row = conn.execute(
        """SELECT AVG(ps.acs) AS a FROM player_stats ps
           JOIN matches m ON m.id=ps.match_id WHERE ps.player_name=? AND m.date=?""",
        (player_name, date),
    ).fetchone()
    return float(row["a"]) if row and row["a"] is not None else 0.0
