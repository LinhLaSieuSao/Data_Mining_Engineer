"""Tiện ích HTTP tùy chọn cho crawler nguồn dùng requests."""

import random
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "DataMiningEngineerAcademicCrawler/1.0"
_ROBOTS = {}


def allowed(url: str) -> bool:
    """Chỉ truy cập URL được robots.txt cho phép."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _ROBOTS:
        parser = RobotFileParser(f"{origin}/robots.txt")
        try:
            parser.read()
        except Exception:
            return False
        _ROBOTS[origin] = parser
    return _ROBOTS[origin].can_fetch(USER_AGENT, url)


def polite_get(session, url: str, min_delay: float, max_delay: float, retries: int = 3):
    """Chờ ngẫu nhiên; thử lại 429/5xx; trả None khi robots không cho phép."""
    if not allowed(url):
        return None
    response = None
    for attempt in range(max(1, retries)):
        time.sleep(random.uniform(min_delay, max_delay))
        response = session.get(url, headers={"User-Agent": USER_AGENT})
        if response.status_code != 429 and response.status_code < 500:
            break
        if attempt + 1 < retries:
            time.sleep(2 ** attempt)
    return response
