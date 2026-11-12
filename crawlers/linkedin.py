"""LinkedIn public job-search listing crawler.

Use a persistent Chrome profile and complete login manually if LinkedIn asks.
Respect LinkedIn terms and stop if access is restricted or a CAPTCHA appears.
"""
import argparse
from pathlib import Path
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from crawlers.base import make_record, write_jsonl, export_csv, interactive_scrape, polite_delay
from crawlers.browser import persistent_chrome_context

PROFILE_DIR = "data/linkedin-profile"
BASE_URL = "https://www.linkedin.com"


def build_search_url(keyword: str, location: str) -> str:
    params = {"keywords": keyword, "location": location}
    return f"{BASE_URL}/jobs/search/?{urlencode(params)}"


def parse_jobs(soup: BeautifulSoup) -> list[dict]:
    rows, seen = [], set()
    cards = soup.select(
        "div.job-search-card, div.job-card-container, li.jobs-search-results__list-item"
    )
    for card in cards:
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link or not link.get("href"):
            continue
        url = urljoin(BASE_URL, link["href"].split("?")[0])
        if url in seen:
            continue
        seen.add(url)
        title = card.select_one("h3, span.sr-only") or link
        company = card.select_one("[class*='company-name'], [class*='companyName']")
        location = card.select_one("[class*='metadata-item'], [class*='location']")
        salary = card.select_one("[class*='salary']")
        rows.append(make_record(
            "linkedin", url,
            title=title.get_text(" ", strip=True),
            company=company.get_text(" ", strip=True) if company else None,
            location=location.get_text(" ", strip=True) if location else None,
            salary=salary.get_text(" ", strip=True) if salary else None,
            raw_fields={"listing_card_text": card.get_text(" ", strip=True)},
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Crawl LinkedIn job listings")
    parser.add_argument("--keyword", default="Data Engineer OR Data Analyst OR Data Scientist")
    parser.add_argument("--location", default="Vietnam")
    parser.add_argument("--scrolls", type=int, default=30)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out", default="data/raw/linkedin.jsonl")
    parser.add_argument("--csv", default="data/raw/linkedin.csv")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # mỗi lần chạy tạo một bộ dữ liệu mới
    with persistent_chrome_context(PROFILE_DIR, args.headless) as context:
        page = context.new_page()
        page.goto(build_search_url(args.keyword, args.location),
                  wait_until="domcontentloaded", timeout=60000)
        print("Nếu được yêu cầu, hãy đăng nhập thủ công. Không vượt CAPTCHA/cơ chế hạn chế.")
        for index in range(args.scrolls):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1800)
            # Scroll the results pane where available; page scroll remains fallback.
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            print(f"Đã cuộn {index + 1}/{args.scrolls}")
            polite_delay(1.5, 2.5)
        rows = parse_jobs(BeautifulSoup(page.content(), "lxml"))
        write_jsonl(output, rows, append=False)
    count = export_csv(output, args.csv)
    print(f"Hoàn tất: {count} records | JSONL={output} | CSV={args.csv}")


if __name__ == "__main__":
    main()
