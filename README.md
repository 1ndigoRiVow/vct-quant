# VCT CN 量化预测与选手股交易系统

针对 VCT CN（无畏契约中国赛区）的电竞量化预测与社区"选手股"模拟交易策略系统。

## 快速开始

### 环境要求
- Python 3.12+

### 离线模式（零重依赖，开箱即用）
```bash
cd vct_quant
python -m vct_quant.main
```
此模式使用合成数据验证全管线，无需安装任何第三方包。

### 真实数据模式
1. 安装依赖：`pip install requests beautifulsoup4`
2. （可选）情绪分析：`pip install transformers`（BERT 初筛）
3. （可选）LLM 深度分析：设置环境变量 `VQ_LLM_API_BASE` 和 `VQ_LLM_API_KEY`
4. 修改 `vct_quant/config.py`：`OFFLINE_MODE = False`
5. 运行：`python -m vct_quant.main`

### 虎扑赛后评分手动录入

为避免使用个人虎扑账号 Cookie 触发登录风控，项目默认不爬虎扑评论。比赛结束后手动填写：

```csv
match_id,player_name,team,rating_avg,rating_count,rating_dist
m0,ZmjjKK,EDG,8.7,2351,
```

文件位置：`vct_quant/data/raw/hupu_ratings.csv`。首次运行
`python -m vct_quant.collectors.manual_hupu_ratings_importer` 会自动生成模板；导入后写入
`hupu_match_ratings`，并按 `match_id|player_name` 幂等更新。

公开舆情文本由贴吧和 B 站采集器写入 `posts`，用于后续情绪分析。

## 架构

```
采集层 → 存储层 → 特征工程 → 量化建模 → 策略层 → 报告输出
```

| 层 | 目录 | 说明 |
|---|---|---|
| 采集 | `collectors/` | VLR.gg 爬虫 + 虎扑/贴吧舆情 + 虎扑赛后评分/评论 + 调度器 |
| 存储 | `storage/` | SQLite 10 张表 + 仓储 CRUD |
| 特征 | `features/` | 滚动实力特征 + BERT/LLM 情绪因子 + 实力-情绪融合 |
| 建模 | `models/` | Glicko-2 评分 + 情绪定价 + 价值残差 + walk-forward 回测 + 选手多维画像 |
| 策略 | `strategy/` | 多空信号 + 半凯利仓位 + dollar-neutral 组合 |
| 输出 | `reporting/` | HTML 信号报告 + Chart.js 仪表盘 |

## 选手能力画像（多维模型）

由比赛统计聚合，写回 `player_profiles` 表，字段包括：
- **特工回合**：`rounds_by_agent` — 选手使用每个特工的上场回合数
- **KDA / ADR / ACS / FK / FD** — 击杀死亡助攻、每回合均伤、平均战斗评分、首杀、首死
- **常用位置**：按特工池回合占比投票出 决斗 / 先锋 / 控场 / 哨卫

配套表：
- `player_teams`：选手 → 当前战队归属（由最近比赛推断，含证据）
- `team_map_winrate`：战队 × 地图 × 对手 的胜率与回合得失

## 核心概念

- **V\*** (Glicko-2 评分)：选手真实实力估值
- **P** (情绪定价)：社区情绪驱动的市场隐含估值
- **Δ = P − V\***：情绪与实力偏差。Δ > 0 = 泡沫（高估），Δ < 0 = 洼地（低估）

## 产出文件

- `reports/signal_report_YYYY-MM-DD.html`：每日信号报告
- `reports/dashboard.html`：可交互仪表盘
- `vct_quant/data/vct_quant.db`：SQLite 数据库

## 定位说明

本系统为**模拟量化研究系统**，不接入真实金融交易。虎扑"选手股"本质是社区驱动的模拟定价/人气市场。
