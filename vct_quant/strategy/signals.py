"""vct_quant.strategy.signals — 多空信号生成：阈值θ + 动量确认。"""
from __future__ import annotations

from .. import config
from ..features.fusion import classify_delta


def generate_signals(value_results: list[dict], sentiment_feats: dict | None = None) -> list[dict]:
    """value_results 来自 value_model；sentiment_feats: {player: {...}} 用于动量确认。"""
    sf = sentiment_feats or {}
    out = []
    for v in value_results:
        label = v["label"]
        if label == "均衡":
            sig, side = "HOLD", 0
        elif label == "洼地":
            sig, side = "BUY", 1
        else:
            sig, side = "SELL", -1
        # 动量确认：情绪动量与信号同向则加成，否则降权
        mom = sf.get(v["player_name"], {}).get("sentiment_momentum", 0)
        confirm = (mom * side) > 0
        strength = v["confidence"] * (1.2 if confirm else 0.7)
        strength = min(1.0, strength)
        out.append({
            **v,
            "signal": sig,
            "side": side,
            "strength": round(strength, 3),
            "momentum_confirmed": confirm,
        })
    out.sort(key=lambda x: abs(x["delta"]) * x["strength"], reverse=True)
    return out
