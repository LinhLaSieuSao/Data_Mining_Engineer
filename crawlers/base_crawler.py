"""Khung chung để các crawler nguồn xuất dữ liệu tuyển dụng thô."""

from __future__ import annotations

import csv
import json
import random
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar, Iterable, Mapping
from urllib.parse import urlsplit
from .schema_utils import coerce, load_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VN_TIMEZONE = timezone(timedelta(hours=7))


def _print_status(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "backslashreplace").decode("ascii"))


@dataclass(frozen=True)
class CrawlResult:
    source: str
    output_path: Path
    saved: int
    skipped: int
    missing: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    status: str = "ok"
    duplicates: int = 0


class BaseCrawler(ABC):
    """Crawler nguồn chỉ cần đặt SOURCE và triển khai iter_jobs()."""

    SOURCE: ClassVar[str] = ""

    def __init__(self, *, min_delay: float = 2.0, max_delay: float = 4.0) -> None:
        schema = load_schema()
        self.columns = tuple(schema["required"])
        self.tracked = tuple(schema["x-tracked-fields"])
        if not {"Nguon", "Timestamp", "URL_Goc"} <= set(self.columns):
            raise ValueError("Schema thiếu cột Nguon, Timestamp hoặc URL_Goc")
        if not set(self.tracked) <= set(self.columns):
            raise ValueError("Schema có cột theo dõi không thuộc required")
        if self.SOURCE not in schema["properties"]["Nguon"]["enum"]:
            raise ValueError(f"Nguồn không có trong schema.json: {self.SOURCE}")
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("Khoảng chờ không hợp lệ")
        self.min_delay, self.max_delay = min_delay, max_delay
        self._warned_unknown = False

    @abstractmethod
    def iter_jobs(self, *, max_pages: int | None = None) -> Iterable[Mapping[str, object]]:
        """Tự phân trang/đọc HTML hoặc API; yield tin dùng tên cột trong schema.json.

        Giá trị giữ nguyên như nguồn. Có thể để thiếu cột; base sẽ điền ô trống.
        Mỗi tin nên có URL_Goc, URL_Tim_Kiem và Tu_Khoa_Tim_Kiem nếu lấy được.
        """

    def pause(self) -> None:
        """Crawler nguồn gọi giữa các lần truy cập, không gọi cho từng hàng CSV."""
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def prepare_record(self, job: Mapping[str, object]) -> dict[str, object | None]:
        """Ánh xạ cấu trúc, không chuẩn hóa giá trị từ website."""
        unknown = set(job) - set(self.columns)
        if unknown and not self._warned_unknown:
            _print_status(f"[{self.SOURCE}] Khóa ngoài schema bị bỏ qua: {sorted(unknown)}")
            self._warned_unknown = True
        record = {name: coerce(job.get(name)) for name in self.columns}
        record["Nguon"] = self.SOURCE
        record["Timestamp"] = datetime.now(VN_TIMEZONE).isoformat(timespec="seconds")
        return record

    @staticmethod
    def is_readable_record(record: Mapping[str, object | None]) -> bool:
        """Chỉ bỏ hàng không thể mở URL tin để đối chiếu với website."""
        url = record.get("URL_Goc")
        if not isinstance(url, str):
            return False
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        return parts.scheme in ("http", "https") and bool(parts.netloc)

    def crawl(
        self, *, max_jobs: int | None = None, max_pages: int | None = None,
        output_path: Path | None = None,
    ) -> CrawlResult:
        """Thu dữ liệu raw; lỗi một hàng không làm mất các hàng đã đọc được."""
        destination = Path(output_path) if output_path else (
            PROJECT_ROOT / "data" / "raw" / f"raw_{self.SOURCE}.csv"
        )
        if (max_jobs is not None and max_jobs <= 0) or (max_pages is not None and max_pages <= 0):
            _print_status("Giới hạn số trang/tin phải lớn hơn 0")
            return CrawlResult(self.SOURCE, destination, 0, 0, error="Giới hạn không hợp lệ", status="failed")

        rows: list[dict[str, object | None]] = []
        missing = {name: 0 for name in self.tracked}
        skipped = duplicates = 0
        seen = set()
        error = None
        status = "ok"
        iterator = None
        checkpoint = Path(f"{destination}.partial.jsonl")
        stamp = datetime.now(VN_TIMEZONE).strftime("%Y%m%d_%H%M%S")
        try:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with checkpoint.open("x", encoding="utf-8") as progress:
                iterator = iter(self.iter_jobs(max_pages=max_pages))
                for job in iterator:
                    if not isinstance(job, Mapping):
                        skipped += 1
                        continue
                    record = self.prepare_record(job)
                    if not self.is_readable_record(record):
                        skipped += 1
                        continue
                    url = urlsplit(record["URL_Goc"])
                    key = ((self.SOURCE, record["Ma_Tin_Nguon"])
                           if record["Ma_Tin_Nguon"] else (url.netloc.lower(), url.path.rstrip("/")))
                    if key in seen:
                        duplicates += 1
                        continue
                    progress.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    progress.flush()
                    seen.add(key)
                    rows.append(record)
                    for name in missing:
                        if record[name] is None:
                            missing[name] += 1
                    if len(rows) % 25 == 0:
                        _print_status(f"[{self.SOURCE}] Đã đọc {len(rows)} tin")
                    if max_jobs is not None and len(rows) >= max_jobs:
                        break
        except KeyboardInterrupt:
            error = "Đã dừng bằng bàn phím"
            status = "partial"
        except Exception as exc:
            error = f"Dừng khi đọc nguồn: {type(exc).__name__}: {exc}"
            status = "partial" if rows else "failed"
        finally:
            if iterator is not None and callable(close := getattr(iterator, "close", None)):
                try:
                    close()
                except Exception:
                    pass

        partial = destination.with_name(f"{destination.stem}_partial_{stamp}{destination.suffix}")
        output = destination if status == "ok" else partial
        written = False
        if rows:
            try:
                self.write_csv(output, rows)
                written = True
            except Exception as exc:
                error = f"Không thay được CSV: {type(exc).__name__}: {exc}"
                status = "partial"
                output = partial
                try:
                    with output.open("x", encoding="utf-8-sig", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=self.columns)
                        writer.writeheader()
                        writer.writerows(rows)
                    written = True
                except Exception as backup_exc:
                    status = "failed"
                    error += f"; file dự phòng lỗi: {backup_exc}"
        elif error is None:
            error, status = "Không có tin đọc được; giữ CSV cũ", "failed"

        if status == "ok" and written:
            checkpoint.unlink()
        saved = len(rows) if written else 0
        result = CrawlResult(self.SOURCE, output, saved, skipped, missing, error, status, duplicates)
        message = (f"[{self.SOURCE}] {status}: lưu={saved}, bỏ qua={skipped}, trùng={duplicates}; thiếu: "
                   + ", ".join(f"{name}={count}" for name, count in missing.items())
                   + f"; file: {output}")
        _print_status(message)
        if error:
            _print_status(f"[{self.SOURCE}] {error}")
        if checkpoint.exists():
            _print_status(f"[{self.SOURCE}] Checkpoint: {checkpoint}")
        return result

    def write_csv(self, destination: Path, rows: list[dict[str, object | None]]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8-sig", newline="", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=self.columns)
                writer.writeheader()
                writer.writerows(rows)
            Path(temp_name).replace(destination)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink()
