"""vct_quant.models.value_model — 复合定价 P = 0.80·Perf + 0.15·Rating + 0.05·Map，残差 Δ 与信号。

定价主轴是客观表现（V*，占 80%），虎扑JR评分情绪层占 15%（辅助 tilt），
地图胜负层占 5%（微调）。为消除"双重基准"造成的系统性偏移，采用等价形式：

    P = V* + 0.15·Rating_dev + 0.05·Map_dev

其中 Rating_dev / Map_dev 都是"相对 V* 的偏离"（中性=0），故中性情形下 P=V*、Δ=0；
强情绪/地图优势才会把价格推离内在价值，产生可交易的洼地/泡沫信号。
"""
from __future__ import annotations

from datetime import datetime

from .. import config
from ..features.fusion import classify_delta, compute_delta
from ..models.sentiment_pricing import rating_deviation
from ..storage import repo


def map_deviation(conn, player_name: str, match_feat: dict | None) -> float:
    """地图层(5%)：战队地图胜率相对 50% 基线的偏离，落到 ~V* 尺度偏差。

    取该选手所属战队在 team_map_winrate 全部 (地图×对手) 行的平均胜率，
    减去公平基线 0.5 后乘以 MAP_PRICING_SCALE。无数据 → 0。
    """
    team = (match_feat or {}).get("team") or repo.get_player_team(conn, player_name)
    if not team:
        return 0.0
    rows = repo.get_team_map_winrate(conn, team)
    wrs = [r["win_rate"] for r in rows if r["win_rate"] is not None]
    if not wrs:
        return 0.0
    avg_wr = sum(wrs) / len(wrs)
    return round((avg_wr - 0.5) * config.MAP_PRICING_SCALE, 2)


def composite_price(conn, player_name: str, v_star: float,
                    sentiment_feat: dict | None, match_feat: dict | None) -> dict:
    """复合定价，返回各层分解（供报告 / rationale 使用）。

    表现层(80%) = V* 本身，作为定价锚，不计入 Δ；
    评分层(15%) = rating_dev（情绪偏离）；
    地图层(5%)  = map_dev（地图胜率偏离）。
    """
    rating_dev = rating_deviation(sentiment_feat, match_feat)   # 15% 层
    map_dev = map_deviation(conn, player_name, match_feat)      # 5% 层
    p_market = v_star + config.PRICING_RATING_WEIGHT * rating_dev + config.PRICING_MAP_WEIGHT * map_dev
    delta = compute_delta(v_star, p_market)
    return {
        "perf": round(v_star, 2),            # 80% 成分（锚）
        "rating_layer": rating_dev,          # 15% 层偏离
        "map_layer": map_dev,                # 5% 层偏离
        "p_market": round(p_market, 2),
        "delta": round(delta, 2),
    }


def compute_player_value(conn, player_name: str, ratings: dict, sentiment_feat: dict | None,
                         match_feat: dict | None) -> dict:
    """计算单选手的 V* / 三层分解 / P / Δ 及标签。"""
    v_star = ratings.get(player_name, {}).get("rating", 1500.0)
    cp = composite_price(conn, player_name, v_star, sentiment_feat, match_feat)
    label, conf = classify_delta(cp["delta"])
    return {
        "player_name": player_name,
        "team": (match_feat or {}).get("team", ""),
        "v_star": round(v_star, 2),
        "perf_layer": cp["perf"],
        "rating_layer": cp["rating_layer"],
        "map_layer": cp["map_layer"],
        "p_market": cp["p_market"],
        "delta": cp["delta"],
        "label": label,
        "confidence": round(conf, 3),
    }


def build_all_values(conn, ratings: dict, date: str | None = None) -> list[dict]:
    """对全部选手计算价值残差，写回 value_signals，按 |Δ| 降序返回。"""
    from ..features.match_features import player_match_features
    from ..features.sentiment_features import player_sentiment_features

    date = date or datetime.now().date().isoformat()
    players = repo.get_all_players(conn)
    results = []
    for p in players:
        mf = player_match_features(conn, p)
        sf = player_sentiment_features(conn, p)
        v = compute_player_value(conn, p, ratings, sf, mf)
        v["rationale"] = _rationale(v, mf, sf)
        repo.upsert_signal(conn, {
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
    parts = [
        f"V*={v['v_star']}(表现层80%锚)",
        f"评分层15%偏离={v['rating_layer']}",
        f"地图层5%偏离={v['map_layer']}",
        f"P={v['p_market']}, Δ={v['delta']}({v['label']})",
    ]
    if mf:
        parts.append(f"近{mf['n_maps']}图ACS={mf['acs']}/胜率{mf['win_rate']}/动量{mf['form_momentum']}")
    if sf:
        parts.append(f"舆情均值{sf['sentiment_mean']}/热度{sf['hype_index']}/看多{sf['bullish_ratio']}")
    return " | ".join(parts)
