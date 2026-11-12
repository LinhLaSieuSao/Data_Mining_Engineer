"""Shared utilities: timestamps, normalization, deduplication and JSONL/CSV output."""
from __future__ import annotations

import csv
import json
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit


from bs4 import BeautifulSoup


def vietnam_timestamp():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    return text or None


def clean_html(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    ) or None


def make_record(site: str, job_url: str | None, **fields) -> dict:
    """Build a consistent raw record while retaining original source values."""
    return {
        "site": site,
        "job_url": normalize_url(job_url),
        "title": clean_text(fields.get("title")),
        "company": clean_text(fields.get("company")),
        "location": clean_text(fields.get("location")),
        "salary": clean_text(fields.get("salary")),  # original, not normalized
        "experience_level": clean_text(fields.get("experience_level")),
        "description": fields.get("description"),
        "requirements": fields.get("requirements"),
        "benefits": fields.get("benefits"),
        "skills": fields.get("skills") or [],
        "posted_at": clean_text(fields.get("posted_at")),
        "work_model": clean_text(fields.get("work_model")),
        "job_type": clean_text(fields.get("job_type")),
        "timestamp": vietnam_timestamp(),
        "raw_fields": fields.get("raw_fields") or {},
    }


def write_jsonl(path: str | Path, rows: Iterable[dict], *, append: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"[WARN] Bỏ qua JSON lỗi ở dòng {line_no}: {exc}")
    return rows


def export_csv(jsonl_path: str | Path, csv_path: str | Path) -> int:
    """Export JSONL records to a flat CSV; list/dict values become JSON strings."""
    rows = read_jsonl(jsonl_path)
    columns = [
        "site", "job_url", "title", "company", "location", "salary",
        "experience_level", "description", "requirements", "benefits",
        "skills", "posted_at", "work_model", "job_type", "timestamp", "raw_fields",
    ]
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False)
                if isinstance(row.get(key), (list, dict)) else row.get(key)
                for key in columns
            })
    return len(rows)


def polite_delay(min_seconds: float = 2.0, max_seconds: float = 4.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def extract_detail_text(page) -> dict:
    """Best-effort generic detail-page extraction; missing fields remain None."""
    page.wait_for_timeout(1200)
    soup = BeautifulSoup(page.content(), "lxml")
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        node.decompose()

    selectors = [
        "[class*='job-description']", "[class*='jobDescription']",
        "[class*='job-detail']", "[class*='jobDetail']",
        "[class*='description']", "article", "main",
    ]
    container = None
    for selector in selectors:
        candidate = soup.select_one(selector)
        if candidate and len(candidate.get_text(" ", strip=True)) > 150:
            container = candidate
            break
    if container is None:
        container = soup.body or soup

    description = clean_text(container.get_text("\n", strip=True))
    return {
        "description": description,
        "requirements": None,
        "benefits": None,
    }


def enrich_details(context_or_page, rows: list[dict], *, limit: int = 0,
                   min_delay: float = 2.0, max_delay: float = 4.0) -> list[dict]:
    """Visit source URLs and attempt to collect full job text, preserving failures."""
    targets = rows[:limit] if limit else rows
    for index, row in enumerate(targets, start=1):
        if row.get("description") and len(row["description"]) > 150:
            continue
        url = row.get("job_url")
        if not url:
            continue
        page = context_or_page.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            details = extract_detail_text(page)
            # Avoid replacing a useful listing description with a shorter page shell.
            if details.get("description") and len(details["description"]) > 150:
                row["description"] = details["description"]
            row["detail_fetch_timestamp"] = vietnam_timestamp()
            row["detail_fetch_status"] = "success" if row.get("description") else "no_text_found"
        except Exception as exc:
            row["detail_fetch_timestamp"] = vietnam_timestamp()
            row["detail_fetch_status"] = f"error: {type(exc).__name__}"
            print(f"[WARN] Detail {index}/{len(targets)} thất bại: {url}")
        finally:
            page.close()
        polite_delay(min_delay, max_delay)
    return rows


def interactive_scrape(page, parse_fn, out_path, *, interval=3.0, label="") -> dict:
    """Monitor a manually navigated page; Ctrl+C ends collection."""
    out = Path(out_path)
    collected = {r["job_url"]: r for r in read_jsonl(out) if r.get("job_url")}
    print(f"[{label}] Đang theo dõi trang; điều hướng/scroll thủ công, Ctrl+C để dừng.")
    try:
        while True:
            try:
                soup = BeautifulSoup(page.content(), "lxml")
                for row in parse_fn(soup):
                    url = normalize_url(row.get("job_url"))
                    if url:
                        collected.setdefault(url, row)
                write_jsonl(out, collected.values(), append=False)
                print(f"[{label}] {len(collected)} tin duy nhất", flush=True)
            except Exception as exc:
                print(f"[{label}] Lỗi đọc trang: {type(exc).__name__}", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    print(f"[{label}] Hoàn tất: {len(collected)} tin -> {out}")
    return collected
