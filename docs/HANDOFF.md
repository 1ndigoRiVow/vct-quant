# 交接日志 HANDOFF

> 最后更新：2026-08-14（周五）｜ 目的：周末换电脑继续干
> 机器 A（旧）：开发 + 提交，SSH key 已配置
> 机器 B（周末用）：需先完成"新环境搭建"一节

---

## 0. 两个项目，一张图

```
VCT 选手股（vct-quant）── 主线：量化预测 + 80/15/5 复合定价（已完成 0→1）
        │
        ├─ 数据层：vlr.gg（主力，待接入）→ 替换合成数据
        │
BERT 微调（docs/bert/）── 支线：虎扑评论情感三分类，给 0.15 评分层供数
        │
        └─ 现状：只有 2 份文档，零代码零数据
```

**定位提醒**（8/14 与用户确认）：转行方向 = **电竞运营里的数据/分析/产品角**。
VCT 选手股是敲门砖，BERT 是配菜（留在 VCT 当评分层，不拆）。重心 = 把 VCT 从"量化系统"长成"能给赛事运营交活的成品"。

---

## 1. VCT 项目当前状态（已完成 ✅）

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 采集→存储→特征→建模→策略→报告 分层管线，SQLite，离线合成数据模式 | ✅ |
| 选手画像 | rounds/kda/adr/acs/fk/fd/常用位置 + 选手-战队映射 + 战队地图胜率表 | ✅ |
| Phase 1 | 蒙特卡洛比赛模拟器（Glicko-2 + 地图修正 → 单回合胜率 → 13胜制 → p̂+95%CI）+ 校准评估 | ✅ |
| 复合定价 | **80% 比赛表现 / 15% 虎扑评分 / 5% 地图胜负**，`composite_price` 单一真相源 | ✅ |
| PRD | docs/PRD.md v1.1（定价规则已重写为 80/15/5） | ✅ |
| 虎扑采集 | collectors/hupu_ratings_collector.py（Codex 写，双模式），提示词规格 docs/CODEX_HUPU_CRAWLER.md | ✅ |

最新 commit：`92ce9d4 feat: 复合定价落地 80/15/5（表现主导·评分辅助）`

### 核心定价公式（改任何地方前先看这个）
```
P = V* + 0.15·评分层偏离 + 0.05·地图层偏离   （Rating/Map 以 V* 为中性锚）
```
- `vct_quant/models/value_model.py` → `composite_price()` / `map_deviation()`
- `vct_quant/config.py` → `PRICING_PERF/RATING/MAP_WEIGHT`、`SIGNAL_THETA=15`（≈1 个 Δ 标准差）
- 回测 `walk_forward` 已全部切到 `composite_price`（恢复 282 笔交易）

### 怎么跑起来（机器 A 已验证）
```bash
cd vct-quant
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # 若没有 requirements.txt，见下方依赖清单
python -m vct_quant.main                            # 全管线，离线合成数据模式
# 报告输出：reports/*.html（gitignore，不提交）
```
依赖（Python 3.13）：pandas, numpy, scipy, scikit-learn, transformers(仅 BERT 阶段), fastapi/uvicorn(仅 BERT 服务), sqlalchemy 或 sqlite3 标准库（看现有代码实际 import）

---

## 2. BERT 项目当前状态（只有文档 📄）

`docs/bert/`：
- **需求文档.md**：虎扑电竞评论情感分类（positive/neutral/negative），底模 `hfl/chinese-roberta-wwm-ext`，验收 macro-F1≥0.80 且 negative recall≥0.75，全程 OFFLINE_MODE
- **提示词.md**：4 类提示词（标注规范+few-shot、微调代码生成、推理服务代码生成、数据清洗）

**零代码、零数据、零模型**。周末从 Phase A 开始。

---

## 3. 数据源调研结论（8/14 已实测 ✅）

| 数据源 | 结论 | 实测 |
|---|---|---|
| **vlr.gg** | ⭐ 主力，无官方 API 但社区有 `vlrdevapi`（pip）/ `vlrggapi`（自部署 FastAPI），字段精准对口选手画像 | ✅ 本机 200 可达 |
| Riot 官方 Valorant API | ❌ 坑：只有玩家天梯数据，**不含 VCT 职业赛**，跳过 | ✅ 可达但无用 |
| valorantesports 官方 feed | 可选锦上添花：赛程/比分/排名，无选手数据，key 需逆向 | ⚠️ 403 |
| web.haojiao.cc | ❌ 排除：登录墙 + 不可达 | ❌ 000 |

**推荐架构**：vlr.gg 替换合成数据 → valorantesports 做事实层对账（后期）→ 虎扑采集器供 BERT。

---

## 4. 周末行动计划（按优先级）

### P0 — 接真实数据（质的飞跃）
1. `pip install vlrdevapi`，验证 `region=china` 能拉到 VCT CN 选手/比赛数据
2. 字段对表：`player_profiles` 的 rounds/kda/adr/acs/fk/fd + `team_map_winrate`
3. 写 `collectors/vlr_connector.py`（vlrdevapi → 现有 repo 的 upsert），替换/并存合成数据
4. 跑通真实数据管线 → 重跑回测 → 看 80/15/5 定价在真实数据上的信号分布

### P1 — BERT Phase A（数据）
1. 从 `hupu_comments` 抽真实评论（写抽数脚本，可问 AI 要）
2. LLM 辅助预标注 2000+ 条，三类均衡
3. 双人标注 + Kappa≥0.7
4. 离线下载 `chinese-roberta-wwm-ext` 权重到本地缓存

### P2 — 赛事运营成品（转行敲门砖）
1. 选手英雄池热力图 / BP ban-pick 分析
2. 赛前 scout report + 赛后复盘模板（选手画像+地图胜率表已打地基）
3. 输出形态：PDF / 网页 dashboard，模拟给运营团队交活

### P3 — BERT 训练与集成（P1 数据齐后）
- `train.py`/`evaluate.py`（提示词 2）→ 推理服务（提示词 3）→ 落库 `hupu_comments.sentiment` → 汇入 `value_model.rating_deviation` 0.15 层

---

## 5. 环境与网络坑（重要 ⚠️）

- **github:443 不通**：只能用 SSH（`git@github.com:1ndigoRiVow/vct-quant.git`），机器 B 需配 SSH key 并 `git remote set-url origin git@github.com:1ndigoRiVow/vct-quant.git`
- **OFFLINE_MODE**：所有权重/依赖本地化，huggingface 下载需在能联网的机器上提前拉缓存
- 机器 B 首次 clone：`git clone git@github.com:1ndigoRiVow/vct-quant.git`
- 编码：所有文件 UTF-8，Windows 下注意 git 不要乱改换行符（仓库内已有 .gitattributes 则无视本条；没有的话建议加 `* text=auto eol=lf`）

---

## 6. 提交规范（沿用）

- 英文 commit message，`feat:` / `fix:` / `docs:` / `refactor:` 前缀
- 中文注释，代码风格 PEP8
- 只推源码和文档，不推 `reports/*.html`、`*.db`、`data/`（.gitignore 已覆盖）
