"""vct_quant.collectors.sentiment_collector — 虎扑/百度贴吧舆情文本采集。

- 真实模式：抓取虎扑话题区与贴吧搜索结果帖/回复。
- 离线模式（默认）：合成带情绪、黑话、反讽的社区文本，供 BERT+LLM 管线演练。
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from .. import config
from ..collectors.vlr_collector import TEAMS
from . import net

# 选手 -> 所属战队，用于把舆情归属到选手
PLAYERS_TEAMS = {p: t for t, ps in TEAMS.items() for p in ps}

POSITIVE_TEMPLATES = [
    "{p} 这波真的猛，ACS 怎么这么稳，看涨！",
    "绝了 {p} 首杀拿麻了，这种状态不冲等什么",
    "{p} 才是定海神针，队伍没他不行，价值洼地",
]
NEGATIVE_TEMPLATES = [
    "{p} 今天隐身了吧，数据一塌糊涂，该跑了",
    "{p} 状态下滑太明显，再跌就要替补了，看空",
    "别吹 {p} 了，遇到强队就拉胯，泡沫。",
]
SARCASM_TEMPLATES = [
    "{p} 太厉害了，又被1v3反杀，这波值不值钱？（狗头）",
    "还得是 {p}，五杀变白给，绝绝子，冲冲冲→快跑",
    "兄弟们 {p} 这状态，下把必C，懂得都懂，反向加仓。",
]
NEUTRAL_TEMPLATES = [
    "今天 {team} 对阵看谁赢，感觉五五开。",
    "求分析 {p} 这版本适合什么阵容？",
    "这赛程安排有点密，{team} 体能顶得住吗。",
]


class HupuTiebaCollector:
    """虎扑 + 百度贴吧舆情采集器。"""

    def __init__(self, offline: bool | None = None):
        self.offline = config.OFFLINE_MODE if offline is None else offline

    def collect(self, conn, n_posts: int = 60, **kwargs) -> int:
        posts = self._synthetic_posts(n_posts) if self.offline else self._fetch_real_posts(n_posts)
        from ..storage import repo
        count = 0
        for p in posts:
            repo.upsert_post(conn, p)
            count += 1
        conn.commit()
        return count

    # ---------- 真实抓取 ----------
    def _fetch_real_posts(self, n_posts: int) -> list[dict]:
        posts: list[dict] = []
        posts += self._fetch_hupu(n_posts // 2)
        posts += self._fetch_tieba(n_posts - len(posts))
        return posts[:n_posts]

    def _fetch_hupu(self, n: int) -> list[dict]:
        # 虎扑话题区列表（结构需现场校验）
        url = f"{config.HUPU_BASE}/vct"  # 占位板块
        try:
            html = net.fetch_html(url)
        except Exception as e:  # noqa: BLE001
            print(f"[hupu] fetch failed: {e}")
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for a in soup.select("a[href*='/thread']")[:n]:
            out.append({
                "id": str(uuid.uuid4()),
                "source": "hupu",
                "thread_id": a.get("href", ""),
                "author": "",
                "content": a.get_text(strip=True),
                "post_time": datetime.now().isoformat(timespec="seconds"),
                "reply_count": 0,
            })
        return out

    def _fetch_tieba(self, n: int) -> list[dict]:
        url = f"{config.TIEBA_BASE}/f?kw=无畏契约&ie=utf-8"
        try:
            html = net.fetch_html(url)
        except Exception as e:  # noqa: BLE001
            print(f"[tieba] fetch failed: {e}")
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for item in soup.select("a.j_th_tit, .threadlist_title a")[:n]:
            out.append({
                "id": str(uuid.uuid4()),
                "source": "tieba",
                "thread_id": item.get("href", ""),
                "author": "",
                "content": item.get_text(strip=True),
                "post_time": datetime.now().isoformat(timespec="seconds"),
                "reply_count": 0,
            })
        return out

    # ---------- 离线合成 ----------
    def _synthetic_posts(self, n_posts: int) -> list[dict]:
        rng = random.Random(7)
        players = list(PLAYERS_TEAMS.keys())
        start = datetime(2024, 3, 1)
        posts: list[dict] = []
        for i in range(n_posts):
            p = rng.choice(players)
            team = PLAYERS_TEAMS[p]
            roll = rng.random()
            if roll < 0.35:
                tpl = rng.choice(POSITIVE_TEMPLATES)
            elif roll < 0.65:
                tpl = rng.choice(NEGATIVE_TEMPLATES)
            elif roll < 0.80:
                tpl = rng.choice(SARCASM_TEMPLATES)
            else:
                tpl = rng.choice(NEUTRAL_TEMPLATES).replace("{team}", team)
            content = tpl.format(p=p) if "{p}" in tpl else tpl
            posts.append({
                "id": str(uuid.uuid4()),
                "source": rng.choice(["hupu", "tieba"]),
                "thread_id": str(rng.randint(10000, 99999)),
                "author": f"user{rng.randint(100, 999)}",
                "content": content,
                "post_time": (start + timedelta(hours=i)).isoformat(timespec="hours"),
                "reply_count": rng.randint(0, 200),
            })
        return posts
