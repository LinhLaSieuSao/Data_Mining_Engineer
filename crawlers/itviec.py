
"""ITviec listing crawler with persistent login session."""

import argparse
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawlers.base import (
    make_record,
    write_jsonl,
    enrich_details,
    export_csv,
    polite_delay,
)

from crawlers.browser import persistent_chrome_context


BASE_URL = "https://itviec.com"
LIST_URL = f"{BASE_URL}/it-jobs"

# Profile riêng để lưu phiên đăng nhập ITviec
PROFILE_DIR = "data/browser_profiles/itviec"


def parse_card(card: BeautifulSoup) -> dict | None:
    """Extract job information from a job listing card."""

    link = card.select_one("h3 a, a[href*='/it-jobs/']")

    if not link or not link.get("href"):
        return None

    url = urljoin(BASE_URL, link["href"].split("?")[0])

    company = card.select_one("span.ims-2 a.text-rich-grey")
    salary = card.select_one("div.salary a")
    location = card.select_one(
        "div.text-rich-grey.text-truncate.text-nowrap"
    )
    exp = card.select_one("[class*='experience']")
    posted = card.select_one("span.small-text.text-dark-grey")

    skills = [
        a.get_text(" ", strip=True)
        for a in card.select(
            "a[data-responsive-tag-list-target='tag']"
        )
    ]

    return make_record(
        "itviec",
        url,
        title=link.get_text(" ", strip=True),
        company=company.get_text(" ", strip=True) if company else None,
        location=(
            location.get("title") or location.get_text(" ", strip=True)
            if location else None
        ),
        salary=salary.get_text(" ", strip=True) if salary else None,
        experience_level=exp.get_text(" ", strip=True) if exp else None,
        posted_at=(
            posted.get_text(" ", strip=True).removeprefix("Posted ")
            if posted else None
        ),
        skills=skills,
        raw_fields={
            "listing_card_text": card.get_text(" ", strip=True)
        },
    )


def fetch_page(page, page_num: int) -> list[dict]:
    """Fetch one ITviec listing page."""

    url = LIST_URL if page_num == 1 else f"{LIST_URL}?page={page_num}"

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_selector(
        "div.job-card",
        timeout=30000,
    )

    soup = BeautifulSoup(page.content(), "lxml")

    return [
        record
        for card in soup.select("div.job-card")
        if (record := parse_card(card))
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Crawl ITviec job listings"
    )

    parser.add_argument("--pages", type=int, default=40)
    parser.add_argument("--limit", type=int, default=0)

    parser.add_argument(
        "--details",
        action="store_true",
        help="Visit job URLs to extract JD text",
    )

    parser.add_argument("--detail-limit", type=int, default=0)
    parser.add_argument("--headless", action="store_true")

    parser.add_argument(
        "--out",
        default="data/raw/itviec.jsonl",
    )

    parser.add_argument(
        "--csv",
        default="data/raw/itviec.csv",
    )

    args = parser.parse_args()

    if args.headless:
        parser.error(
            "ITviec login mode requires a visible browser. "
            "Please remove --headless."
        )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    csv_output = Path(args.csv)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    # Mỗi lần chạy tạo một bộ dữ liệu mới
    if output.exists():
        output.unlink()

    seen = set()
    rows = []

    with persistent_chrome_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
    ) as context:

        page = context.new_page()

        # Mở ITviec
        page.goto(
            BASE_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print("\nĐã mở ITviec trên Chrome.")
        print("Nếu chưa đăng nhập, hãy đăng nhập tài khoản của bạn.")

        input(
            "\nSau khi đăng nhập và kiểm tra quyền xem dữ liệu, "
            "hãy nhấn Enter trong Terminal để bắt đầu crawl..."
        )

        # Thu thập dữ liệu từ các trang
        for number in range(1, args.pages + 1):

            try:
                batch = fetch_page(page, number)

            except Exception as exc:
                print(
                    f"[WARN] Trang {number}: "
                    f"{type(exc).__name__}: {exc}"
                )
                break

            # Loại bỏ tin tuyển dụng trùng URL
            batch = [
                record
                for record in batch
                if record["job_url"]
                and record["job_url"] not in seen
            ]

            if not batch:
                print(f"[INFO] Không có tin mới ở trang {number}.")
                break

            for record in batch:
                seen.add(record["job_url"])

            # Giới hạn số lượng tin
            if args.limit:
                remaining = max(0, args.limit - len(rows))
                batch = batch[:remaining]

            rows.extend(batch)

            write_jsonl(output, batch)

            print(
                f"Page {number}: +{len(batch)}, "
                f"tổng {len(rows)}"
            )

            if args.limit and len(rows) >= args.limit:
                break

            polite_delay()

        # Truy cập trang chi tiết nếu được yêu cầu
        if args.details and rows:
            print("\nĐang thu thập thông tin chi tiết...")

            enrich_details(
                context,
                rows,
                limit=args.detail_limit,
            )

            write_jsonl(
                output,
                rows,
                append=False,
            )

    # Xuất dữ liệu CSV
    count = export_csv(output, csv_output)

    print("\n========== KẾT QUẢ ==========")
    print(f"Tổng số tin: {count}")
    print(f"JSONL: {output}")
    print(f"CSV: {csv_output}")


if __name__ == "__main__":
    main()
