
"""TopDev crawler with persistent login, pagination and deduplication."""

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


BASE_URL = "https://topdev.vn"
LIST_URL = f"{BASE_URL}/jobs/search"

# Profile riêng để lưu phiên đăng nhập TopDev
PROFILE_DIR = "data/browser_profiles/topdev"


def parse_cards(soup: BeautifulSoup) -> list[dict]:
    """Extract job information from listing cards."""

    rows = []
    seen = set()

    for link in soup.select("a[href*='/detail-jobs/']"):

        href = link.get("href")

        if not href:
            continue

        url = urljoin(BASE_URL, href.split("?")[0])

        if url in seen:
            continue

        seen.add(url)

        # Tìm phần tử cha có khả năng là job card
        card = link

        for _ in range(8):
            if not card.parent:
                break

            card = card.parent

            if "rounded-[16px]" in " ".join(card.get("class", [])):
                break

        company = card.select_one("span.line-clamp-1")

        grid = card.select_one("div.mt-2.grid")

        grid_values = (
            [
                span.get_text(" ", strip=True)
                for span in grid.select("span.line-clamp-1")
            ]
            if grid else []
        )

        # Tìm thông tin lương trong nội dung thẻ
        salary = card.find(
            "span",
            string=lambda value: (
                value and "salary" in value.lower()
            ),
        )

        skills = [
            a.get_text(" ", strip=True)
            for a in card.select("a.line-clamp-1.h-6")
        ]

        posted = card.select_one("span.text-xs.text-text-500")

        rows.append(
            make_record(
                "topdev",
                url,
                title=link.get_text(" ", strip=True),
                company=(
                    company.get_text(" ", strip=True)
                    if company else None
                ),
                location=(
                    grid_values[0]
                    if grid_values else None
                ),
                experience_level=(
                    ", ".join(grid_values[1:])
                    if len(grid_values) > 1 else None
                ),
                salary=(
                    salary.get_text(" ", strip=True)
                    if salary else None
                ),
                posted_at=(
                    posted.get_text(" ", strip=True)
                    if posted else None
                ),
                skills=skills,
                raw_fields={
                    "listing_card_text": card.get_text(
                        " ",
                        strip=True,
                    )
                },
            )
        )

    return rows


def main():

    parser = argparse.ArgumentParser(
        description="Crawl TopDev jobs with login session"
    )

    parser.add_argument("--pages", type=int, default=100)
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
        default="data/raw/topdev.jsonl",
    )

    parser.add_argument(
        "--csv",
        default="data/raw/topdev.csv",
    )

    args = parser.parse_args()

    # Cần Chrome hiển thị để đăng nhập thủ công
    if args.headless:
        parser.error(
            "TopDev login mode requires a visible browser. "
            "Please remove --headless."
        )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    csv_output = Path(args.csv)
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    # Mỗi lần chạy tạo một bộ dữ liệu mới
    if output.exists():
        output.unlink()

    rows = []
    seen = set()

    # Sử dụng Chrome profile riêng của TopDev
    with persistent_chrome_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
    ) as context:

        page = context.new_page()

        # Mở trang TopDev
        page.goto(
            BASE_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print("\nĐã mở TopDev trên Chrome.")
        print("Nếu chưa đăng nhập, hãy đăng nhập tài khoản của bạn.")

        input(
            "\nSau khi đăng nhập và kiểm tra quyền xem thông tin lương, "
            "hãy nhấn Enter trong Terminal để bắt đầu crawl..."
        )

        # Bắt đầu thu thập dữ liệu
        for number in range(1, args.pages + 1):

            url = (
                LIST_URL
                if number == 1
                else f"{LIST_URL}?page={number}"
            )

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                page.wait_for_timeout(2500)

                soup = BeautifulSoup(
                    page.content(),
                    "lxml",
                )

                batch = parse_cards(soup)

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
                print(
                    f"[INFO] Không có tin mới ở trang {number}."
                )
                break

            for record in batch:
                seen.add(record["job_url"])

            # Giới hạn tổng số tin
            if args.limit:
                remaining = max(0, args.limit - len(rows))
                batch = batch[:remaining]

            rows.extend(batch)

            # Lưu dữ liệu sau mỗi trang
            write_jsonl(output, batch)

            print(
                f"Page {number}: +{len(batch)}, "
                f"tổng {len(rows)}"
            )

            if args.limit and len(rows) >= args.limit:
                break

            polite_delay()

        # Thu thập thông tin chi tiết nếu được yêu cầu
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

    # Xuất CSV
    count = export_csv(output, csv_output)

    print("\n========== KẾT QUẢ ==========")
    print(f"Tổng số tin: {count}")
    print(f"JSONL: {output}")
    print(f"CSV: {csv_output}")


if __name__ == "__main__":
    main()
