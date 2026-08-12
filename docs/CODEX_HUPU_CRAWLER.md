# Codex 任务规格：虎扑赛后评分 + 评论舆情采集器

> 这是给 Codex（或同类代码生成 agent）的任务提示词。直接把本文件全文作为 prompt 喂给 Codex 即可。
> 目标仓库：`vct-quant`（VCT CN 电竞量化预测 + “虎扑选手股”交易系统）。

---

## 0. 你的角色与一句话任务

你是一名 Python 数据采集工程师。请在 `vct-quant` 项目中实现一个**虎扑（bbs.hupu.com）赛后选手评分 + 比赛评论舆情采集器**，把数据采集落盘到 SQLite，并严格对齐项目现有的存储与采集约定。不要碰与本任务无关的其他模块。

关键认知（决定数据怎么设计）：本项目第二层预测模型需要的是**“一场比赛后，虎扑网友对每名选手的赛后评分（含评分人数）”**以及**“该场比赛的讨论评论文本”**。评分人数本身就是“热度/人气”的天然代理指标。模型消费的是**评分相对该选手历史基线的变化**和**评论情感**，而不是绝对值。因此采集时必须同时拿到 `rating_avg` 和 `rating_count`。

---

## 1. 先读这些文件，对齐项目约定（必做，不要跳过）

在写任何代码前，先读并理解以下文件，确保你写的代码风格/接口与现有代码一致：

- `vct_quant/config.py` —— 全局配置。注意 `HUPU_BASE = "https://bbs.hupu.com"`、`OFFLINE_MODE`（默认 True=离线合成）、`REQUEST_TIMEOUT / REQUEST_DELAY / MAX_RETRIES / USER_AGENT`。
- `vct_quant/collectors/sentiment_collector.py` —— 现有舆情采集器。**重点模仿它的接口约定**：`__init__(self, offline: bool | None = None)`（不传则读 `config.OFFLINE_MODE`），`collect(conn, ...)` 方法体里 `if self.offline: 合成 else: 真实抓取`，真实抓取失败要 `try/except` 降级返回空列表并打印 `[hupu] fetch failed: ...`，最后调用 `repo.upsert_*` 落库并 `conn.commit()`。
- `vct_quant/collectors/vlr_collector.py` —— 参考它解析 VLR.gg 比赛页的方式（`TEAMS` 常量、比赛/地图/选手统计的结构），以及它如何生成稳定的 `id`（如 `match_id|player_name` 防止重复）。
- `vct_quant/collectors/net.py` —— 现有的 HTTP 抓取封装（`fetch_html` 等），优先复用；如需要异步/渲染页面自行补充。
- `vct_quant/storage/schema.sql` —— 现有表结构。新增表按这里的 SQL 风格（`CREATE TABLE IF NOT EXISTS`、snake_case、外键可选）。
- `vct_quant/storage/db.py` —— 注意已有 `_migrate()` 轻量迁移机制（`init_db` 会 `executescript(SCHEMA)` + 补缺失列）。新增表只要在 `schema.sql` 加 `CREATE TABLE IF NOT EXISTS` 即可被自动创建，无需手动建表。
- `vct_quant/storage/repo.py` —— 现有的 `upsert_*` 系列（尤其 `upsert_post`、`upsert_sentiment`），**严格仿照它们的字段名、ON CONFLICT 幂等写法、参数形态**来写新表的 upsert。

---

## 2. 数据模型（新增两张表，不要改现有表）

在 `schema.sql` 末尾追加：

```sql
-- 虎扑赛后选手评分（第二层人气模型核心标签）
CREATE TABLE IF NOT EXISTS hupu_match_ratings (
  id TEXT PRIMARY KEY,            -- match_id||'|'||player_name，稳定去重
  match_id TEXT NOT NULL,
  player_name TEXT NOT NULL,
  team TEXT,
  rating_avg REAL,               -- 虎扑赛后平均分（通常 1-10 制，以实际页面为准）
  rating_count INTEGER,          -- 评分人数 —— 热度/人气的天然代理，必须采集
  rating_dist TEXT,              -- 可选 JSON: {"1":n,...,"10":n} 分布，抓不到可留空
  fetched_at TEXT
);

-- 虎扑赛后比赛评论（文本舆情，供情感分析 + 热度）
CREATE TABLE IF NOT EXISTS hupu_comments (
  id TEXT PRIMARY KEY,            -- 稳定 hash: match_id||thread_id||floor
  match_id TEXT,                  -- 关联到 VLR 的比赛；侦察不到则留空
  thread_id TEXT,
  page INTEGER,
  author TEXT,
  content TEXT,
  floor INTEGER,                  -- 楼层号
  like_count INTEGER,
  post_time TEXT,                 -- ISO 字符串，抓不到具体时间则留空
  fetched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_hupu_rating_match  ON hupu_match_ratings(match_id);
CREATE INDEX IF NOT EXISTS idx_hupu_rating_player ON hupu_match_ratings(player_name);
CREATE INDEX IF NOT EXISTS idx_hupu_comment_match ON hupu_comments(match_id);
```

在 `repo.py` 追加（仿 `upsert_post` 风格，幂等）：

```python
def upsert_hupu_rating(conn, r: dict) -> None:
    r = {**r, "id": r.get("id") or f"{r['match_id']}|{r['player_name']}",
         "fetched_at": r.get("fetched_at") or _now()}
    conn.execute(
        """INSERT INTO hupu_match_ratings
             (id, match_id, player_name, team, rating_avg, rating_count, rating_dist, fetched_at)
           VALUES (:id,:match_id,:player_name,:team,:rating_avg,:rating_count,:rating_dist,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             rating_avg=excluded.rating_avg, rating_count=excluded.rating_count,
             rating_dist=excluded.rating_dist, fetched_at=excluded.fetched_at""",
        r,
    )

def upsert_hupu_comment(conn, c: dict) -> None:
    conn.execute(
        """INSERT INTO hupu_comments
             (id, match_id, thread_id, page, author, content, floor, like_count, post_time, fetched_at)
           VALUES (:id,:match_id,:thread_id,:page,:author,:content,:floor,:like_count,:post_time,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             content=excluded.content, like_count=excluded.like_count,
             post_time=excluded.post_time, fetched_at=excluded.fetched_at""",
        c,
    )
```

> 注：`_now()` 是 `repo.py` 已有的私有辅助函数，直接复用。

---

## 3. 新建采集模块 `vct_quant/collectors/hupu_ratings_collector.py`

类名建议 `HupuRatingsCollector`，接口与 `HupuTiebaCollector` 保持一致：

```python
class HupuRatingsCollector:
    def __init__(self, offline: bool | None = None):
        self.offline = config.OFFLINE_MODE if offline is None else offline

    def collect(self, conn, match_ids: list[str] | None = None,
                n_comments: int = 200, **kwargs) -> dict:
        """返回 {'ratings': int, 'comments': int} 落库计数。"""
        ...
```

### 3.1 真实抓取逻辑（侦察优先，不要硬编码错误选择器）

虎扑的赛后评分与评论**页面结构你需要先实地侦察**，不要凭空假设 DOM。建议步骤：

1. **定位入口**：从 `config.HUPU_BASE` 出发，找到 VCT / 无畏契约 / 电竞赛事相关板块或具体比赛帖。先 `WebFetch` / 手动 `fetch_html` 一个已知比赛页，打印 HTML 片段，定位：
   - 赛后评分组件（每名选手的 avg 分、评分人数、可能的分布柱状图）；
   - 评论容器（楼层、作者、内容、点赞、时间）。
2. **评分解析**：把每场比赛的参赛选手名单（可与 `vlr_collector` 的 `TEAMS` / 已入库 `player_stats` 对齐）与虎扑评分页面对应，解析出 `player_name, team, rating_avg, rating_count, rating_dist`。选手名要做模糊匹配/别名归一（虎扑昵称可能与 VLR 不一致），匹配不上的评分也保留但 `player_name` 原样落库，留待后续人工/规则对齐。
3. **评论解析**：翻页抓取评论（注意虎扑评论常是动态加载 + 反爬），拿到 `author, content, floor, like_count, post_time`。若评论页带 `match_id`，关联写入；否则 `match_id` 留空，后续用时间窗口 + 战队名回灌关联。
4. **健壮性**：每次请求遵守 `config.REQUEST_DELAY` 间隔、`config.MAX_RETRIES` 重试、带 `config.USER_AGENT`。单页/单请求失败不得中断整体，记日志后跳过。评论翻页要有上限（如 `n_comments` 或 max_page）防止死循环。

### 3.2 在线模式的登录/反爬（重要）

虎扑对高频抓取和评论接口有风控，**匿名可能拿不到评论或评分**。请：
- 优先尝试匿名访问；
- 若需要登录态，从环境变量读取 Cookie（`HUPU_COOKIE`，可不在代码里硬编码），并在 README/注释里说明如何获取；
- 不要尝试绕过验证码或做破坏性操作，遇到硬墙就 `print` 警告并返回已拿到部分；
- 在模块 docstring 里如实写明“已验证可匿名获取评分 / 需登录才能获取评论”的结论。

### 3.3 离线合成（必须实现，保持管线可跑）

当 `self.offline` 为真（默认），生成**合成的赛后评分 + 评论**，让 `OFFLINE_MODE=True` 时全管线不依赖联网：
- 评分：对已知 `TEAMS` 里的每名选手，随机生成 `rating_avg`（如 5.0~9.5 正态分布截断）与 `rating_count`（如 50~3000，明星选手偏高）。
- 评论：仿 `sentiment_collector` 的模板风格，生成带情绪/黑话/反讽的中文评论文本（正负中性混合），填充 `author/content/floor/like_count`。
- 合成的 `id` 必须稳定（用 `match_id|player_name` / hash），保证可重入去重。
- 合成数据量要与真实模式近似（`n_comments` 等参数生效）。

### 3.4 增量

`collect` 应先查 `hupu_match_ratings` 里已存在的 `match_id`，跳过已抓比赛（除非显式传 `force=True`）。不要重复抓同一场比赛。

---

## 4. 工程与接口约束（硬要求）

- **纯标准库 + requests + beautifulsoup4 + 可选 playwright**（项目现有依赖，不要引入重型新依赖；如必须加，在 PR/说明里列出并确认）。
- 所有落库走 `repo.upsert_hupu_rating` / `upsert_hupu_comment`，**不要**直接 `conn.execute` 裸写（保持仓储层单一入口）。
- 不要修改 `sentiment_collector.py`、`vlr_collector.py`、`schema.sql` 里**既有表**的定义（只追加新表）。
- 不要改 `main.py` 主流程（如需验证，单独提供一个 `if __name__ == "__main__":` 脚本或 `collect(conn, ...)` 示例，注释说明如何手动运行）。
- 代码要有类型注解、`docstring`、关键步骤 `print` 进度（仿现有 `main.py` 的 `[n/8]` 风格可选）。
- 异常用 `try/except Exception` 包裹单点抓取并 `print` 警告，绝不让单个请求失败导致整批崩溃。

---

## 5. 不要做的事（边界）

- ❌ 不要实现情绪分析 / 打分模型（那是 `features/` 和 `models/` 的事，本任务只采集原始数据）。
- ❌ 不要写任何“预测”“信号”“交易”逻辑。
- ❌ 不要把虎扑评分直接当作 `player_ratings`（那是 Glicko-2 实力评分表），两者字段与语义不同，分开存。
- ❌ 不要删改现有 `posts` / `sentiments` 表及其用途。

---

## 6. 验收标准（交付前自检）

1. `python -m vct_quant.collectors.hupu_ratings_collector`（或你提供的运行入口）在 `OFFLINE_MODE=True` 下能跑通，向 SQLite 写入若干 `hupu_match_ratings` 与 `hupu_comments` 行，`conn` 关闭正常，无报错。
2. 用 `sqlite3` / 一段 Python 打印两张新表的行数、样例（前 5 行）确认字段正确。
3. 真实模式：提供至少 **1 个你实地侦察过的虎扑比赛 URL**，运行后能解析出该场**所有选手的 `rating_avg` + `rating_count`** 以及部分评论，并说明匿名/登录的结论。
4. 增量：对同一个 `match_id` 跑两次，第二次数不增加（幂等）。
5. 模块 docstring 写清：虎扑评分入口 URL 规律、评分/评论所在 DOM 选择器（或“需登录”结论）、离线/在线切换方式。
6. 不破坏现有 `python -m vct_quant.main` 离线全管线运行。

---

## 7. 交付物清单

- `vct_quant/collectors/hupu_ratings_collector.py`（新）
- `vct_quant/storage/schema.sql`（追加 2 张表 + 索引）
- `vct_quant/storage/repo.py`（追加 2 个 upsert 函数）
- （可选）`vct_quant/collectors/net.py` 若需补充抓取能力
- 在 `README.md` 的“采集层”小节追加一行说明本模块

完成后简短报告：实现了什么、侦察到的虎扑页面结构关键结论、匿名/登录结论、离线合成是否通过、遇到的最大坑。
