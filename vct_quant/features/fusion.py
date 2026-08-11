"""vct_quant.features.fusion — 实力 vs 情绪 偏差融合。

核心：Δ = P(市场情绪估值) − V*(真实实力估值)。
Δ>0 市场高估（泡沫），Δ<0 市场低估（价值洼地）。
"""
from __future__ import annotations

from .. import config


def compute_delta(v_star: float, p_market: float) -> float:
    return p_market - v_star


def classify_delta(delta: float, theta: float = config.SIGNAL_THETA) -> tuple[str, float]:
    """返回 (标签, 置信度)。"""
    ad = abs(delta)
    conf = min(1.0, ad / theta)
    if delta > theta:
        return "泡沫", conf
    if delta < -theta:
        return "洼地", conf
    return "均衡", conf
