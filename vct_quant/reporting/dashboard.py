"""vct_quant.reporting.dashboard — 本地 Web 仪表盘。

默认生成可交互的静态 HTML（Chart.js，离线可看）；若安装了 Flask 可起本地服务实时查看。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .. import config


def build_dashboard(signals: list[dict], portfolio: dict, backtest: dict,
                     db_summary: dict, out_path: Path | None = None,
                     profiles: list[dict] | None = None,
                     map_winrate: list[dict] | None = None,
                     calibration: dict | None = None) -> Path:
    profiles = profiles or []
    map_winrate = map_winrate or []
    n_signals = len(signals)
    points = [
        {"x": s["v_star"], "y": s["p_market"], "r": min(14, 4 + abs(s["delta"]) / 20),
         "player": s["player_name"], "signal": s["signal"], "delta": s["delta"]}
        for s in signals
    ]
    data = json.dumps(points, ensure_ascii=False)
    bars = json.dumps([{"player": s["player_name"], "delta": s["delta"], "signal": s["signal"]} for s in signals[:20]], ensure_ascii=False)

    # 选手画像：位置分布 + 顶部 KDA/ACS 排行
    role_counts: dict[str, int] = {}
    for p in profiles:
        role = p["main_role"] or "unknown"
        role_counts[role] = role_counts.get(role, 0) + 1
    role_data = json.dumps({
        "labels": [ROLE_CN.get(r, r) for r in role_counts],
        "values": list(role_counts.values()),
    }, ensure_ascii=False)
    top_perf = json.dumps([
        {"player": p["player_name"], "role": ROLE_CN.get(p["main_role"], p["main_role"]),
         "acs": p["acs"], "adr": p["adr"], "kda": p["kda"]}
        for p in sorted(profiles, key=lambda x: x["acs"], reverse=True)[:15]
    ], ensure_ascii=False)

    # 战队地图胜率：按胜率取前 20 条
    mw = sorted(map_winrate, key=lambda x: (x["win_rate"] or 0), reverse=True)[:20]
    mapwr_data = json.dumps([
        {"label": f'{r["team"]}·{r["map_name"]}·vs{r["opponent"]}', "wr": r["win_rate"] or 0}
        for r in mw
    ], ensure_ascii=False)

    # 比赛模拟器校准：每场 p̂(x) vs 实际结果(y，带确定性抖动避免重叠)
    calib_pts = []
    if calibration and calibration.get("details"):
        for i, d in enumerate(calibration["details"]):
            actual_a = 1 if d["actual_winner"] == d["team_a"] else 0
            jitter = (((i * 37) % 10) - 4.5) / 60.0  # ±0.075 确定性抖动
            calib_pts.append({
                "x": d["p_win_a"], "y": actual_a + jitter,
                "label": f'{d["team_a"]} vs {d["team_b"]}·{d["map"]}',
                "actual": actual_a,
            })
    calib_data = json.dumps(calib_pts, ensure_ascii=False)
    cal_acc = (calibration or {}).get("accuracy")
    cal_brier = (calibration or {}).get("brier")
    cal_acc_disp = f"{cal_acc:.1%}" if isinstance(cal_acc, (int, float)) else "—"
    cal_brier_disp = f"{cal_brier:.3f}" if isinstance(cal_brier, (int, float)) else "—"

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _html(data, bars, n_signals, portfolio, backtest, db_summary, gen,
                 role_data, top_perf, mapwr_data, calib_data, cal_acc_disp, cal_brier_disp)
    out = out_path or (Path(config.REPORT_DIR) / "dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


ROLE_CN = {"duelist": "决斗", "initiator": "先锋", "controller": "控场", "sentinel": "哨卫", "unknown": "未知"}


def _html(points, bars, n_signals, portfolio, backtest, db_summary, gen,
          role_data=None, top_perf=None, mapwr_data=None,
          calib_data=None, cal_acc="—", cal_brier="—") -> str:
    role_data = role_data or '{"labels":[],"values":[]}'
    top_perf = top_perf or "[]"
    mapwr_data = mapwr_data or "[]"
    calib_data = calib_data or "[]"
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
  <div class="row">
    <div class="panel"><div class="sub">选手常用位置分布（先锋/决斗/控场/哨卫）</div><canvas id="roles"></canvas></div>
    <div class="panel"><div class="sub">选手 ACS 排行（平均战斗评分 TOP15）</div><canvas id="perf"></canvas></div>
  </div>
  <div class="panel"><div class="sub">战队 × 地图 × 对手 胜率 TOP20</div><canvas id="mapwr"></canvas></div>
  <div class="panel"><div class="sub">比赛模拟器校准 · 预测胜率 p̂ vs 实际结果（红=A胜 绿=A负）｜命中率 {cal_acc} · Brier {cal_brier}</div><canvas id="calib"></canvas></div>
  <footer>买入(看涨)=红 / 卖出(看跌)=绿，遵循 A 股惯例。校准图为蒙特卡洛模拟器赛前胜率预测 p̂ 与实际胜负对照。</footer>
  <script>
  const pts = {points};
  const bars = {bars};
  const roleData = {role_data};
  const perf = {top_perf};
  const mapwr = {mapwr_data};
  const calib = {calib_data};
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
  new Chart(document.getElementById('roles'), {{
    type:'doughnut',
    data:{{labels:roleData.labels,datasets:[{{data:roleData.values,backgroundColor:['#dc2626','#3b82f6','#7c3aed','#0d9488','#94a3b8']}}]}},
    options:{{plugins:{{legend:{{position:'bottom'}}}}}}
  }});
  new Chart(document.getElementById('perf'), {{
    type:'bar',
    data:{{labels:perf.map(p=>p.player+'('+p.role+')'),datasets:[{{label:'ACS',data:perf.map(p=>p.acs),backgroundColor:'#3b82f6'}}]}},
    options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{title:{{display:true,text:'ACS'}}}}}}}}
  }});
  new Chart(document.getElementById('mapwr'), {{
    type:'bar',
    data:{{labels:mapwr.map(m=>m.label),datasets:[{{label:'胜率',data:mapwr.map(m=>m.wr),backgroundColor:mapwr.map(m=>m.wr>=0.5?'#dc2626':'#94a3b8')}}]}},
    options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{min:0,max:1,title:{{display:true,text:'胜率'}}}}}}}}
  }});
  if (calib.length) {{
    new Chart(document.getElementById('calib'), {{
      type:'scatter',
      data:{{datasets:[{{label:'每场比赛',data:calib,backgroundColor:calib.map(c=>c.actual===1?'#dc2626':'#16a34a'),pointRadius:6}}]}},
      options:{{plugins:{{tooltip:{{callbacks:{{label:function(c){{var p=c.raw;return p.label+'  p̂(A胜)='+p.x.toFixed(2);}}}}}},legend:{{display:false}}}},
        scales:{{x:{{min:0,max:1,title:{{display:true,text:'预测 A 胜率 p̂'}}}},
                 y:{{min:-0.2,max:1.2,ticks:{{callback:function(v){{return Math.abs(v-1)<0.01?'A胜':Math.abs(v)<0.01?'A负':'';}}}},title:{{display:true,text:'实际结果'}}}}}}}}
    }});
  }}
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
