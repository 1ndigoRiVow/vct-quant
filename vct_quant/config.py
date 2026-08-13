"""vct_quant.config — 全局配置：路径、阈值、数据源、抓取与情绪管线参数。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "vct_quant.db"
REPORT_DIR = BASE_DIR / ".." / "reports"
TEMPLATE_DIR = BASE_DIR / "reporting" / "templates"

for _d in (DATA_DIR, RAW_DIR, REPORT_DIR, TEMPLATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DB_URL = f"sqlite:///{DB_PATH}"

# === 数据源 ===
VLR_BASE = "https://www.vlr.gg"
HAOJIAO_BASE = "https://web.haojiao.cc"
HUPU_BASE = "https://bbs.hupu.com"
TIEBA_BASE = "https://tieba.baidu.com"
BILIBILI_BASE = "https://search.bilibili.com"

# Manual Hupu post-match ratings import. Keep account login/cookies out of code.
HUPU_RATINGS_CSV = RAW_DIR / "hupu_ratings.csv"

# VCT CN 赛区 event id（vlr.gg 上的赛季索引，占位，实际需核对当前赛季）
VCT_CN_EVENT_IDS = ["1388", "1905"]

# === 抓取行为 ===
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 2.0
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# === 特征窗口 ===
ROLL_WINDOW_MAPS = 8
FORM_MOMENTUM_WINDOW = 5

# === 建模：Glicko-2 ===
GLICKO2_TAU = 0.5
GLICKO2_DEFAULT_RATING = 1500.0
GLICKO2_DEFAULT_RD = 350.0
GLICKO2_DEFAULT_VOL = 0.06

# === 复合定价：股价 P = 0.80·表现层(Perf) + 0.15·评分层(Rating) + 0.05·地图层(Map) ===
# 表现层(80%) = V*(Glicko-2 客观实力)，作为定价锚（不贡献 Δ）；
# 评分层(15%) = 虎扑JR评分/舆情情绪溢价，相对 V* 的偏离；
# 地图层(5%)  = 战队地图胜率相对 50% 基线的边际修正，相对 V* 的偏离。
# 等价实现：P = V* + 0.15·Rating_dev + 0.05·Map_dev（Rating/Map 以 V* 为中性锚，中性时 Δ=0）。
PRICING_PERF_WEIGHT = 0.80
PRICING_RATING_WEIGHT = 0.15
PRICING_MAP_WEIGHT = 0.05

# 评分层(15%)：情绪 → 相对 V* 的偏离（中性=0）；形变(form)属表现层，不在此层。
RATING_PRICING_ALPHA = 200.0    # sentiment_index(-1..1) 系数
RATING_PRICING_BETA = 150.0     # hype_index(0..1) 系数
RATING_PRICING_BULL = 80.0      # (bullish_ratio - 0.5) 系数

# 地图层(5%)：战队地图胜率 → 相对 V* 的偏离
MAP_PRICING_SCALE = 200.0       # (avg_win_rate - 0.5) * scale → 偏离（仅在 5% 权重内生效）

# === 策略阈值 ===
# 注：复合定价下 Δ = 0.15·评分层偏离 + 0.05·地图层偏离，典型 |Δ|<30（std≈16.6）。
# 阈值按新量级重标定（≈1 个标准差），仅显著的情绪/地图偏离触发交易信号。
SIGNAL_THETA = 15.0
MOMENTUM_CONFIRM_DAYS = 3
MAX_POSITION_PCT = 0.15
MAX_DRAWDOWN_PCT = 0.20
KELLY_FRACTION = 0.5

# === 情绪管线：BERT 初筛 + LLM 深度分析 ===
SENTIMENT_BERT_MODEL = "uer/roberta-sentiment-chinese"
SENTIMENT_BERT_THRESHOLD = 0.55
SENTIMENT_LLM_ENABLED = False
SENTIMENT_LLM_API_BASE = os.environ.get("VQ_LLM_API_BASE", "")
SENTIMENT_LLM_API_KEY = os.environ.get("VQ_LLM_API_KEY", "")
SENTIMENT_LLM_MODEL = os.environ.get("VQ_LLM_MODEL", "gpt-4o-mini")

# === 回测 ===
BACKTEST_START_DATE = "2024-01-01"
WALKFORWARD_TRAIN_DAYS = 90

# === 比赛模拟器（赛前胜率预测 p̂，FPS 回合制蒙特卡洛）===
# 队伍实力(Glicko-2 均值 + 地图胜率修正) → logistic 单回合胜率 → 13 胜制模拟 → 蒙特卡洛
SIM_LOGISTIC_SCALE = 90.0   # Glicko 分差 → 单回合胜率敏感度（差约 90 ≈ 单回合 ~62%）
SIM_MAP_WEIGHT = 160.0      # 地图胜率修正强度：(该图历史胜率 - 0.5) * weight 加到实力
SIM_MIN_MAP_SAMPLE = 2      # 地图修正所需最小历史场次
SIM_N_SIMS = 2000           # 单场蒙特卡洛模拟次数

# === 运行模式 ===
# True = 离线用合成数据跑通全管线（默认）；False = 真实联网抓取
OFFLINE_MODE = True
