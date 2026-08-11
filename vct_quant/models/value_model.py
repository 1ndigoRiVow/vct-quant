"""vct_quant.models.value_model — 价值残差 Δ = P − V*，泡沫/洼地识别。"""
from __future__ import annotations

from datetime import datetime

from ..features.fusion import classify_delta, compute_delta
from ..storage import repo


def compute_player_value(conn, player_name: str, ratings: dict, sentiment_feat: dict | None,
                         match_feat: dict | None) -> dict:
    """计算单选手的 V* / P / Δ 及标签。"""
    v_star = ratings.get(player_name, {}).get("rating", 1500.0)
    from ..models.sentiment_pricing import market_price
    p_market = market_price(sentiment_feat, match_feat)
    delta = compute_delta(v_star, p_market)
    label, conf = classify_delta(delta)
    return {
        "player_name": player_name,
        "team": (match_feat or {}).get("team", ""),
        "v_star": round(v_star, 2),
        "p_market": p_market,
        "delta": round(delta, 2),
        "label": label,
        "confidence": round(conf, 3),
    }


def build_all_values(conn, ratings: dict, date: str | None = None) -> list[dict]:
    """对全部选手计算价值残差，写回 value_signals，按 |Δ| 降序返回。"""
    from ..features.match_features import player_match_features
    from ..features.sentiment_features import player_sentiment_features

    date = date or datetime.now().date().isoformat()
    from ..storage import repo as _repo
    players = _repo.get_all_players(conn)
    results = []
    for p in players:
        mf = player_match_features(conn, p)
        sf = player_sentiment_features(conn, p)
        v = compute_player_value(conn, p, ratings, sf, mf)
        v["rationale"] = _rationale(v, mf, sf)
        _repo.upsert_signal(conn, {
            "date": date,
            "player_name": p,
            "v_star": v["v_star"],
            "p_market": v["p_market"],
            "delta": v["delta"],
            "signal": _label_to_signal(v["label"], v["delta"]),
            "position": 0.0,
            "rationale": v["rationale"],
        })
        results.append(v)
    conn.commit()
    results.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return results


def _label_to_signal(label: str, delta: float) -> str:
    if label == "洼地":
        return "BUY"
    if label == "泡沫":
        return "SELL"
    return "HOLD"


def _rationale(v: dict, mf, sf) -> str:
    parts = [f"V*={v['v_star']}, P={v['p_market']}, Δ={v['delta']}({v['label']})"]
    if mf:
        parts.append(f"近{mf['n_maps']}图ACS={mf['acs']}/胜率{mf['win_rate']}/动量{mf['form_momentum']}")
    if sf:
        parts.append(f"舆情均值{sf['sentiment_mean']}/热度{sf['hype_index']}/看多{sf['bullish_ratio']}")
    return " | ".join(parts)
