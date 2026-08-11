"""vct_quant.reporting.dashboard — 本地 Web 仪表盘。

默认生成可交互的静态 HTML（Chart.js，离线可看）；若安装了 Flask 可起本地服务实时查看。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .. import config


def build_dashboard(signals: list[dict], portfolio: dict, backtest: dict,
                     db_summary: dict, out_path: Path | None = None) -> Path:
    n_signals = len(signals)
    points = [
        {"x": s["v_star"], "y": s["p_market"], "r": min(14, 4 + abs(s["delta"]) / 20),
         "player": s["player_name"], "signal": s["signal"], "delta": s["delta"]}
        for s in signals
    ]
    data = json.dumps(points, ensure_ascii=False)
    bars = json.dumps([{"player": s["player_name"], "delta": s["delta"], "signal": s["signal"]} for s in signals[:20]], ensure_ascii=False)
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _html(data, bars, n_signals, portfolio, backtest, db_summary, gen)
    out = out_path or (Path(config.REPORT_DIR) / "dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _html(points, bars, n_signals, portfolio, backtest, db_summary, gen) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VCT CN 选手股 · 仪表盘</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f8fafc;color:#0f172a;margin:0;padding:20px; }}
  h1 {{ font-size:18px; }} .sub {{ color:#64748b;font-size:13px;margin-bottom:16px; }}
  .grid {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px; }}
  .card {{ background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px; }}
  .card .k {{ font-size:12px;color:#64748b; }} .card .v {{ font-size:18px;font-weight:600; }}
  .row {{ display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px; }}
  .panel {{ background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px; }}
  canvas {{ max-height:340px; }}
  footer {{ margin-top:16px;color:#94a3b8;font-size:11px; }}
</style></head>
<body>
  <h1>VCT CN 选手股 · 量化仪表盘</h1>
  <div class="sub">生成于 {gen} · 模拟量化研究</div>
  <div class="grid">
    <div class="card"><div class="k">比赛样本</div><div class="v">{db_summary.get('matches',0)}</div></div>
    <div class="card"><div class="k">舆情帖子</div><div class="v">{db_summary.get('posts',0)}</div></div>
    <div class="card"><div class="k">信号数</div><div class="v">{n_signals}</div></div>
    <div class="card"><div class="k">命中率</div><div class="v">{backtest.get('hit_rate',0)}</div></div>
    <div class="card"><div class="k">最大回撤</div><div class="v">{backtest.get('max_drawdown',0)}</div></div>
    <div class="card"><div class="k">净敞口</div><div class="v">{portfolio.get('net_exposure',0)}</div></div>
  </div>
  <div class="row">
    <div class="panel"><div class="sub">V* vs P（对角线=均衡，上方=泡沫，下方=洼地）</div><canvas id="scatter"></canvas></div>
    <div class="panel"><div class="sub">残差 Δ（红=买入洼地，绿=卖出泡沫）</div><canvas id="bars"></canvas></div>
  </div>
  <footer>买入(看涨)=红 / 卖出(看跌)=绿，遵循 A 股惯例。</footer>
  <script>
  const pts = {points};
  const bars = {bars};
  Chart.defaults.color = '#475569';
  const scatter = new Chart(document.getElementById('scatter'), {{
    type:'bubble',
    data:{{datasets:[{{label:'选手',data:pts,backgroundColor:pts.map(p=>p.signal==='BUY'?'#dc2626':p.signal==='SELL'?'#16a34a':'#94a3b8')}}]}},
    options:{{plugins:{{tooltip:{{callbacks:{{label:function(c){{var p=c.raw;return p.player+' Δ='+p.delta;}}}}}}}},scales:{{x:{{title:{{display:true,text:'V* 真实评分'}}}},y:{{title:{{display:true,text:'P 市场估值'}}}}}}}}
  }});
  const bar = new Chart(document.getElementById('bars'), {{
    type:'bar',
    data:{{labels:bars.map(b=>b.player),datasets:[{{label:'Δ',data:bars.map(b=>b.delta),backgroundColor:bars.map(b=>b.signal==='BUY'?'#dc2626':b.signal==='SELL'?'#16a34a':'#94a3b8')}}]}},
    options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{title:{{display:true,text:'残差 Δ=P−V*'}}}}}}}}
  }});
  </script>
</body></html>"""


def serve_flask(conn, host="127.0.0.1", port=5050):
    """可选：用 Flask 起本地服务实时查看。需 pip install flask。"""
    from flask import Flask, jsonify
    from ..storage import repo
    app = Flask(__name__)

    @app.get("/")
    def index():
        from pathlib import Path
        return (Path(config.REPORT_DIR) / "dashboard.html").read_text(encoding="utf-8")

    @app.get("/api/signals")
    def api_signals():
        date = datetime.now().date().isoformat()
        rows = [dict(r) for r in repo.get_signals_by_date(conn, date)]
        return jsonify(rows)

    app.run(host=host, port=port)
