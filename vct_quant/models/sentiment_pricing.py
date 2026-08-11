"""vct_quant.models.sentiment_pricing — 情绪因子 → 市场隐含估值 P。

P = 1500 + alpha * sentiment_index + beta * hype_index + gamma * form
把社区情绪与热度映射到与 V* 同一评分尺度，便于计算残差 Δ = P − V*。
"""
from __future__ import annotations

from .. import config


def market_price(sentiment_features: dict | None, match_features: dict | None = None) -> float:
    if not sentiment_features:
        # 无舆情则市场价 ≈ 中性基准，靠比赛状态小幅修正
        base = 1500.0
        if match_features:
            base += 30 * match_features.get("form_momentum", 0) / 10
        return round(base, 2)
    s_idx = sentiment_features["sentiment_mean"]            # -1..1
    hype = sentiment_features["hype_index"]                 # 0..1
    bull = sentiment_features["bullish_ratio"]              # 0..1
    base = 1500.0
    p = (
        base
        + config.SENTIMENT_PRICING_ALPHA * s_idx
        + config.SENTIMENT_PRICING_BETA * hype
        + 80.0 * (bull - 0.5)
    )
    if match_features:
        p += 6.0 * match_features.get("form_momentum", 0)
    return round(p, 2)
