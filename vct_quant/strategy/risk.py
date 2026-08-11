"""vct_quant.strategy.risk — 仓位与风控：半凯利 + 单标的上限 + 回撤止损。"""
from __future__ import annotations

from .. import config


def size_position(signal_row: dict) -> float:
    """半凯利，按信号强度缩放，受单标的上限约束。"""
    kelly = 2 * signal_row["strength"] - 1  # 0..1 -> -1..1
    raw = config.KELLY_FRACTION * max(kelly, 0.0)
    return round(min(config.MAX_POSITION_PCT, raw), 3)


def check_drawdown(current_equity: float, peak: float) -> tuple[bool, float]:
    """返回 (是否触发止损, 当前回撤)。"""
    dd = (peak - current_equity) / peak if peak > 0 else 0
    return dd >= config.MAX_DRAWDOWN_PCT, round(dd, 3)
