from __future__ import annotations

import csv
import json
import logging
import os
import random
import re
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Iterable, Mapping
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Page, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schema.json"


@dataclass(frozen=True)
class SearchTask:
    url: str
    keyword: str | None = None


@dataclass(frozen=True)
class CrawlResult:
    source: str
    output_path: Path
    saved: int
    skipped: int


class BaseCrawler(ABC):
    SOURCE: ClassVar[str] = ""

    def __init__(
        self,
        *,
        headless: bool = True,
        min_delay: float = 2.0,
        max_delay: float = 4.0,
        timeout_ms: int = 30_000,
        user_agent: str = "DataMiningEngineerAcademicCrawler/1.0",
    ) -> None:
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("Cần 0 <= min_delay <= max_delay")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms phải lớn hơn 0")

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.columns: tuple[str, ...] = tuple(schema["required"])
        self.properties: dict = schema["properties"]
        sources = self.properties["Nguon"]["enum"]
        if self.SOURCE not in sources:
            raise ValueError(f"SOURCE phải là một trong {sources}")
        if set(self.columns) != set(self.properties):
            raise ValueError("required và properties trong schema.json không khớp")

        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent
        self.logger = logging.getLogger(f"crawler.{self.SOURCE}")
        self._last_navigation: float | None = None

    @abstractmethod
    def iter_search_tasks(self) -> Iterable[SearchTask]:
        """Yield SearchTask cho từng trang/từ khóa; xử lý phân trang tại đây."""

    @abstractmethod
    def extract_job_urls(self, page: Page, task: SearchTask) -> Iterable[str]:
        """Trả URL tin từ trang kết quả; có thể cuộn trang trước khi trích xuất."""

    @abstractmethod
    def parse_job(self, page: Page, task: SearchTask) -> Mapping[str, str | None]:
        """Trả các cột gốc theo schema.json, ít nhất phải có Tieu_De."""

    def visit(self, page: Page, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"URL không hợp lệ: {url!r}")
        if self._last_navigation is not None:
            delay = random.uniform(self.min_delay, self.max_delay)
            remaining = delay - (time.monotonic() - self._last_navigation)
            if remaining > 0:
                time.sleep(remaining)
        self._last_navigation = time.monotonic()
        response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if response is not None and response.status >= 400:
            raise RuntimeError(f"HTTP {response.status} khi tải {url}")

    def make_record(
        self, raw_fields: Mapping[str, str | None], task: SearchTask, job_url: str
    ) -> dict[str, str | None]:
        reserved = {"Nguon", "URL_Goc", "URL_Tim_Kiem", "Tu_Khoa_Tim_Kiem", "Timestamp"}
        unknown = set(raw_fields) - set(self.columns)
        forbidden = set(raw_fields) & reserved
        if unknown or forbidden:
            raise ValueError(f"Cột lạ: {sorted(unknown)}; cột do lớp nền quản lý: {sorted(forbidden)}")

        record: dict[str, str | None] = {column: None for column in self.columns}
        record.update(raw_fields)
        record.update(
            Nguon=self.SOURCE,
            URL_Goc=job_url,
            URL_Tim_Kiem=task.url,
            Tu_Khoa_Tim_Kiem=task.keyword,
            Timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        self.validate_record(record)
        return record

    def validate_record(self, record: Mapping[str, str | None]) -> None:
        if set(record) != set(self.columns):
            raise ValueError("Bản ghi thiếu hoặc thừa cột so với schema.json")
        for name, rule in self.properties.items():
            value = record[name]
            accepted_types = rule["type"]
            if isinstance(accepted_types, str):
                accepted_types = [accepted_types]
            if value is None:
                if "null" not in accepted_types:
                    raise ValueError(f"{name} không được để trống")
                continue
            if "string" not in accepted_types or not isinstance(value, str):
                raise ValueError(f"{name} phải là chuỗi hoặc null")
            if "enum" in rule and value not in rule["enum"]:
                raise ValueError(f"{name} không thuộc tập giá trị cho phép")
            if "pattern" in rule and not re.search(rule["pattern"], value):
                raise ValueError(f"{name} không đúng mẫu yêu cầu")
            if rule.get("format") == "uri":
                parsed = urlsplit(value)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise ValueError(f"{name} phải là URL HTTP(S)")
            if rule.get("format") == "date-time":
                try:
                    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError(f"{name} phải là thời điểm ISO 8601") from exc
                if timestamp.utcoffset() is None:
                    raise ValueError(f"{name} phải có múi giờ")

    def crawl(self, *, max_jobs: int | None = None, output_path: Path | None = None) -> CrawlResult:
        """Chạy crawler và xuất CSV theo thứ tự cột trong schema.json."""
        if max_jobs is not None and max_jobs <= 0:
            raise ValueError("max_jobs phải lớn hơn 0")
        destination = Path(output_path) if output_path else PROJECT_ROOT / "data" / "raw" / f"raw_{self.SOURCE}.csv"
        seen_urls: set[str] = set()
        rows: list[dict[str, str | None]] = []
        skipped = 0
        self._last_navigation = None

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context(user_agent=self.user_agent, locale="vi-VN")
            listing_page = context.new_page()
            detail_page = context.new_page()
            try:
                for task in self.iter_search_tasks():
                    if not isinstance(task, SearchTask):
                        raise TypeError("iter_search_tasks phải trả SearchTask")
                    self.visit(listing_page, task.url)
                    for href in self.extract_job_urls(listing_page, task):
                        job_url = urljoin(listing_page.url, href)
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)
                        try:
                            self.visit(detail_page, job_url)
                            fields = self.parse_job(detail_page, task)
                            record = self.make_record(fields, task, detail_page.url)
                        except Exception:
                            skipped += 1
                            self.logger.exception("Bỏ qua tin lỗi: %s", job_url)
                            continue
                        rows.append(record)
                        if max_jobs is not None and len(rows) >= max_jobs:
                            break
                    if max_jobs is not None and len(rows) >= max_jobs:
                        break
            finally:
                context.close()
                browser.close()

        if not rows:
            raise RuntimeError(f"Không có tin hợp lệ từ {self.SOURCE}; không ghi đè CSV cũ")
        self._write_csv(destination, rows)
        self.logger.info("Đã lưu %d tin, bỏ qua %d tin: %s", len(rows), skipped, destination)
        return CrawlResult(self.SOURCE, destination, len(rows), skipped)

    def _write_csv(self, destination: Path, rows: list[dict[str, str | None]]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=self.columns)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temp_name, destination)
        finally:
            if temp_name is not None and os.path.exists(temp_name):
                os.unlink(temp_name)
