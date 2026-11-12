"""ITviec listing crawler. Detail pages are optionally visited for JD text."""
import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawlers.base import make_record, write_jsonl, read_jsonl, enrich_details, export_csv, polite_delay
from crawlers.browser import browser

BASE_URL = "https://itviec.com"
LIST_URL = f"{BASE_URL}/it-jobs"


def parse_card(card: BeautifulSoup) -> dict | None:
    link = card.select_one("h3 a, a[href*='/it-jobs/']")
    if not link or not link.get("href"):
        return None
    url = urljoin(BASE_URL, link["href"].split("?")[0])
    company = card.select_one("span.ims-2 a.text-rich-grey")
    salary = card.select_one("div.salary a")
    location = card.select_one("div.text-rich-grey.text-truncate.text-nowrap")
    exp = card.select_one("[class*='experience']")
    posted = card.select_one("span.small-text.text-dark-grey")
    skills = [a.get_text(" ", strip=True) for a in card.select("a[data-responsive-tag-list-target='tag']")]
    return make_record(
        "itviec", url,
        title=link.get_text(" ", strip=True),
        company=company.get_text(" ", strip=True) if company else None,
        location=location.get("title") or location.get_text(" ", strip=True) if location else None,
        salary=salary.get_text(" ", strip=True) if salary else None,
        experience_level=exp.get_text(" ", strip=True) if exp else None,
        posted_at=posted.get_text(" ", strip=True).removeprefix("Posted ") if posted else None,
        skills=skills,
        raw_fields={"listing_card_text": card.get_text(" ", strip=True)},
    )


def fetch_page(page, page_num: int) -> list[dict]:
    url = LIST_URL if page_num == 1 else f"{LIST_URL}?page={page_num}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("div.job-card", timeout=30000)
    soup = BeautifulSoup(page.content(), "lxml")
    return [r for card in soup.select("div.job-card") if (r := parse_card(card))]


def main():
    parser = argparse.ArgumentParser(description="Crawl ITviec job listings")
    parser.add_argument("--pages", type=int, default=40)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--details", action="store_true", help="Visit job URLs to extract JD text")
    parser.add_argument("--detail-limit", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out", default="data/raw/itviec.jsonl")
    parser.add_argument("--csv", default="data/raw/itviec.csv")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # mỗi lần chạy tạo một bộ dữ liệu mới
    seen, rows = set(), []
    with browser(args.headless) as context:
        page = context.new_page()
        for number in range(1, args.pages + 1):
            try:
                batch = fetch_page(page, number)
            except Exception as exc:
                print(f"[WARN] Trang {number}: {type(exc).__name__}")
                break
            batch = [r for r in batch if r["job_url"] and r["job_url"] not in seen]
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
