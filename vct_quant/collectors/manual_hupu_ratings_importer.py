"""Manual Hupu post-match rating importer.

Use this instead of logging in with a personal Hupu account for automated
scraping. After a match, fill vct_quant/data/raw/hupu_ratings.csv with:

match_id,player_name,team,rating_avg,rating_count,rating_dist
m0,ZmjjKK,EDG,8.7,2351,

The importer writes rows into hupu_match_ratings through repo.upsert_hupu_rating.
It creates an empty template when the CSV is missing so the workflow is obvious
and safe to repeat.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .. import config
from ..storage import db as dbmod
from ..storage import repo

FIELDS = ["match_id", "player_name", "team", "rating_avg", "rating_count", "rating_dist"]


class ManualHupuRatingsImporter:
    """Import manually entered Hupu player ratings from CSV."""

    def __init__(self, csv_path: str | Path | None = None):
        self.csv_path = Path(csv_path or config.HUPU_RATINGS_CSV)

    def collect(self, conn, **kwargs) -> int:
        """Import CSV rows and return the number of written ratings."""
        path = Path(kwargs.get("hupu_ratings_csv") or self.csv_path)
        if not path.exists():
            self._write_template(path)
            print(f"[hupu-manual] template created: {path}")
            return 0

        count = 0
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = [field for field in FIELDS[:5] if field not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"missing CSV columns: {', '.join(missing)}")
            for row in reader:
                rating = self._normalize_row(row)
                if not rating:
                    continue
                repo.upsert_hupu_rating(conn, rating)
                count += 1
        conn.commit()
        print(f"[hupu-manual] imported {count} ratings from {path}")
        return count

    @staticmethod
    def _normalize_row(row: dict) -> dict | None:
        match_id = (row.get("match_id") or "").strip()
        player_name = (row.get("player_name") or "").strip()
        if not match_id or not player_name:
            return None
        rating_avg = (row.get("rating_avg") or "").strip()
        rating_count = (row.get("rating_count") or "").strip()
        if not rating_avg or not rating_count:
            return None
        return {
            "id": f"{match_id}|{player_name}",
            "match_id": match_id,
            "player_name": player_name,
            "team": (row.get("team") or "").strip() or None,
            "rating_avg": float(rating_avg),
            "rating_count": int(float(rating_count)),
            "rating_dist": (row.get("rating_dist") or "").strip() or None,
        }

    @staticmethod
    def _write_template(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(FIELDS)


if __name__ == "__main__":
    conn = dbmod.connect()
    try:
        dbmod.init_db(conn)
        n = ManualHupuRatingsImporter().collect(conn)
        print(f"[hupu-manual] done: {n}")
    finally:
        conn.close()
