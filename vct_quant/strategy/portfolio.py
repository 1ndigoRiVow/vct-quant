"""vct_quant.strategy.portfolio — 多空组合构建：多头洼地 + 空头泡沫，近似 dollar-neutral。"""
from __future__ import annotations

from .risk import size_position


def build_portfolio(signals: list[dict], top_n: int = 5) -> dict:
    """取信心最强的 top_n 买入与 top_n 卖出，等权基础上按 strength 微调。"""
    buys = [s for s in signals if s["signal"] == "BUY"][:top_n]
    sells = [s for s in signals if s["signal"] == "SELL"][:top_n]
    longs = [{"player_name": s["player_name"], "weight": size_position(s), "rationale": s["rationale"]} for s in buys]
    shorts = [{"player_name": s["player_name"], "weight": size_position(s), "rationale": s["rationale"]} for s in sells]
    total = sum(x["weight"] for x in longs) + sum(x["weight"] for x in shorts)
    if total > 0:
        scale = 1.0 / total
        for x in longs + shorts:
            x["weight"] = round(x["weight"] * scale, 3)
    return {
        "long": longs,
        "short": shorts,
        "net_exposure": round(
            sum(x["weight"] for x in longs) - sum(x["weight"] for x in shorts), 3
        ),
        "gross_exposure": round(
            sum(x["weight"] for x in longs) + sum(x["weight"] for x in shorts), 3
        ),
    }
