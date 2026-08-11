"""HTTP 抓取辅助：带重试、限速、UA。礼貌爬取，避免给源站压力。"""
from __future__ import annotations

import time

from .. import config


def fetch_html(url: str, **kwargs) -> str:
    import requests  # 惰性导入，离线模式无需安装

    headers = kwargs.pop("headers", None) or {"User-Agent": config.USER_AGENT}
    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        try:
            time.sleep(config.REQUEST_DELAY)
            r = requests.get(
                url, headers=headers, timeout=config.REQUEST_TIMEOUT, **kwargs
            )
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(config.REQUEST_DELAY * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url} -> {last_err}")
