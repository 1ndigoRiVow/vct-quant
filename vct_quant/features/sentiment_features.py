"""vct_quant.features.sentiment_features — 舆情情绪管线：BERT 初筛 + LLM 深度分析。

流程：对每条帖子用 BERT 做情感初筛 → 命中选手归属 →
低置信或含黑话/反讽则交 LLM 深度抽取看好度 → 输出 sentiment/bullish/confidence。
所有重依赖(transformers/openai)均有轻量回退，保证离线可跑。
"""
from __future__ import annotations

import re
import statistics
import uuid

from .. import config
from ..collectors.vlr_collector import TEAMS
from ..storage import repo

PLAYERS = {p: t for t, ps in TEAMS.items() for p in ps}

POS = {"猛", "涨", "冲", "神", "稳", "强", "看好", "洼地", "加仓", "无敌", "定海神针", "C", "c"}
NEG = {"拉胯", "隐身", "跌", "空", "泡沫", "跑", "替补", "废", "菜", "下滑", "塌", "白给"}
SARCASM_MARKERS = ["狗头", "反向", "懂的都懂", "绝绝子", "→", "？", "冲冲冲", "快跑", "问问"]


class SentimentPipeline:
    """BERT 初筛 + LLM 深度的舆情情绪抽取管线。"""

    def __init__(self):
        self._bert = _BertGate()
        self._llm = _LlmGate()

    def analyze_posts(self, conn, limit: int = 500) -> int:
        """对未处理帖子抽取情绪并落库 sentiments，返回新增条数。"""
        rows = conn.execute(
            """SELECT * FROM posts WHERE id NOT IN (SELECT post_id FROM sentiments)
               ORDER BY post_time DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        n = 0
        for post in rows:
            for item in self._analyze_one(post):
                repo.upsert_sentiment(conn, item)
                n += 1
        conn.commit()
        return n

    def _analyze_one(self, post) -> list[dict]:
        text = post["content"] or ""
        mentioned = [p for p in PLAYERS if p in text]
        if not mentioned:
            return []
        label, score = self._bert.predict(text)
        sarcasm = any(m in text for m in SARCASM_MARKERS)
        use_llm = (score < config.SENTIMENT_BERT_THRESHOLD) or sarcasm
        if use_llm:
            bullish, conf, method = self._llm.analyze(text)
        else:
            bullish = _map_bullish(label, score)
            conf = score
            method = "bert"
        sentiment_score = bullish * 2 - 1  # 0..1 -> -1..1
        out = []
        for p in mentioned:
            out.append({
                "post_id": post["id"],
                "player_name": p,
                "team": PLAYERS[p],
                "sentiment_score": round(sentiment_score, 3),
                "bullish_score": round(bullish, 3),
                "confidence": round(conf, 3),
                "method": method,
            })
        return out


class _BertGate:
    """BERT 情感初筛：优先 HuggingFace 中文模型，缺失则词典回退。"""

    def __init__(self):
        self._model = None
        self._tok = None
        self._ready = False
        try:  # 延迟导入，避免无 transformers 环境报错
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa
            import torch  # noqa
            self._AutoModel = AutoModelForSequenceClassification
            self._AutoTok = AutoTokenizer
            self._torch = torch
        except Exception:  # noqa: BLE001
            self._AutoModel = None

    def predict(self, text: str) -> tuple[str, float]:
        if self._AutoModel and not self._ready:
            try:
                self._tok = self._AutoTok.from_pretrained(config.SENTIMENT_BERT_MODEL)
                self._model = self._AutoModel.from_pretrained(config.SENTIMENT_BERT_MODEL)
                self._model.eval()
                self._ready = True
            except Exception:  # noqa: BLE001
                self._ready = False
        if self._ready:
            try:
                with self._torch.no_grad():
                    inp = self._tok(text, return_tensors="pt", truncation=True, max_length=128)
                    logits = self._model(**inp).logits[0]
                    probs = self._torch.softmax(logits, dim=0).tolist()
                idx = int(probs.index(max(probs)))
                labels = ["negative", "neutral", "positive"]
                return labels[idx], float(probs[idx])
            except Exception:  # noqa: BLE001
                pass
        return _lexicon_predict(text)


def _lexicon_predict(text: str) -> tuple[str, float]:
    pos = sum(1 for w in POS if w in text)
    neg = sum(1 for w in NEG if w in text)
    if pos == neg:
        return "neutral", 0.5
    if pos > neg:
        return "positive", min(0.9, 0.55 + 0.1 * (pos - neg))
    return "negative", min(0.9, 0.55 + 0.1 * (neg - pos))


def _map_bullish(label: str, score: float) -> float:
    base = {"positive": 0.85, "neutral": 0.5, "negative": 0.15}[label]
    return round(min(0.99, max(0.01, base * (0.6 + 0.4 * score))), 3)


class _LlmGate:
    """LLM 深度分析：调用 OpenAI 兼容接口抽取看好度；未配置则黑话规则回退。"""

    def __init__(self):
        self._client = None
        if config.SENTIMENT_LLM_ENABLED and config.SENTIMENT_LLM_API_BASE:
            try:
                from openai import OpenAI  # noqa
                self._OpenAI = OpenAI
            except Exception:  # noqa: BLE001
                self._OpenAI = None
        else:
            self._OpenAI = None

    def analyze(self, text: str) -> tuple[float, float, str]:
        if self._OpenAI:
            try:
                client = self._OpenAI(
                    base_url=config.SENTIMENT_LLM_API_BASE,
                    api_key=config.SENTIMENT_LLM_API_KEY or "none",
                )
                resp = client.chat.completions.create(
                    model=config.SENTIMENT_LLM_MODEL,
                    messages=[
                        {"role": "system", "content": (
                            "你是电竞选手舆情分析师。对帖子判断对选手的看好度(0最看空,1最看多),"
                            "注意黑话、反讽、狗头。仅返回 JSON: {\"bullish\":0-1,\"confidence\":0-1}。")},
                        {"role": "user", "content": text},
                    ],
                    temperature=0.2,
                )
                import json
                data = json.loads(re.search(r"\{.*\}", resp.choices[0].message.content, re.S).group(0))
                return float(data["bullish"]), float(data.get("confidence", 0.7)), "llm"
            except Exception:  # noqa: BLE001
                pass
        # 黑话/反讽规则回退
        bullish, conf = _sarcasm_rule(text)
        return bullish, conf, "llm_rule"


def _sarcasm_rule(text: str) -> tuple[float, float]:
    """反讽检测：含狗头/反向/冲冲冲→快跑等反转信号。"""
    reversed_signal = any(m in text for m in ["狗头", "反向", "冲冲冲", "→", "快跑", "问问"])
    pos = sum(1 for w in POS if w in text)
    neg = sum(1 for w in NEG if w in text)
    raw = 0.5 + 0.12 * (pos - neg)
    if reversed_signal:
        raw = 1 - raw  # 反转
    return min(0.99, max(0.01, raw)), 0.7


def player_sentiment_features(conn, player_name: str, days: int = 30) -> dict | None:
    rows = repo.get_recent_sentiments(conn, player_name, days)
    if not rows:
        return None
    sentiments = [r["sentiment_score"] for r in rows]
    bullish = [r["bullish_score"] for r in rows]
    confs = [r["confidence"] for r in rows]
    # 热度：提及量 × 平均互动（用 conf 近似）
    hype = min(1.0, len(rows) / 20.0) * (statistics.mean(confs) if confs else 0.5)
    # 情绪动量：后一半均值 - 前一半均值
    half = max(1, len(sentiments) // 2)
    recent_m = statistics.mean(sentiments[:half])
    old_m = statistics.mean(sentiments[half:]) if len(sentiments) > half else recent_m
    momentum = recent_m - old_m
    return {
        "player_name": player_name,
        "n_mentions": len(rows),
        "sentiment_mean": round(statistics.mean(sentiments), 3),
        "bullish_ratio": round(statistics.mean(bullish), 3),
        "hype_index": round(hype, 3),
        "sentiment_momentum": round(momentum, 3),
    }
