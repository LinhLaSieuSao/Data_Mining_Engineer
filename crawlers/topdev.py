"""Crawler TopDev tuần tự, đọc tin công khai và lưu CSV theo schema dự án."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from crawlers import (DUNG, doc_schema, kiem_thu_robot, duoc_phep, doc_csv, khoa_url, danh_dau_bat_dau, nghi_ngau_nhien, tai_thu_lai, xuat_csv)

TRANG_CHU = "https://topdev.vn"
TEN_BOT = "DataMining-Crawler/1.0"
THU_MUC = Path(__file__).resolve().parent.parent
KEYWORDS_MAC_DINH = THU_MUC / "keyword.json"
OUT_MAC_DINH = THU_MUC / "data" / "raw" / "raw_topdev.csv"
SO_LAN_CUON = 8
ANH_XA_COT = {
    "web": "Web", "id": "Ma_Tin_Nguon", "url": "URL_Goc",
    "search_url": "URL_Tim_Kiem", "search_keyword": "Tu_Khoa_Tim_Kiem",
    "timestamp": "Timestamp", "title": "Tieu_De", "company": "Ten_Cong_Ty",
    "location": "Dia_Diem", "salary": "Luong", "experience": "Kinh_Nghiem",
    "work_type": "Hinh_Thuc_Lam_Viec", "contract": "Loai_Hop_Dong",
    "posted": "Ngay_Dang", "description": "Mo_Ta_Cong_Viec", "skills": "Ky_Nang",
}


def tao_url_tim_kiem(keyword: str, page_num: int) -> str:
    """TopDev tìm kiếm tại /jobs/search; q là cụm từ khóa, page là số trang."""
    return f"{TRANG_CHU}/jobs/search?{urlencode({'q': keyword, 'page': page_num})}"


def doc_keywords(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    roles = data.get("Nhom_Nghanh", [])
    if not isinstance(roles, list):
        raise ValueError("keyword.json cần Nhom_Nghanh là danh sách")
    return list(dict.fromkeys(str(x).strip() for x in roles if str(x).strip()))


def kiem_tra_anh_xa(schema: dict[str, Any]) -> set[str]:
    required = {c for c in schema["required"] if "null" not in schema["properties"][c]["type"]}
    mapped = list(ANH_XA_COT.values())
    extra = sorted(set(mapped) - set(schema["required"]))
    missing = sorted(required - set(mapped))
    duplicates = len(mapped) != len(set(mapped))
    if extra or missing or duplicates:
        raise ValueError(f"ANH_XA_COT sai schema: cột thừa={extra}, cột bắt buộc chưa ánh xạ={missing}, mapping trùng={duplicates}")
    return required


def _text(node: Tag | None) -> str | None:
    if not node:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def parse_cards(html: str) -> list[dict[str, Any]]:
    """Bóc các card TopDev theo selector của crawler cũ, không phụ thuộc Playwright."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.rounded-\\[16px\\]")
    if not cards:
        cards = soup.select("div[class*='text-card-foreground']")
    if not cards:
        cards = soup.select("a[href*='/detail-jobs/']")
    rows, seen = [], set()
    for item in cards:
        link = item if item.name == "a" else item.select_one("a[href*='/detail-jobs/']")
        if not link or not link.get("href"):
            continue
        url = urljoin(TRANG_CHU, str(link["href"]).split("?", 1)[0])
        if (urlsplit(url).hostname or "").lower().removeprefix("www.") != "topdev.vn":
            continue
        key = khoa_url(url)
        if key in seen:
            continue
        seen.add(key)
        # Với selector link-only, card là node cha gần nhất có đủ thông tin hiển thị.
        card = item
        if item.name == "a":
            for _ in range(6):
                if not card.parent or card.parent.name in ("body", "html"):
                    break
                card = card.parent
                if len(card.get_text(" ", strip=True)) > len(item.get_text(" ", strip=True)) + 10:
                    break
        spans = [x.get_text(" ", strip=True) for x in card.select("span.line-clamp-1") if x.get_text(" ", strip=True)]
        company_node = card.select_one("span.line-clamp-1")
        grid = card.select_one("div.mt-2.grid")
        grid_values = [x.get_text(" ", strip=True) for x in grid.select("span.line-clamp-1")] if grid else []
        salary_node = card.select_one("span[class*='salary' i]")
        skills = [x.get_text(" ", strip=True) for x in card.select("a.line-clamp-1.h-6") if x.get_text(" ", strip=True)]
        posted_node = card.select_one("span.text-xs.text-text-500")
        rows.append({
            "url": url, "key": key, "title": _text(link),
            "company": _text(company_node), "location": grid_values[0] if grid_values else None,
            "experience": ", ".join(grid_values[1:]) if len(grid_values) > 1 else None,
            "salary": _text(salary_node), "posted": _text(posted_node),
            "skills": list(dict.fromkeys(skills)) or None,
            "listing_text": card.get_text("\n", strip=True) or None,
        })
    return rows


def parse_detail(html: str) -> dict[str, Any]:
    """Bóc các trường chi tiết từ HTML; selector chi tiết là điểm cần xác nhận."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.select_one("article")
    if not main:
        return {}
    title = main.select_one("h1")
    company = main.select_one("a[href*='/company/'], [class*='company']")
    description = (
        main.select_one("[class*='description']")
        or main.select_one("[class*='job-detail']")
        or main.select_one("[class*='detail-job']")
    )
    description_text = None
    if description:
        # Tách bản sao để tiêu đề tin không bị lấy kèm khi container bao quanh cả phần đầu trang.
        description_soup = BeautifulSoup(str(description), "lxml")
        for heading in description_soup.select("h1, h2, h3, h4, h5, h6"):
            if heading.name == "h1" or _text(heading) == _text(title):
                heading.decompose()
        description_text = description_soup.get_text("\n", strip=True) or None
    skill_nodes = main.select("a[class*='skill'], [class*='skill-tag']")
    salary = next((_text(node) for node in main.select("[class*='salary'], [class*='wage']") if _text(node)), None)
    return {
        "title": _text(title), "company": _text(company),
        "salary": salary,
        "description": description_text,
        "skills": list(dict.fromkeys(x.get_text(" ", strip=True) for x in skill_nodes if x.get_text(" ", strip=True))) or None,
    }


def _mo_trang(page: Any, url: str, loai: str, khoang_nghi: tuple[float, float]) -> tuple[str | None, str]:
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else 0
        if response is None:
            return None, "loi_tam_thoi"
        if status in (404, 410):
            return None, "khong_ton_tai"
        if status == 403:
            return None, "bi_chan" if loai == "danh_sach" else "bi_cam"
        if status == 429:
            return None, "bi_chan"
        if status >= 500 or status != 200:
            return None, "loi_tam_thoi"
        final_url = urlsplit(page.url)
        if (final_url.scheme != "https" or
                (final_url.hostname or "").lower().removeprefix("www.") !=
                (urlsplit(TRANG_CHU).hostname or "").lower().removeprefix("www.")):
            return None, "bi_cam"
        selector = ("body" if loai == "trang_chu" else
                    "a[href*='/detail-jobs/']" if loai == "danh_sach" else "main h1, article h1")
        try:
            page.wait_for_selector(selector, timeout=12000)
        except PlaywrightTimeoutError:
            pass
        html = page.content()
        title = (page.title() or "").casefold()
        lower = html.casefold()
        has_content = bool(page.locator(selector).count())
        if "verify you are human" in lower or "cf-chl-" in lower or ("access denied" in title and not has_content):
            return None, "bi_chan"
        if loai == "danh_sach":
            old_count, stagnant = page.locator(selector).count(), 0
            for _ in range(SO_LAN_CUON):
                if stagnant >= 2:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                nghi_ngau_nhien(khoang_nghi)
                new_count = page.locator(selector).count()
                stagnant = stagnant + 1 if new_count <= old_count else 0
                old_count = new_count
            html = page.content()
        return html, "ok"
    except (PlaywrightError, OSError):
        return None, "loi_tam_thoi"


def _row(schema: dict[str, Any], card: dict[str, Any], detail: dict[str, Any],
         search_url: str, keyword: str, timestamp: str) -> dict[str, Any]:
    match = re.search(r"(\d+)(?:\.html)?$", card["url"].rstrip("/"))
    values = {
        "web": "topdev", "id": match.group(1) if match is not None else None,
        "url": card["url"], "search_url": search_url, "search_keyword": keyword,
        "timestamp": timestamp, "title": detail.get("title") or card.get("title"),
        "company": detail.get("company") or card.get("company"), "location": card.get("location"),
        "salary": detail.get("salary") or card.get("salary"), "experience": card.get("experience"),
        "work_type": None, "contract": None, "posted": card.get("posted"),
        "description": detail.get("description"),
        "skills": detail.get("skills") or card.get("skills"),
    }
    row = {column: None for column in schema["required"]}
    for key, column in ANH_XA_COT.items():
        row[column] = values.get(key)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawler TopDev theo keyword.json")
    parser.add_argument("--out", type=Path, default=OUT_MAC_DINH)
    parser.add_argument("--keywords", type=Path, default=KEYWORDS_MAC_DINH)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--target", type=int, default=1500)
    parser.add_argument("--checkpoint", type=int, default=10)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--login", action="store_true", help="Mở trình duyệt để đăng nhập thủ công trước khi cào")
    args = parser.parse_args(argv)
    if args.max_pages < 1 or args.target < 1 or args.checkpoint < 1 or args.delay_min < 2 or args.delay_max < args.delay_min:
        parser.error("Kiểm tra max-pages, target, checkpoint và delay (tối thiểu 2 giây)")
    schema = doc_schema()
    required = kiem_tra_anh_xa(schema)
    keywords = doc_keywords(args.keywords)
    if not keywords:
        parser.error("keyword.json không có từ khóa")
    rp, reason = kiem_thu_robot(TRANG_CHU, [tao_url_tim_kiem(k, 1) for k in keywords], TEN_BOT)
    if rp is None:
        print(reason)
        return 2
    rows = doc_csv(args.out)
    row_by_key = {khoa_url(str(row["URL_Goc"])): row for row in rows if row.get("URL_Goc")}
    stats: Counter = Counter()
    fresh, blocked, stop_all = 0, False, False
    salary_updates = changes_since_checkpoint = 0
    detail_checked: set[tuple] = set()
    forbidden_run = 0
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=args.headless and not args.login)
            context = browser.new_context(user_agent=TEN_BOT)
            page = context.new_page()
            try:
                if duoc_phep(rp, TRANG_CHU, TRANG_CHU, TEN_BOT):
                    pause = (args.delay_min, args.delay_max)
                    _, home_code = tai_thu_lai(
                        lambda u: _mo_trang(page, u, "trang_chu", pause),
                        TRANG_CHU, stats, khoang_nghi=pause,
                    )
                    if home_code != "ok":
                        print(f"Không mở được trang chủ TopDev ({home_code}); dừng trước khi tìm kiếm.")
                        return 2
                else:
                    print("robots.txt không cho phép trang chủ TopDev; bỏ qua bước mở trang chủ.")
                if args.login:
                    login_url = tao_url_tim_kiem(keywords[0], 1)
                    print("Đang mở TopDev. Hãy đăng nhập trong cửa sổ trình duyệt.")
                    try:
                        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                    except PlaywrightError as error:
                        print(f"Không mở được TopDev để đăng nhập: {error}")
                        return 2
                    input("Đăng nhập xong, nhấn Enter để bắt đầu cào...")
                for keyword in keywords:
                    if len(rows) >= args.target:
                        break
                    empty_pages = 0
                    print(f"Từ khóa: {keyword}")
                    for number in range(1, args.max_pages + 1):
                        search_url = tao_url_tim_kiem(keyword, number)
                        if not duoc_phep(rp, TRANG_CHU, search_url, TEN_BOT):
                            break
                        pause = (args.delay_min, args.delay_max)
                        html, code = tai_thu_lai(lambda u: _mo_trang(page, u, "danh_sach", pause), search_url, stats, khoang_nghi=pause)
                        if code in DUNG:
                            blocked = stop_all = True
                            break
                        if code == "khong_ton_tai":
                            break
                        if code != "ok":
                            continue
                        cards = parse_cards(html or "")
                        if not cards:
                            break
                        before = fresh + salary_updates
                        for card in cards:
                            existing = row_by_key.get(card["key"])
                            if existing is not None and existing.get("Luong"):
                                continue
                            if existing is not None and card.get("salary"):
                                existing["Luong"] = card["salary"]
                                salary_updates += 1
                                changes_since_checkpoint += 1
                                if changes_since_checkpoint >= args.checkpoint:
                                    xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                                    changes_since_checkpoint = 0
                                continue
                            if existing is not None and card["key"] in detail_checked:
                                continue
                            if not duoc_phep(rp, TRANG_CHU, card["url"], TEN_BOT):
                                continue
                            detail_html, detail_code = tai_thu_lai(
                                lambda u: _mo_trang(page, u, "chi_tiet", pause), card["url"], stats, khoang_nghi=pause
                            )
                            if detail_code in DUNG:
                                blocked = stop_all = True
                                break
                            if detail_code == "bi_cam":
                                forbidden_run += 1
                                if forbidden_run >= 3:
                                    print("Dừng: 3 trang chi tiết liên tiếp trả 403.")
                                    blocked = stop_all = True
                                    break
                                continue
                            forbidden_run = 0
                            if detail_code != "ok":
                                continue
                            detail = parse_detail(detail_html or "")
                            detail_checked.add(card["key"])
                            if existing is not None:
                                salary = detail.get("salary")
                                if salary:
                                    existing["Luong"] = salary
                                    salary_updates += 1
                                    changes_since_checkpoint += 1
                                    if changes_since_checkpoint >= args.checkpoint:
                                        xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                                        changes_since_checkpoint = 0
                                continue
                            row = _row(schema, card, detail, search_url, keyword, danh_dau_bat_dau())
                            missing = [c for c in required if row.get(c) is None or isinstance(row.get(c), str) and not row[c].strip()]
                            if missing:
                                print(f"Bỏ tin thiếu cột bắt buộc {missing}: {card['url']}")
                                continue
                            rows.append(row)
                            row_by_key[card["key"]] = row
                            fresh += 1
                            changes_since_checkpoint += 1
                            if changes_since_checkpoint >= args.checkpoint:
                                xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                                changes_since_checkpoint = 0
                            if len(rows) >= args.target:
                                stop_all = True
                                break
                        if stop_all:
                            break
                        empty_pages = empty_pages + 1 if fresh + salary_updates == before else 0
                        print(f"  Trang {number}: {len(cards)} thẻ; tin mới {fresh}; tổng {len(rows)}")
                        if empty_pages >= 2:
                            break
                    if stop_all:
                        break
            finally:
                context.close()
                browser.close()
    except KeyboardInterrupt:
        blocked = True
    finally:
        xuat_csv(args.out, rows, mot_dong_vat_ly=True)
        print(f"Thống kê: {dict(stats)}; tin mới: {fresh}; lương bổ sung: {salary_updates}; tổng: {len(rows)}; CSV: {args.out.resolve()}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
