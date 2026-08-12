"""vct_quant.storage.repo — CRUD 仓储。所有写入走 upsert，保证可重入。"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from . import db as dbmod


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_match(conn, m: dict) -> None:
    conn.execute(
        """INSERT INTO matches(id,event,date,team_a,team_b,score_a,score_b,url,fetched_at)
           VALUES (:id,:event,:date,:team_a,:team_b,:score_a,:score_b,:url,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             event=excluded.event, date=excluded.date, team_a=excluded.team_a,
             team_b=excluded.team_b, score_a=excluded.score_a, score_b=excluded.score_b,
             url=excluded.url, fetched_at=excluded.fetched_at""",
        {**m, "fetched_at": _now()},
    )


def upsert_map(conn, mp: dict) -> None:
    conn.execute(
        """INSERT INTO maps(id,match_id,map_name,team_a_score,team_b_score,winner,duration_sec,site)
           VALUES (:id,:match_id,:map_name,:team_a_score,:team_b_score,:winner,:duration_sec,:site)
           ON CONFLICT(id) DO UPDATE SET
             match_id=excluded.match_id, map_name=excluded.map_name,
             team_a_score=excluded.team_a_score, team_b_score=excluded.team_b_score,
             winner=excluded.winner, duration_sec=excluded.duration_sec, site=excluded.site""",
        mp,
    )


def upsert_player_stats(conn, ps: dict) -> None:
    # 稳定 id：同一选手同一图只保留一行，保证可重入去重
    ps = {**ps, "id": ps.get("id") or f"{ps['map_id']}|{ps['player_name']}"}
    conn.execute(
        """INSERT INTO player_stats
             (id,map_id,match_id,player_name,team,agent,acs,kills,deaths,assists,
              kast,fk,fd,adr,hs_pct,rounds)
           VALUES
             (:id,:map_id,:match_id,:player_name,:team,:agent,:acs,:kills,:deaths,:assists,
              :kast,:fk,:fd,:adr,:hs_pct,:rounds)
           ON CONFLICT(id) DO UPDATE SET
             acs=excluded.acs, kills=excluded.kills, deaths=excluded.deaths,
             assists=excluded.assists, kast=excluded.kast, fk=excluded.fk, fd=excluded.fd,
             adr=excluded.adr, hs_pct=excluded.hs_pct, rounds=excluded.rounds""",
        ps,
    )


def upsert_post(conn, p: dict) -> None:
    conn.execute(
        """INSERT INTO posts(id,source,thread_id,author,content,post_time,reply_count,fetched_at)
           VALUES (:id,:source,:thread_id,:author,:content,:post_time,:reply_count,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             content=excluded.content, post_time=excluded.post_time,
             reply_count=excluded.reply_count, fetched_at=excluded.fetched_at""",
        {**p, "fetched_at": _now()},
    )


def upsert_sentiment(conn, s: dict) -> None:
    s = {**s, "id": s.get("id") or str(uuid.uuid4()), "created_at": _now()}
    conn.execute(
        """INSERT INTO sentiments
             (id,post_id,player_name,team,sentiment_score,bullish_score,confidence,method,created_at)
           VALUES
             (:id,:post_id,:player_name,:team,:sentiment_score,:bullish_score,
              :confidence,:method,:created_at)
           ON CONFLICT(id) DO UPDATE SET
             sentiment_score=excluded.sentiment_score, bullish_score=excluded.bullish_score,
             confidence=excluded.confidence, method=excluded.method""",
        s,
    )


def upsert_rating(conn, r: dict) -> None:
    conn.execute(
        """INSERT INTO player_ratings(player_name,rating,rd,vol,updated_at)
           VALUES (:player_name,:rating,:rd,:vol,:updated_at)
           ON CONFLICT(player_name) DO UPDATE SET
             rating=excluded.rating, rd=excluded.rd, vol=excluded.vol,
             updated_at=excluded.updated_at""",
        {**r, "updated_at": _now()},
    )


def upsert_player_profile(conn, p: dict) -> None:
    conn.execute(
        """INSERT INTO player_profiles
             (player_name,team,main_role,role_share,total_rounds,rounds_by_agent,top_agents,
              kills,deaths,assists,kda,acs,adr,fk,fd,n_maps,updated_at)
           VALUES
             (:player_name,:team,:main_role,:role_share,:total_rounds,:rounds_by_agent,:top_agents,
              :kills,:deaths,:assists,:kda,:acs,:adr,:fk,:fd,:n_maps,:updated_at)
           ON CONFLICT(player_name) DO UPDATE SET
             team=excluded.team, main_role=excluded.main_role, role_share=excluded.role_share,
             total_rounds=excluded.total_rounds, rounds_by_agent=excluded.rounds_by_agent,
             top_agents=excluded.top_agents, kills=excluded.kills, deaths=excluded.deaths,
             assists=excluded.assists, kda=excluded.kda, acs=excluded.acs, adr=excluded.adr,
             fk=excluded.fk, fd=excluded.fd, n_maps=excluded.n_maps, updated_at=excluded.updated_at""",
        {**p, "updated_at": _now()},
    )


def upsert_player_team(conn, pt: dict) -> None:
    conn.execute(
        """INSERT INTO player_teams(player_name,team,evidence,updated_at)
           VALUES (:player_name,:team,:evidence,:updated_at)
           ON CONFLICT(player_name) DO UPDATE SET
             team=excluded.team, evidence=excluded.evidence, updated_at=excluded.updated_at""",
        {**pt, "updated_at": _now()},
    )


def upsert_hupu_rating(conn, r: dict) -> None:
    r = {
        **r,
        "id": r.get("id") or f"{r['match_id']}|{r['player_name']}",
        "fetched_at": r.get("fetched_at") or _now(),
    }
    conn.execute(
        """INSERT INTO hupu_match_ratings
             (id,match_id,player_name,team,rating_avg,rating_count,rating_dist,fetched_at)
           VALUES
             (:id,:match_id,:player_name,:team,:rating_avg,:rating_count,:rating_dist,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             rating_avg=excluded.rating_avg, rating_count=excluded.rating_count,
             rating_dist=excluded.rating_dist, fetched_at=excluded.fetched_at""",
        r,
    )


def upsert_hupu_comment(conn, c: dict) -> None:
    c = {
        **c,
        "id": c.get("id") or str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"hupu|{c.get('match_id', '')}|{c.get('thread_id', '')}|{c.get('floor', '')}",
        )),
        "fetched_at": c.get("fetched_at") or _now(),
    }
    conn.execute(
        """INSERT INTO hupu_comments
             (id,match_id,thread_id,page,author,content,floor,like_count,post_time,fetched_at)
           VALUES
             (:id,:match_id,:thread_id,:page,:author,:content,:floor,:like_count,:post_time,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             content=excluded.content, like_count=excluded.like_count,
             post_time=excluded.post_time, fetched_at=excluded.fetched_at""",
        c,
    )


def upsert_team_map_winrate(conn, r: dict) -> None:
    conn.execute(
        """INSERT INTO team_map_winrate
             (team,map_name,opponent,wins,losses,rounds_won,rounds_lost,n_maps,win_rate,updated_at)
           VALUES
             (:team,:map_name,:opponent,:wins,:losses,:rounds_won,:rounds_lost,:n_maps,:win_rate,:updated_at)
           ON CONFLICT(team, map_name, opponent) DO UPDATE SET
             wins=excluded.wins, losses=excluded.losses,
             rounds_won=excluded.rounds_won, rounds_lost=excluded.rounds_lost,
             n_maps=excluded.n_maps, win_rate=excluded.win_rate, updated_at=excluded.updated_at""",
        {**r, "updated_at": _now()},
    )


def upsert_signal(conn, s: dict) -> None:
    s = {**s, "created_at": _now()}
    conn.execute(
        """INSERT INTO value_signals
             (date,player_name,v_star,p_market,delta,signal,position,rationale,created_at)
           VALUES
             (:date,:player_name,:v_star,:p_market,:delta,:signal,:position,:rationale,:created_at)
           ON CONFLICT(date, player_name) DO UPDATE SET
             v_star=excluded.v_star, p_market=excluded.p_market, delta=excluded.delta,
             signal=excluded.signal, position=excluded.position, rationale=excluded.rationale,
             created_at=excluded.created_at""",
        s,
    )


def get_player_stats_window(conn, player_name: str, limit: int = 50):
    return conn.execute(
        """SELECT * FROM player_stats WHERE player_name=? ORDER BY rowid DESC LIMIT ?""",
        (player_name, limit),
    ).fetchall()


def get_recent_sentiments(conn, player_name: str, days: int = 30):
    return conn.execute(
        """SELECT * FROM sentiments WHERE player_name=?
             AND created_at >= datetime('now', ?) ORDER BY created_at DESC""",
        (player_name, f"-{days} days"),
    ).fetchall()


def get_all_players(conn):
    return [r["player_name"] for r in conn.execute(
        "SELECT DISTINCT player_name FROM player_stats ORDER BY player_name"
    ).fetchall()]


def get_ratings(conn):
    return {r["player_name"]: dict(r) for r in conn.execute(
        "SELECT * FROM player_ratings"
    ).fetchall()}


def get_signals_by_date(conn, date: str):
    return conn.execute(
        "SELECT * FROM value_signals WHERE date=? ORDER BY ABS(delta) DESC", (date,)
    ).fetchall()


def get_player_profiles(conn, limit: int | None = None):
    sql = "SELECT * FROM player_profiles ORDER BY total_rounds DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def get_player_profile(conn, player_name: str):
    return conn.execute(
        "SELECT * FROM player_profiles WHERE player_name=?", (player_name,)
    ).fetchone()


def get_player_team(conn, player_name: str):
    row = conn.execute(
        "SELECT * FROM player_teams WHERE player_name=?", (player_name,)
    ).fetchone()
    return row["team"] if row else None


def get_team_map_winrate(conn, team: str | None = None):
    sql = "SELECT * FROM team_map_winrate ORDER BY team, map_name, opponent"
    args = ()
    if team:
        sql = "SELECT * FROM team_map_winrate WHERE team=? ORDER BY map_name, opponent"
        args = (team,)
    return conn.execute(sql, args).fetchall()


def get_map_pool(conn, team: str | None = None) -> dict[str, dict]:
    """战队地图池概览：每张图的胜率/场次（跨对手聚合）。"""
    sql = """SELECT map_name,
                    SUM(wins) AS wins, SUM(losses) AS losses,
                    SUM(rounds_won) AS rounds_won, SUM(rounds_lost) AS rounds_lost,
                    SUM(n_maps) AS n_maps
             FROM team_map_winrate
             {where}
             GROUP BY map_name ORDER BY n_maps DESC, wins DESC"""
    where, args = "", ()
    if team:
        where, args = "WHERE team=?", (team,)
    rows = conn.execute(sql.format(where=where), args).fetchall()
    out = {}
    for r in rows:
        n = r["n_maps"] or 0
        out[r["map_name"]] = {
            "wins": r["wins"], "losses": r["losses"],
            "win_rate": round((r["wins"] / n), 3) if n else 0.0,
            "rounds_won": r["rounds_won"], "rounds_lost": r["rounds_lost"],
            "n_maps": n,
        }
    return out


def count_rows(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def reset_all(conn) -> None:
    """清空全部业务表（研究管线重跑前调用，保证可重入）。"""
    for t in ("value_signals", "player_ratings", "sentiments", "posts",
              "player_stats", "maps", "matches",
              "player_profiles", "player_teams", "team_map_winrate",
              "hupu_match_ratings", "hupu_comments"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()

