"""vct_quant.main — 端到端 pipeline 入口。

流程：init_db → 采集(硬数据+舆情) → 情绪管线 → Glicko-2 评分 → 价值残差
     → 多空信号 → 组合 → 回测 → 生成 HTML 报告 + 仪表盘
"""
from __future__ import annotations

from datetime import datetime

from . import config
from .collectors.scheduler import Scheduler
from .collectors.sentiment_collector import HupuTiebaCollector
from .collectors.vlr_collector import VLRCollector
from .features.sentiment_features import SentimentPipeline, player_sentiment_features
from .models.backtest import walk_forward
from .models.glicko2 import rate_all_players
from .models.value_model import build_all_values
from .reporting.dashboard import build_dashboard
from .reporting.report import render_report
from .storage import db, repo
from .strategy.portfolio import build_portfolio
from .strategy.signals import generate_signals


def run_pipeline(n_matches: int = 24, n_posts: int = 80, backtest: bool = True):
    conn = db.connect()
    db.init_db(conn)
    repo.reset_all(conn)
    print("[1/8] 初始化数据库完成")

    # 1. 采集
    sched = Scheduler(conn).add(VLRCollector()).add(HupuTiebaCollector())
    summary = sched.run(n_matches=n_matches, n_posts=n_posts)
    print(f"[2/8] 采集完成: {summary['results']}")

    # 2. 情绪管线
    sp = SentimentPipeline()
    n_sent = sp.analyze_posts(conn)
    print(f"[3/8] 情绪管线产出 {n_sent} 条情绪记录")

    # 3. Glicko-2 评分
    ratings = rate_all_players(conn)
    print(f"[4/8] Glicko-2 评分完成，覆盖 {len(ratings)} 名选手")

    # 4. 价值残差 + 信号
    date = datetime.now().date().isoformat()
    values = build_all_values(conn, ratings, date)
    sf_map = {}
    for v in values:
        sf = player_sentiment_features(conn, v["player_name"])
        if sf:
            sf_map[v["player_name"]] = sf
    signals = generate_signals(values, sf_map)
    print(f"[5/8] 信号生成完成，买入{sum(1 for s in signals if s['signal']=='BUY')} "
          f"卖出{sum(1 for s in signals if s['signal']=='SELL')} "
          f"观望{sum(1 for s in signals if s['signal']=='HOLD')}")

    # 5. 组合
    portfolio = build_portfolio(signals)
    print(f"[6/8] 组合构建完成：多头{len(portfolio['long'])} 空头{len(portfolio['short'])} "
          f"净敞口{portfolio['net_exposure']}")

    # 6. 回测
    bt = walk_forward(conn) if backtest else {}
    print(f"[7/8] 回测完成: {bt}")

    # 7. 输出
    db_summary = {
        "matches": repo.count_rows(conn, "matches"),
        "player_stats": repo.count_rows(conn, "player_stats"),
        "posts": repo.count_rows(conn, "posts"),
        "sentiments": repo.count_rows(conn, "sentiments"),
    }
    report_path = render_report(date, signals, portfolio, bt, db_summary)
    dash_path = build_dashboard(signals, portfolio, bt, db_summary)
    print(f"[8/8] 报告: {report_path}")
    print(f"      仪表盘: {dash_path}")
    conn.close()
    return {"report": str(report_path), "dashboard": str(dash_path), "backtest": bt, "signals": len(signals)}


if __name__ == "__main__":
    run_pipeline()
