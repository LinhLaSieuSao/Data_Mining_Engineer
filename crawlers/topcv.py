"""TopCV IT job crawler with automatic pagination and optional detail extraction."""
import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawlers.base import make_record, write_jsonl, enrich_details, export_csv, polite_delay
from crawlers.browser import browser

BASE_URL = "https://www.topcv.vn"
LIST_URL = f"{BASE_URL}/tim-viec-lam-cong-nghe-thong-tin-cr257"


def parse_cards(soup: BeautifulSoup) -> list[dict]:
    rows, seen = [], set()
    for card in soup.select("div.job-item-search-result"):
        link = card.select_one("h3.title a, a[href*='/viec-lam/']")
        if not link or not link.get("href"):
            continue
        url = urljoin(BASE_URL, link["href"].split("?")[0])
        if url in seen:
            continue
        seen.add(url)
        company = card.select_one("a.company")
        salary = card.select_one("label.salary")
        location = card.select_one("a.address, span.city-text")
        exp = card.select_one("label.exp")
        posted = card.select_one("label.label-update")
        rows.append(make_record(
            "topcv", url,
            title=link.get_text(" ", strip=True),
            company=company.get_text(" ", strip=True) if company else None,
            salary=salary.get_text(" ", strip=True) if salary else None,
            location=location.get_text(" ", strip=True) if location else None,
            experience_level=exp.get_text(" ", strip=True) if exp else None,
            posted_at=posted.get_text(" ", strip=True) if posted else None,
            raw_fields={"listing_card_text": card.get_text(" ", strip=True)},
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Crawl TopCV IT jobs")
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--detail-limit", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out", default="data/raw/topcv.jsonl")
    parser.add_argument("--csv", default="data/raw/topcv.csv")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # mỗi lần chạy tạo một bộ dữ liệu mới
    rows, seen = [], set()
    with browser(args.headless) as context:
        page = context.new_page()
        for number in range(args.start_page, args.start_page + args.pages):
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
                print(f"Dừng tại trang {number}: không có tin mới.")
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
