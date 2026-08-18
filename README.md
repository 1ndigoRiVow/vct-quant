# vct-quant · VCT CN 量化预测与虎扑社区选手股模拟交易系统

> 把电竞选手当作"股票"来定价：**80% 比赛表现 + 15% 虎扑社区评分 + 5% 地图胜负**，用量化方法预测赛果、捕捉人气与实力的错价。
>
> 纯搞耍+vibe coding，不喜勿喷。有建议欢迎提出喵

面向 **VCT CN（无畏契约中国赛区）** 的电竞量化研究系统：从选手/比赛数据出发，构建 Glicko-2 实力评分与赛前胜率预测（p̂），叠加虎扑社区评分形成复合定价（P），输出多空信号与模拟组合——本质是一套 **「选手数据为主、社区评分为辅」** 的复合定价引擎。

> ⚠️ 本系统为**模拟量化研究项目**，不接入真实金融交易。"选手股"是社区驱动的模拟定价/人气市场。

---

## ✨ 为什么值得看

| 亮点 | 说明 |
|---|---|
| **80/15/5 复合定价** | 比赛表现 80% / 虎扑评分 15% / 地图胜负 5% 加权，把「打得好不好」和「人气高不高」量化进一个可回测的定价公式 |
| **Glicko-2 选手实力层** | 带不确定度（RD）的 Elo 系评分，比简单 KDA 更能反映"真实实力" |
| **赛前胜率模拟器 p̂** | 回合制蒙特卡洛引擎（13 胜制 + 加时 + 地图修正），输出赛前胜率与 95% 置信区间 |
| **信号 → 仓位 → 组合** | 价值偏差 Δ = P − V* 驱动多空信号，半凯利仓位 + dollar-neutral 组合，walk-forward 回测验证 |
| **选手画像体系** | 特工池/位置/地图胜率多维画像，为 scout report 打地基 |

---

## 🧠 核心定价逻辑

```
P = V* + 0.15 · 评分层偏离 + 0.05 · 地图层偏离
     └─ 80% 比赛表现 ─┘   └─ 15% 虎扑 ─┘   └─ 5% 地图 ─┘
```

- **V\***：Glicko-2 实力评分（表现层主体）
- **评分层偏离**：虎扑赛后评分相对 V* 的情绪溢价（人气层）
- **地图层偏离**：战队地图胜率相对实力预期的偏差（情境层）
- **Δ = P − V\***：Δ > 0 高估（泡沫），Δ < 0 低估（洼地）

---

## 🏗️ 系统架构

```
采集层 → 存储层 → 特征工程 → 量化建模 → 策略层 → 报告输出
```

| 层 | 目录 | 说明 |
|---|---|---|
| 采集 | `collectors/` | VLR.gg 采集（规划接入）、虎扑赛后评分/评论、贴吧/B站舆情、调度器 |
| 存储 | `storage/` | SQLite 12+ 张表 + 幂等仓储 CRUD |
| 特征 | `features/` | 滚动实力特征 + 情绪因子 + 实力-情绪融合 |
| 建模 | `models/` | Glicko-2、复合定价（`composite_price` 单一真相源）、蒙特卡洛模拟器、选手画像、walk-forward 回测 |
| 策略 | `strategy/` | 多空信号、半凯利仓位、dollar-neutral 组合、风险控制 |
| 输出 | `reporting/` | HTML 信号报告 + Chart.js 仪表盘（含校准板块） |

### 比赛模拟器（p̂）

FPS 回合制蒙特卡洛引擎：队伍实力（Glicko-2 均值按 RD 采样 + 地图胜率修正）→ 逻辑斯蒂映射单回合胜率 → 13 胜制逐回合模拟（12:12 加时）→ N 次重复输出 **p̂ + 95%CI**。配套 `evaluate_calibration` 输出 Brier / Log-Loss / 命中率。

### 选手画像

由比赛统计聚合写回 `player_profiles`：
- `rounds_by_agent` 特工回合数 + **常用位置**（决斗/先锋/控场/哨卫）
- **KDA / ADR / ACS / FK / FD**
- `player_teams` 选手→战队映射（含证据）、`team_map_winrate` 战队×地图×对手胜率

---

## 🚀 快速开始

### 环境要求
- Python 3.12+（开发使用 3.13）

### 离线模式（零第三方依赖，开箱即用）

```bash
python -m vct_quant.main
```

合成数据验证全管线，无需安装任何包；输出信号报告与仪表盘到 `reports/`。

### 真实数据模式

```bash
pip install requests beautifulsoup4            # 采集
pip install transformers                        # （可选）BERT 情绪初筛
export VQ_LLM_API_BASE=... VQ_LLM_API_KEY=...   # （可选）LLM 深度分析
```

修改 `vct_quant/config.py` 中 `OFFLINE_MODE = False` 后运行 `python -m vct_quant.main`。

### 虎扑赛后评分手动录入

为避免个人账号 Cookie 触发风控，评分默认手动导入 CSV：

```csv
match_id,player_name,team,rating_avg,rating_count,rating_dist
m0,ZmjjKK,EDG,8.7,2351,
```

模板路径 `vct_quant/data/raw/hupu_ratings.csv`，运行
`python -m vct_quant.collectors.manual_hupu_ratings_importer` 自动生成；
按 `match_id|player_name` 幂等写入 `hupu_match_ratings`。

---

## 🗺️ 路线图

- [x] **Phase 0** 采集→存储→特征→建模→策略→报告 分层管线（离线合成数据模式）
- [x] **Phase 1** 蒙特卡洛比赛模拟器 + 校准评估 + 选手画像体系
- [x] **定价 v1.1** 80/15/5 复合定价落地（表现主导·评分辅助）
- [ ] **Phase 2** 接入 vlr.gg 真实 VCT CN 数据，替换合成数据并重跑回测
- [ ] **Phase 3** 虎扑评论 BERT 情感微调，汇入 0.15 评分层
- [ ] **Phase 4** 赛事运营成品：scout report / 赛前分析 / 赛后复盘模板

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | 产品需求文档 v1.1（双层预测模型 + 80/15/5 定价框架） |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | 交接日志（项目状态 / 数据源调研 / 行动计划） |
| [`docs/CODEX_HUPU_CRAWLER.md`](docs/CODEX_HUPU_CRAWLER.md) | 虎扑评分/评论采集器提示词规格 |
| [`docs/bert/`](docs/bert/) | BERT 情感分类需求文档 + 提示词（支线项目） |

---

## 📄 License

[MIT](LICENSE) © 2026 1ndigoRiVow
