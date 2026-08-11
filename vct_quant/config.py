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

# 情绪定价：把情绪因子映射为市场隐含估值 P
#   P = base + alpha * sentiment_index + beta * hype_index
SENTIMENT_PRICING_ALPHA = 200.0
SENTIMENT_PRICING_BETA = 150.0

# === 策略阈值 ===
SIGNAL_THETA = 120.0
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

# === 运行模式 ===
# True = 离线用合成数据跑通全管线（默认）；False = 真实联网抓取
OFFLINE_MODE = True
