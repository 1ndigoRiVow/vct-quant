"""vct_quant.reporting.report — HTML 信号报告渲染。

配色遵循 A 股惯例：买入(看涨)=红，卖出(看跌)=绿，观望=灰。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import config


def render_report(date: str, signals: list[dict], portfolio: dict,
                  backtest: dict, db_summary: dict, out_path: Path | None = None) -> Path:
    html = _build_html(date, signals, portfolio, backtest, db_summary)
    out = out_path or (Path(config.REPORT_DIR) / f"signal_report_{date}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _badge(sig: str) -> str:
    style = {"BUY": "background:#fee2e2;color:#991b1b;", "SELL": "background:#dcfce7;color:#166534;", "HOLD": "background:#f1f5f9;color:#475569;"}
    label = {"BUY": "买入·洼地", "SELL": "卖出·泡沫", "HOLD": "观望"}
    return f'<span style="{style[sig]} padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600">{label[sig]}</span>'


def _build_html(date, signals, portfolio, backtest, db_summary) -> str:
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for s in signals:
        rows.append(
            f"<tr>"
            f'<td style="font-weight:600">{s["player_name"]}</td>'
            f'<td>{s.get("team","")}</td>'
            f"<td>{_badge(s['signal'])}</td>"
            f'<td>{s["v_star"]}</td><td>{s["p_market"]}</td>'
            f'<td style="font-weight:600">{s["delta"]:+.0f}</td>'
            f'<td>{s["strength"]}</td>'
            f'<td>{"✓" if s.get("momentum_confirmed") else "—"}</td>'
            f'<td style="font-size:11px;color:#64748b">{s["rationale"]}</td>'
            f"</tr>"
        )
    rows_html = "\n".join(rows) or '<tr><td colspan="9" style="text-align:center;color:#94a3b8">暂无信号</td></tr>'

    def _port_table(items):
        if not items:
            return '<tr><td colspan="3" style="text-align:center;color:#94a3b8">无</td></tr>'
        return "\n".join(
            f'<tr><td style="font-weight:600">{x["player_name"]}</td>'
            f'<td>{x["weight"]}</td>'
            f'<td style="font-size:11px;color:#64748b">{x["rationale"]}</td></tr>'
            for x in items
        )

    long_tbl = _port_table(portfolio["long"])
    short_tbl = _port_table(portfolio["short"])
    bubbles = [s for s in signals if s["signal"] == "SELL"][:3]
    pockets = [s for s in signals if s["signal"] == "BUY"][:3]
    bubble_html = "<br>".join(f'{b["player_name"]} (Δ={b["delta"]:+.0f})' for b in bubbles) or "无"
    pocket_html = "<br>".join(f'{b["player_name"]} (Δ={b["delta"]:+.0f})' for b in pockets) or "无"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VCT CN 选手股信号报告 · {date}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background:#f8fafc; color:#0f172a; margin:0; padding:24px; line-height:1.6; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#64748b; font-size:13px; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:20px; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:14px 16px; }}
  .card .k {{ font-size:12px; color:#64748b; }}
  .card .v {{ font-size:20px; font-weight:600; margin-top:4px; }}
  h2 {{ font-size:15px; margin:24px 0 10px; border-left:3px solid #3b82f6; padding-left:8px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; border:1px solid #e2e8f0; font-size:13px; }}
  th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #f1f5f9; }}
  th {{ background:#f8fafc; font-weight:600; font-size:12px; color:#475569; }}
  td {{ vertical-align:top; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .hi {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:14px 16px; }}
  .hi .t {{ font-size:12px; color:#64748b; margin-bottom:6px; }}
  footer {{ margin-top:24px; color:#94a3b8; font-size:11px; }}
</style></head>
<body>
  <h1>VCT CN 选手股 · 量化信号报告</h1>
  <div class="sub">报告日期 {date} · 生成于 {gen} · 模拟量化研究，非真实交易</div>

  <div class="grid">
    <div class="card"><div class="k">比赛样本</div><div class="v">{db_summary.get('matches',0)}</div></div>
    <div class="card"><div class="k">选手统计行</div><div class="v">{db_summary.get('player_stats',0)}</div></div>
    <div class="card"><div class="k">舆情帖子</div><div class="v">{db_summary.get('posts',0)}</div></div>
    <div class="card"><div class="k">情绪记录</div><div class="v">{db_summary.get('sentiments',0)}</div></div>
    <div class="card"><div class="k">信号命中率</div><div class="v">{backtest.get('hit_rate',0)}</div></div>
    <div class="card"><div class="k">最大回撤</div><div class="v">{backtest.get('max_drawdown',0)}</div></div>
  </div>

  <div class="two">
    <div class="hi"><div class="t">价值洼地（被低估，建议买入）</div><div>{pocket_html}</div></div>
    <div class="hi"><div class="t">泡沫选手（被高估，建议卖出/避险）</div><div>{bubble_html}</div></div>
  </div>

  <h2>多空组合（dollar-neutral 近似）</h2>
  <div class="two">
    <div>
      <div class="sub">多头（洼地）</div>
      <table><thead><tr><th>选手</th><th>权重</th><th>逻辑</th></tr></thead><tbody>{long_tbl}</tbody></table>
    </div>
    <div>
      <div class="sub">空头（泡沫）</div>
      <table><thead><tr><th>选手</th><th>权重</th><th>逻辑</th></tr></thead><tbody>{short_tbl}</tbody></table>
    </div>
  </div>
  <div class="sub">净敞口 {portfolio.get('net_exposure',0)} · 总敞口 {portfolio.get('gross_exposure',0)}</div>

  <h2>全部信号明细</h2>
  <table>
    <thead><tr><th>选手</th><th>战队</th><th>信号</th><th>V*</th><th>P</th><th>Δ</th><th>强度</th><th>动量确认</th><th>逻辑</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  <footer>本报告由 vct_quant 自动生成。V*=Glicko-2 真实评分；P=情绪定价市场估值；Δ=P−V*。买入(看涨)=红、卖出(看跌)=绿，遵循 A 股惯例。</footer>
</body></html>"""
