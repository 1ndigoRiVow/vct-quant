"""vct_quant.collectors.scheduler — 增量调度：定时跑采集器，去重落库。"""
from __future__ import annotations

from datetime import datetime


class Scheduler:
    """简单的顺序调度器：按注册顺序执行采集器并记录运行状态。"""

    def __init__(self, conn, collectors: list | None = None):
        self.conn = conn
        self.collectors = collectors or []
        self.last_run: dict[str, str] = {}

    def add(self, collector) -> "Scheduler":
        self.collectors.append(collector)
        return self

    def run(self, **kwargs) -> dict:
        summary = {"run_at": datetime.now().isoformat(timespec="seconds"), "results": {}}
        for c in self.collectors:
            name = c.__class__.__name__
            try:
                n = c.collect(self.conn, **kwargs)
                summary["results"][name] = {"ok": True, "count": n}
                self.last_run[name] = summary["run_at"]
            except Exception as e:  # noqa: BLE001
                summary["results"][name] = {"ok": False, "error": str(e)}
        return summary
