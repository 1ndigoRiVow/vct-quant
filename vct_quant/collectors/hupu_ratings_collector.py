"""Hupu post-match player rating and comment collector.

Observed public entry points:
- Topic board: https://bbs.hupu.com/803 and https://bbs.hupu.com/869 list
  Valorant/VCT threads. Static HTML exposes title, author, time, reply/view
  counts and some visible replies.
- Rating pages: https://m.hupu.com/score-list/common_first/<id> lists score
  items, while https://m.hupu.com/score-item/common_second/<id> exposes one
  item's average score, "JRs评分" count, five bucket percentages, and visible
  comments.

Anonymous access can read the public score/list/thread HTML captured above.
Some comments and interactive rating actions may require a logged-in Hupu app
session. Online mode reads HUPU_COOKIE from the environment when available,
never attempts to bypass captchas or risk controls, and returns partial data
when a page cannot be fetched or parsed.

Offline mode is the default through config.OFFLINE_MODE. It synthesizes stable
match ratings and comments from the known VCT CN roster so the whole pipeline
can run without network access.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urljoin, urlparse

from .. import config
from ..storage import db as dbmod
from ..storage import repo
from . import net
from .vlr_collector import TEAMS

PLAYERS_TEAMS = {player: team for team, players in TEAMS.items() for player in players}

POSITIVE_COMMENTS = [
    "{p} 今天这个发挥真像把鼠标焊手上了，残局一点不慌。",
    "{team} 这场赢得干净，{p} 的首杀价值太高了。",
    "{p} 这评分低了吧，关键回合全是他在兜底。",
    "这把看完只想加仓 {p}，状态回来得很明显。",
]
NEGATIVE_COMMENTS = [
    "{p} 今天有点迷，几波前压看得人血压上来。",
    "{team} 这图输得不冤，{p} 的timing全错开了。",
    "别只看击杀，{p} 好几波白给太伤节奏。",
    "{p} 这个分我觉得还偏高，观感真的一般。",
]
SARCASM_COMMENTS = [
    "{p} 这波太团队了，直接把优势送回五五开。",
    "懂了，{p} 是在藏战术，藏到观众都看不懂。",
    "{team} 粉丝今天心率训练拉满，建议计入健身时长。",
]
NEUTRAL_COMMENTS = [
    "这场节奏挺怪，{team} 中期暂停以后明显变慢了。",
    "{p} 数据不算炸，但几个道具细节还可以。",
    "下一场如果还是这套阵容，{team} 得把默认做扎实点。",
]


class HupuRatingsCollector:
    """Collect Hupu post-match player ratings and comments."""

    def __init__(self, offline: bool | None = None):
        self.offline = config.OFFLINE_MODE if offline is None else offline

    def collect(
        self,
        conn,
        match_ids: list[str] | None = None,
        n_comments: int = 200,
        **kwargs,
    ) -> dict:
        """Collect ratings/comments, write them through repo upserts, and return counts."""
        force = bool(kwargs.get("force", False))
        target_match_ids = self._resolve_match_ids(conn, match_ids)
        existing = self._existing_rating_match_ids(conn) if not force else set()
        target_match_ids = [mid for mid in target_match_ids if mid not in existing]

        if not target_match_ids:
            print("[hupu] no new matches to collect")
            return {"ratings": 0, "comments": 0}

        if self.offline:
            ratings, comments = self._synthetic_records(target_match_ids, n_comments)
        else:
            ratings, comments = self._fetch_real_records(target_match_ids, n_comments, **kwargs)

        rating_count = 0
        for rating in ratings:
            repo.upsert_hupu_rating(conn, rating)
            rating_count += 1

        comment_count = 0
        for comment in comments:
            repo.upsert_hupu_comment(conn, comment)
            comment_count += 1

        conn.commit()
        print(f"[hupu] stored ratings={rating_count}, comments={comment_count}")
        return {"ratings": rating_count, "comments": comment_count}

    # ---------- Incremental planning ----------
    @staticmethod
    def _existing_rating_match_ids(conn) -> set[str]:
        try:
            rows = conn.execute("SELECT DISTINCT match_id FROM hupu_match_ratings").fetchall()
        except Exception:  # noqa: BLE001
            return set()
        return {r["match_id"] for r in rows if r["match_id"]}

    @staticmethod
    def _resolve_match_ids(conn, match_ids: list[str] | None) -> list[str]:
        if match_ids:
            return match_ids
        try:
            rows = conn.execute("SELECT id FROM matches ORDER BY date DESC, id LIMIT 8").fetchall()
        except Exception:  # noqa: BLE001
            rows = []
        ids = [r["id"] for r in rows]
        return ids or ["m0", "m1", "m2"]

    # ---------- Online collection ----------
    def _fetch_real_records(
        self,
        match_ids: list[str],
        n_comments: int,
        **kwargs,
    ) -> tuple[list[dict], list[dict]]:
        urls = self._normalize_urls(kwargs)
        if not urls:
            urls = [f"{config.HUPU_BASE}/803", f"{config.HUPU_BASE}/869"]
            print("[hupu] no URL supplied; probing public Valorant boards")

        ratings: list[dict] = []
        comments: list[dict] = []
        per_page_limit = max(1, n_comments // max(1, len(urls)))

        for idx, url in enumerate(urls):
            match_id = match_ids[min(idx, len(match_ids) - 1)]
            try:
                html = self._fetch_hupu_html(url)
            except Exception as exc:  # noqa: BLE001
                print(f"[hupu] fetch failed: {url} -> {exc}")
                continue

            try:
                page_ratings, page_comments = self._parse_hupu_page(
                    html, url, match_id, per_page_limit
                )
                ratings.extend(page_ratings)
                comments.extend(page_comments)
                print(
                    f"[hupu] parsed {url}: ratings={len(page_ratings)}, "
                    f"comments={len(page_comments)}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[hupu] parse failed: {url} -> {exc}")

        return ratings, comments[:n_comments]

    @staticmethod
    def _normalize_urls(kwargs: dict) -> list[str]:
        raw = (
            kwargs.get("urls")
            or kwargs.get("hupu_urls")
            or kwargs.get("score_urls")
            or kwargs.get("thread_urls")
            or []
        )
        if isinstance(raw, str):
            raw = [raw]
        return [str(url) for url in raw if str(url).strip()]

    def _fetch_hupu_html(self, url: str) -> str:
        headers = {"User-Agent": config.USER_AGENT}
        cookie = os.environ.get("HUPU_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        return net.fetch_html(url, headers=headers)

    def _parse_hupu_page(
        self,
        html: str,
        url: str,
        match_id: str,
        n_comments: int,
    ) -> tuple[list[dict], list[dict]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        parsed_url = urlparse(url)
        ratings: list[dict] = []
        if "/score-list/" in parsed_url.path:
            ratings = self._parse_score_list(soup, url, match_id)
        elif "/score-item/" in parsed_url.path:
            rating = self._parse_score_item(soup, url, match_id)
            ratings = [rating] if rating else []
        else:
            ratings = self._parse_embedded_ratings(soup, match_id)

        comments = self._parse_comments(soup, url, match_id, n_comments)
        return ratings, comments

    def _parse_score_list(self, soup, url: str, match_id: str) -> list[dict]:
        text = self._clean_text(soup.get_text(" ", strip=True))
        lines = [line for line in re.split(r"\s{2,}|(?<=评分)\s+", text) if line.strip()]
        ratings: list[dict] = []

        for line in lines:
            found = re.search(r"(?P<name>[\w\u4e00-\u9fff.·-]{2,30}).{0,30}?(?P<avg>\d+(?:\.\d)?)\s+(?P<count>\d+)\s*JRs评分", line)
            if found:
                name = found.group("name").strip()
                ratings.append(self._rating(match_id, name, found.group("avg"), found.group("count")))

        for link in soup.select("a[href*='/score-item/']"):
            block = self._clean_text(link.get_text(" ", strip=True))
            found = re.search(r"(?P<name>[\w\u4e00-\u9fff.·-]{2,30}).*?(?P<avg>\d+(?:\.\d)?)\s+(?P<count>\d+)\s*JRs评分", block)
            if found:
                ratings.append(self._rating(match_id, found.group("name"), found.group("avg"), found.group("count")))

        return self._dedupe_ratings(ratings)

    def _parse_score_item(self, soup, url: str, match_id: str) -> dict | None:
        text = self._clean_text(soup.get_text(" ", strip=True))
        found = re.search(r"(?P<name>[\w\u4e00-\u9fff.·-]{2,30}).{0,80}?(?P<avg>\d+(?:\.\d)?)\s+(?P<count>\d+)\s*JRs评分", text)
        if not found:
            found = re.search(r"(?P<avg>\d+(?:\.\d)?)\s+(?P<count>\d+)\s*JRs评分", text)
        if not found:
            return None

        title = self._title_text(soup)
        name = found.groupdict().get("name") or title or self._item_id(url)
        dist = self._rating_dist(text, int(found.group("count")))
        return self._rating(match_id, name, found.group("avg"), found.group("count"), dist)

    def _parse_embedded_ratings(self, soup, match_id: str) -> list[dict]:
        text = self._clean_text(soup.get_text(" ", strip=True))
        ratings: list[dict] = []
        patterns = [
            r"(?P<name>[\w\u4e00-\u9fff.·-]{2,30}).{0,18}?(?P<avg>\d+(?:\.\d)?)\s*分.{0,10}?(?P<count>\d+)\s*JRs?评分",
            r"(?P<name>[\w\u4e00-\u9fff.·-]{2,30}).{0,18}?(?P<avg>\d+(?:\.\d)?)\s+(?P<count>\d+)\s*JRs?评分",
        ]
        for pattern in patterns:
            for found in re.finditer(pattern, text):
                ratings.append(self._rating(match_id, found.group("name"), found.group("avg"), found.group("count")))
        return self._dedupe_ratings(ratings)

    def _parse_comments(self, soup, url: str, match_id: str, n_comments: int) -> list[dict]:
        candidates = soup.select(
            ".reply-list li, .post-reply-list li, .comment-list li, "
            ".reply-item, .comment-item, [class*='reply'], [class*='comment']"
        )
        out: list[dict] = []
        thread_id = self._thread_id(url)

        for floor, node in enumerate(candidates, start=1):
            content = self._clean_text(node.get_text(" ", strip=True))
            if len(content) < 4 or content in {"回复", "举报", "收藏", "推荐"}:
                continue
            author_node = node.select_one(".author, .user-name, [class*='author'], [class*='user']")
            time_node = node.select_one("time, .time, [class*='time']")
            out.append({
                "id": self._comment_id(match_id, thread_id, floor),
                "match_id": match_id,
                "thread_id": thread_id,
                "page": self._page_number(url),
                "author": self._clean_text(author_node.get_text(" ", strip=True)) if author_node else "",
                "content": content[:1000],
                "floor": floor,
                "like_count": self._first_int(content, default=0),
                "post_time": self._clean_text(time_node.get_text(" ", strip=True)) if time_node else "",
            })
            if len(out) >= n_comments:
                break

        if out:
            return out

        # Search-result snippets often expose useful visible replies as plain text.
        text = self._clean_text(soup.get_text(" ", strip=True))
        snippets = [s.strip() for s in re.split(r"全部回帖|这些回帖亮了|收起|引用", text) if len(s.strip()) > 20]
        for floor, snippet in enumerate(snippets[:n_comments], start=1):
            out.append({
                "id": self._comment_id(match_id, thread_id, floor),
                "match_id": match_id,
                "thread_id": thread_id,
                "page": self._page_number(url),
                "author": "",
                "content": snippet[:1000],
                "floor": floor,
                "like_count": 0,
                "post_time": "",
            })
        return out

    # ---------- Offline synthesis ----------
    def _synthetic_records(
        self,
        match_ids: list[str],
        n_comments: int,
    ) -> tuple[list[dict], list[dict]]:
        ratings: list[dict] = []
        comments: list[dict] = []
        teams = list(TEAMS.keys())
        comments_per_match = max(1, n_comments // max(1, len(match_ids)))

        for idx, match_id in enumerate(match_ids):
            rng = random.Random(f"hupu-ratings|{match_id}")
            team_a, team_b = teams[idx % len(teams)], teams[(idx + 1) % len(teams)]
            for team in (team_a, team_b):
                for player in TEAMS[team]:
                    ratings.append(self._synthetic_rating(rng, match_id, team, player))
            comments.extend(self._synthetic_comments(rng, match_id, team_a, team_b, comments_per_match))

        return ratings, comments[:n_comments]

    def _synthetic_rating(self, rng: random.Random, match_id: str, team: str, player: str) -> dict:
        star_boost = 0.7 if player in {"ZmjjKK", "whzy", "AAAAY", "nobody", "Life"} else 0.0
        avg = min(9.8, max(4.6, rng.gauss(7.1 + star_boost, 1.05)))
        count = rng.randint(260, 3000) if star_boost else rng.randint(50, 1600)
        dist = self._synthetic_dist(avg, count)
        return {
            "id": f"{match_id}|{player}",
            "match_id": match_id,
            "player_name": player,
            "team": team,
            "rating_avg": round(avg, 1),
            "rating_count": count,
            "rating_dist": json.dumps(dist, ensure_ascii=False, sort_keys=True),
        }

    @staticmethod
    def _synthetic_dist(avg: float, count: int) -> dict[str, int]:
        center = max(1, min(10, round(avg)))
        weights = {score: max(0.03, 1.0 / (abs(score - center) + 1.0)) for score in range(1, 11)}
        total = sum(weights.values())
        dist = {str(score): int(count * weights[score] / total) for score in range(1, 11)}
        dist[str(center)] += count - sum(dist.values())
        return dist

    def _synthetic_comments(
        self,
        rng: random.Random,
        match_id: str,
        team_a: str,
        team_b: str,
        n_comments: int,
    ) -> list[dict]:
        start = datetime(2024, 3, 1) + timedelta(days=abs(hash(match_id)) % 180)
        thread_id = f"synthetic-{match_id}"
        out: list[dict] = []
        players = [(team, p) for team in (team_a, team_b) for p in TEAMS[team]]

        for floor in range(1, n_comments + 1):
            team, player = rng.choice(players)
            roll = rng.random()
            if roll < 0.36:
                tpl = rng.choice(POSITIVE_COMMENTS)
            elif roll < 0.66:
                tpl = rng.choice(NEGATIVE_COMMENTS)
            elif roll < 0.82:
                tpl = rng.choice(SARCASM_COMMENTS)
            else:
                tpl = rng.choice(NEUTRAL_COMMENTS)
            out.append({
                "id": self._comment_id(match_id, thread_id, floor),
                "match_id": match_id,
                "thread_id": thread_id,
                "page": 1 + (floor - 1) // 20,
                "author": f"虎扑JR{rng.randint(1000000000, 9999999999)}",
                "content": tpl.format(p=player, team=team),
                "floor": floor,
                "like_count": rng.randint(0, 260),
                "post_time": (start + timedelta(minutes=floor * 3)).isoformat(timespec="minutes"),
            })
        return out

    # ---------- Small helpers ----------
    @staticmethod
    def _rating(
        match_id: str,
        player_name: str,
        rating_avg: str | float,
        rating_count: str | int,
        rating_dist: dict[str, int] | None = None,
    ) -> dict:
        name = player_name.strip()
        return {
            "id": f"{match_id}|{name}",
            "match_id": match_id,
            "player_name": name,
            "team": PLAYERS_TEAMS.get(name),
            "rating_avg": float(rating_avg),
            "rating_count": int(rating_count),
            "rating_dist": json.dumps(rating_dist, ensure_ascii=False, sort_keys=True) if rating_dist else None,
        }

    @staticmethod
    def _dedupe_ratings(ratings: Iterable[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for rating in ratings:
            key = rating["id"]
            if key in seen:
                continue
            seen.add(key)
            out.append(rating)
        return out

    @staticmethod
    def _rating_dist(text: str, count: int) -> dict[str, int] | None:
        percentages = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", text)]
        if len(percentages) < 5:
            return None
        buckets = ["10", "8", "6", "4", "2"]
        dist = {bucket: int(count * pct / 100.0) for bucket, pct in zip(buckets, percentages[:5])}
        remainder = count - sum(dist.values())
        dist["10"] = dist.get("10", 0) + remainder
        return dist

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _title_text(soup) -> str:
        title = soup.select_one("h1, title")
        if not title:
            return ""
        text = title.get_text(" ", strip=True)
        return re.sub(r"[_-].*$", "", text).strip()

    @staticmethod
    def _item_id(url: str) -> str:
        parts = [p for p in urlparse(url).path.split("/") if p]
        return parts[-1] if parts else "unknown"

    @staticmethod
    def _thread_id(url: str) -> str:
        path = urlparse(url).path
        found = re.search(r"/(?:bbs/)?(\d+)(?:-\d+)?\.html", path)
        if found:
            return found.group(1)
        return path.strip("/") or url

    @staticmethod
    def _page_number(url: str) -> int:
        found = re.search(r"-(\d+)\.html", urlparse(url).path)
        return int(found.group(1)) if found else 1

    @staticmethod
    def _first_int(text: str, default: int = 0) -> int:
        found = re.search(r"\d+", text)
        return int(found.group(0)) if found else default

    @staticmethod
    def _comment_id(match_id: str, thread_id: str, floor: int) -> str:
        raw = f"{match_id}|{thread_id}|{floor}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()


if __name__ == "__main__":
    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        result = HupuRatingsCollector(offline=True).collect(conn, match_ids=["demo-hupu"], n_comments=12)
        print(f"[hupu] demo complete: {result}")
        for table in ("hupu_match_ratings", "hupu_comments"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            sample = conn.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
            print(f"[hupu] {table}: {n} rows")
            for row in sample:
                print(dict(row))
    finally:
        conn.close()
