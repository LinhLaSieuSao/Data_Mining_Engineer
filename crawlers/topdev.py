"""TopDev crawler with pagination, deduplication and optional detail extraction."""
import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawlers.base import make_record, write_jsonl, enrich_details, export_csv, polite_delay
from crawlers.browser import browser

BASE_URL = "https://topdev.vn"
LIST_URL = f"{BASE_URL}/jobs/search"


def parse_cards(soup: BeautifulSoup) -> list[dict]:
    rows, seen = [], set()
    for link in soup.select("a[href*='/detail-jobs/']"):
        href = link.get("href")
        if not href:
            continue
        url = urljoin(BASE_URL, href.split("?")[0])
        if url in seen:
            continue
        seen.add(url)
        card = link
        for _ in range(8):
            if not card.parent:
                break
            card = card.parent
            if "rounded-[16px]" in " ".join(card.get("class", [])):
                break
        company = card.select_one("span.line-clamp-1")
        grid = card.select_one("div.mt-2.grid")
        grid_values = [s.get_text(" ", strip=True) for s in grid.select("span.line-clamp-1")] if grid else []
        salary = card.find("span", string=lambda value: value and "salary" in value.lower())
        skills = [a.get_text(" ", strip=True) for a in card.select("a.line-clamp-1.h-6")]
        posted = card.select_one("span.text-xs.text-text-500")
        rows.append(make_record(
            "topdev", url,
            title=link.get_text(" ", strip=True),
            company=company.get_text(" ", strip=True) if company else None,
            location=grid_values[0] if grid_values else None,
            experience_level=", ".join(grid_values[1:]) if len(grid_values) > 1 else None,
            salary=salary.get_text(" ", strip=True) if salary else None,
            posted_at=posted.get_text(" ", strip=True) if posted else None,
            skills=skills,
            raw_fields={"listing_card_text": card.get_text(" ", strip=True)},
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Crawl TopDev jobs")
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--detail-limit", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out", default="data/raw/topdev.jsonl")
    parser.add_argument("--csv", default="data/raw/topdev.csv")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # mỗi lần chạy tạo một bộ dữ liệu mới
    rows, seen = [], set()
    with browser(args.headless) as context:
        page = context.new_page()
        for number in range(1, args.pages + 1):
            url = LIST_URL if number == 1 else f"{LIST_URL}?page={number}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                batch = parse_cards(BeautifulSoup(page.content(), "lxml"))
            except Exception as exc:
                print(f"[WARN] Trang {number}: {type(exc).__name__}")
                break
            batch = [r for r in batch if r["job_url"] not in seen]
            if not batch:
                break
            for row in batch:
                seen.add(row["job_url"])
            if args.limit:
                batch = batch[:max(0, args.limit - len(rows))]
            rows.extend(batch)
            write_jsonl(output, batch)
            print(f"Page {number}: +{len(batch)}, tổng {len(rows)}")
            if args.limit and len(rows) >= args.limit:
                break
            polite_delay()
        if args.details:
            enrich_details(context, rows, limit=args.detail_limit)
            write_jsonl(output, rows, append=False)
    count = export_csv(output, args.csv)
    print(f"Hoàn tất: {count} records | JSONL={output} | CSV={args.csv}")


if __name__ == "__main__":
    main()
