"""vct_quant.collectors.vlr_collector — VCT CN 比赛硬数据采集。

数据源：vlr.gg（备 web.haojiao.cc）。
- 真实模式：抓取 event 页取比赛列表，再逐场抓比赛详情页解析选手统计。
- 离线模式（默认）：合成 VCT CN 风格数据，保证全管线可跑通。

字段：地图胜率、阵容(Agent)、ACS、KAST、首杀FK、存活(KAST/ADR)、HS%。
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from .. import config
from ..storage import repo
from . import net

# VCT CN 赛区样本战队与选手（用于离线合成与真实数据对齐）
TEAMS = {
    "EDG": ["ZmjjKK", "nobody", "asyura", "AFTERHASH", "Life"],
    "FPX": ["AAAAY", "BerLIN", "autumn", "yuetaaa", "yuhaocn"],
    "BLG": ["whzy", "Knight", "yuwin605", "stewen", "Javemes"],
    "TE": ["xccurate", "Freeman", "B1n", "zhengking", "tvvoo"],
    "DRG": ["vo0kash", "Stax", "vortex", "tyson", "Fearless"],
    "NOVA": ["Bialy", "kzz", "Early", "Adler", "Melody"],
}

MAPS = ["Bind", "Haven", "Split", "Lotus", "Pearl", "Ascent", "Sunset"]
AGENTS = ["Jett", "Raze", "Reyna", "Omen", "Chamber", "Killjoy", "Sage", "Sova", "Skye", "Cypher"]

# 特工 → 常用位置（VCT 四类：duelist 决斗 / initiator 先锋 / controller 控场 / sentinel 哨卫）
AGENT_ROLES = {
    # 决斗
    "Jett": "duelist", "Raze": "duelist", "Reyna": "duelist", "Phoenix": "duelist",
    "Neon": "duelist", "Yoru": "duelist", "Iso": "duelist", "Waylay": "duelist",
    # 先锋
    "Sova": "initiator", "Skye": "initiator", "KAY/O": "initiator", "Breach": "initiator",
    "Fade": "initiator", "Gekko": "initiator", "Tejo": "initiator",
    # 控场
    "Omen": "controller", "Brimstone": "controller", "Viper": "controller",
    "Astra": "controller", "Harbor": "controller", "Clove": "controller",
    # 哨卫
    "Cypher": "sentinel", "Killjoy": "sentinel", "Sage": "sentinel",
    "Chamber": "sentinel", "Deadlock": "sentinel", "Vyse": "sentinel",
}
ROLE_CN = {"duelist": "决斗", "initiator": "先锋", "controller": "控场", "sentinel": "哨卫"}

DEFAULT_TOTAL_ROUNDS = 24  # 常规图 13-11；真实解析拿不到比分时的兜底


class VLRCollector:
    """VLR 比赛硬数据采集器。"""

    def __init__(self, offline: bool | None = None):
        self.offline = config.OFFLINE_MODE if offline is None else offline

    def collect(self, conn, n_matches: int = 24, **kwargs) -> int:
        """采集 n 场比赛，写入数据库，返回新增比赛数。"""
        if self.offline:
            records = self._synthetic_matches(n_matches)
        else:
            records = self._fetch_real_matches(n_matches)
        count = 0
        for match in records:
            repo.upsert_match(conn, match["match"])
            for mp in match["maps"]:
                repo.upsert_map(conn, mp)
                for ps in match["stats"].get(mp["id"], []):
                    repo.upsert_player_stats(conn, ps)
            count += 1
        conn.commit()
        return count

    # ---------- 真实抓取 ----------
    def _fetch_real_matches(self, n_matches: int) -> list[dict]:
        event_ids = config.VCT_CN_EVENT_IDS
        results: list[dict] = []
        for eid in event_ids:
            html = net.fetch_html(f"{config.VLR_BASE}/event/matches/{eid}/?group=completed")
            match_ids = self._parse_event_match_list(html)
            for mid in match_ids[:n_matches]:
                try:
                    page = net.fetch_html(f"{config.VLR_BASE}/{mid}")
                    results.append(self._parse_match_page(page, mid))
                except Exception as e:  # noqa: BLE001
                    print(f"[vlr] skip match {mid}: {e}")
        return results

    def _parse_event_match_list(self, html: str) -> list[str]:
        """从 event 页解析已完成比赛 id 列表（vlr.gg 结构可能变动，需现场校验）。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        ids: list[str] = []
        for a in soup.select("a[href^='/']"):
            href = a.get("href", "")
            # vlr 比赛 href 形如 /12345/team-a-vs-team-b
            parts = href.strip("/").split("/")
            if len(parts) == 2 and parts[0].isdigit():
                ids.append(parts[0])
        # 去重保序
        seen = set()
        uniq = [x for x in ids if not (x in seen or seen.add(x))]
        return uniq

    def _parse_match_page(self, html: str, match_id: str) -> dict:
        """解析单场比赛详情页：双方、比分、各图选手统计。结构以现场为准。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # 队伍名与比分（选择器为占位，需按当前 vlr 页面校准）
        team_names = [t.get_text(strip=True) for t in soup.select(".match-header .wf-title")]
        scores = [s.get_text(strip=True) for s in soup.select(".match-header .js-spoiler")]
        team_a = team_names[0] if len(team_names) > 0 else "TBA"
        team_b = team_names[1] if len(team_names) > 1 else "TBA"
        sa = int(scores[0]) if len(scores) > 0 and scores[0].isdigit() else 0
        sb = int(scores[1]) if len(scores) > 1 and scores[1].isdigit() else 0
        match = {
            "id": match_id,
            "event": "VCT CN",
            "date": datetime.now().date().isoformat(),
            "team_a": team_a,
            "team_b": team_b,
            "score_a": sa,
            "score_b": sb,
            "url": f"{config.VLR_BASE}/{match_id}",
        }
        maps: list[dict] = []
        stats: dict[str, list[dict]] = {}
        for idx, mblock in enumerate(soup.select(".vm-stats-game")):
            mid = f"{match_id}_m{idx}"
            # 尽力解析该图比分（vlr 结构可能变动，拿不到用默认回合数兜底）
            map_scores = [
                s.get_text(strip=True)
                for s in mblock.select(".vm-stats-game-header .score")
            ]
            sa = sb = 0
            if len(map_scores) >= 2:
                sa = int(map_scores[0]) if map_scores[0].isdigit() else 0
                sb = int(map_scores[1]) if map_scores[1].isdigit() else 0
            total_rounds = (sa + sb) if (sa + sb) > 0 else DEFAULT_TOTAL_ROUNDS
            mp = {
                "id": mid,
                "match_id": match_id,
                "map_name": MAPS[idx % len(MAPS)],
                "team_a_score": sa or 13,
                "team_b_score": sb or 11,
                "winner": team_a,
                "duration_sec": 2400,
                "site": "vlr.gg",
            }
            maps.append(mp)
            row_stats = []
            for row in mblock.select("tr"):
                cells = [c.get_text(strip=True) for c in row.select("td")]
                if len(cells) < 6:
                    continue
                try:
                    row_stats.append(self._row_to_stat(mid, match_id, cells, team_a, total_rounds))
                except Exception:  # noqa: BLE001
                    continue
            stats[mid] = row_stats
        return {"match": match, "maps": maps, "stats": stats}

    @staticmethod
    def _row_to_stat(map_id, match_id, cells, default_team, total_rounds=DEFAULT_TOTAL_ROUNDS) -> dict:
        def _f(i, cast=float, d=0.0):
            return cast(cells[i]) if i < len(cells) and cells[i] else d
        return {
            "map_id": map_id,
            "match_id": match_id,
            "player_name": cells[0],
            "team": default_team,
            "agent": cells[1] if len(cells) > 1 else "Unknown",
            "acs": _f(2),
            "kills": int(_f(3, float, 0)),
            "deaths": int(_f(4, float, 0)),
            "assists": int(_f(5, float, 0)),
            "kast": _f(6) / 100.0 if _f(6) > 1.2 else _f(6),
            "fk": int(_f(7, float, 0)),
            "fd": int(_f(8, float, 0)),
            "adr": _f(9),
            "hs_pct": _f(10),
            "rounds": total_rounds,
        }

    # ---------- 离线合成 ----------
    def _synthetic_matches(self, n_matches: int) -> list[dict]:
        rng = random.Random(42)
        teams = list(TEAMS.keys())
        start = datetime(2024, 3, 1)
        out: list[dict] = []
        for i in range(n_matches):
            ta, tb = rng.sample(teams, 2)
            date = (start + timedelta(days=i)).date().isoformat()
            n_maps = rng.choice([1, 2, 3])
            sa = sb = 0
            maps: list[dict] = []
            stats: dict[str, list[dict]] = {}
            for mi in range(n_maps):
                mid = f"m{i}_g{mi}"
                a_rounds, b_rounds = 13, rng.choice([7, 9, 11, 13, 14])
                if a_rounds == b_rounds:
                    b_rounds = 11
                winner = ta if a_rounds > b_rounds else tb
                if a_rounds > b_rounds:
                    sa += 1
                else:
                    sb += 1
                mp = {
                    "id": mid,
                    "match_id": f"m{i}",
                    "map_name": rng.choice(MAPS),
                    "team_a_score": a_rounds,
                    "team_b_score": b_rounds,
                    "winner": winner,
                    "duration_sec": rng.randint(1900, 2900),
                    "site": "vlr.gg",
                }
                maps.append(mp)
                stats[mid] = self._synthetic_player_stats(rng, mid, f"m{i}", ta, tb,
                                                          a_rounds=a_rounds, b_rounds=b_rounds)
            out.append({
                "match": {
                    "id": f"m{i}",
                    "event": "VCT CN",
                    "date": date,
                    "team_a": ta,
                    "team_b": tb,
                    "score_a": sa,
                    "score_b": sb,
                    "url": f"{config.VLR_BASE}/m{i}",
                },
                "maps": maps,
                "stats": stats,
            })
        return out

    @staticmethod
    def _synthetic_player_stats(rng, map_id, match_id, ta, tb,
                                a_rounds: int = 13, b_rounds: int = 11) -> list[dict]:
        rows = []
        total_rounds = a_rounds + b_rounds
        for team in (ta, tb):
            for pname in TEAMS[team]:
                star = rng.random() < 0.25  # 明星选手高表现
                base_acs = rng.uniform(250, 320) if star else rng.uniform(150, 230)
                rows.append({
                    "map_id": map_id,
                    "match_id": match_id,
                    "player_name": pname,
                    "team": team,
                    "agent": rng.choice(AGENTS),
                    "acs": round(base_acs + rng.uniform(-15, 15), 1),
                    "kills": rng.randint(8, 28),
                    "deaths": rng.randint(8, 22),
                    "assists": rng.randint(0, 12),
                    "kast": round(rng.uniform(0.60, 0.92), 3),
                    "fk": rng.randint(0, 7),
                    "fd": rng.randint(-4, 4),
                    "adr": round(rng.uniform(90, 180), 1),
                    "hs_pct": round(rng.uniform(18, 38), 1),
                    "rounds": total_rounds,
                })
        return rows
