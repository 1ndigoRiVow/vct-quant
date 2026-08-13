"""vct_quant.models.sentiment_pricing — 评分层(15%)：虎扑JR评分/舆情 → 相对 V* 的情绪偏离。

旧版把情绪直接映射成市场价 P（100% 权重）。新复合定价下，情绪只占总价 15%，
且作为"相对内在价值 V* 的溢价/折价"存在（中性=0），不再自带 1500 基准——
基准由表现层 V* 统一提供，避免双重基准导致的系统性偏移。
形变(form_momentum)属客观表现层，不计入此评分层。
"""
from __future__ import annotations

from .. import config


def rating_deviation(sentiment_features: dict | None, match_features: dict | None = None) -> float:
    """相对 V* 的情绪溢价/折价；无舆情 → 0（中性，不贡献 Δ）。

    返回的是"偏离量"（与 V* 同尺度），由调用方乘以 0.15 权重后并入股价。
    """
    if not sentiment_features:
        return 0.0
    s_idx = sentiment_features["sentiment_mean"]   # -1..1
    hype = sentiment_features["hype_index"]         # 0..1
    bull = sentiment_features["bullish_ratio"]      # 0..1
    dev = (
        config.RATING_PRICING_ALPHA * s_idx
        + config.RATING_PRICING_BETA * hype
        + config.RATING_PRICING_BULL * (bull - 0.5)
    )
    return round(dev, 2)
