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
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from crawlers import (
    DUNG,
    danh_dau_bat_dau,
    doc_csv,
    doc_schema,
    duoc_phep,
    kiem_thu_robot,
    khoa_url,
    nghi_ngau_nhien,
    tai_thu_lai,
    xuat_csv,
)

TRANG_CHU = "https://topdev.vn"
TEN_BOT = "DataMining-Crawler/1.0"
THU_MUC = Path(__file__).resolve().parent.parent
KEYWORDS_MAC_DINH = THU_MUC / "keyword.json"
OUT_MAC_DINH = THU_MUC / "data/raw/topdev.csv"
SO_LAN_CUON = 8

# Ánh xạ đầy đủ 18 cột theo đúng schema.json (v3.0.0)
ANH_XA_COT = {
    "web": "Web",
    "id": "Ma_Tin_Nguon",
    "url": "URL_Goc",
    "search_url": "URL_Tim_Kiem",
    "search_keyword": "Tu_Khoa_Tim_Kiem",
    "timestamp": "Timestamp",
    "title": "Tieu_De",
    "company": "Ten_Cong_Ty",
    "location": "Dia_Diem",
    "salary": "Luong",
    "experience": "Kinh_Nghiem",
    "work_type": "Hinh_Thuc_Lam_Viec",
    "contract": "Loai_Hop_Dong",
    "posted": "Ngay_Dang",
    "description": "Mo_Ta_Cong_Viec",
    "requirements": "Yeu_Cau_Chi_Tiet",
    "benefits": "Quyen_Loi",
    "skills": "Ky_Nang",
}


# ===========================================================================
# HÀM XỬ LÝ DỮ LIỆU XUỐNG DÒNG TRONG CSV VÀ CHUẨN HÓA VĂN BẢN
# ===========================================================================

def xu_ly_dong_van_ban(text: str | None) -> str | None:
    """Xóa bỏ hoàn toàn ký tự xuống dòng, gom khoảng trắng thành 1 dòng duy nhất.

    Dùng cho các trường một dòng như Tieu_De, Ten_Cong_Ty, Dia_Diem, Luong,
    Kinh_Nghiem, Hinh_Thuc_Lam_Viec, Loai_Hop_Dong, Ngay_Dang.
    """
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned or None


def xu_ly_khoi_van_ban(text: str | None, *, mot_dong_vat_ly: bool = False) -> str | None:
    """Chuẩn hóa khối văn bản nhiều dòng (Mo_Ta_Cong_Viec, Yeu_Cau_Chi_Tiet, Quyen_Loi).

    - Chuyển đổi các định dạng xuống dòng hỗn tạp (\\r\\n, \\r) thành \\n chuẩn.
    - Cắt khoảng trắng thừa đầu/cuối mỗi dòng và rút gọn dòng trống liên tiếp.
    - Khi mot_dong_vat_ly=True: thay thế ký tự \\n thực tế bằng ký tự literal '\\\\n'
      để dữ liệu trong ô CSV không làm vỡ record thành nhiều dòng vật lý.
    """
    if not text:
        return None
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    result_lines: list[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 2:
                result_lines.append("")
        else:
            blank_count = 0
            result_lines.append(line)

    cleaned = "\n".join(result_lines).strip()
    if not cleaned:
        return None
    if mot_dong_vat_ly:
        cleaned = cleaned.replace("\n", r"\n")
    return cleaned


def xu_ly_xuong_dong_csv(duong_dan_csv: Path | str, duong_dan_dich: Path | str | None = None) -> int:
    """Xử lý và chuẩn hóa toàn bộ file CSV để đảm bảo mỗi bản ghi nằm trên một dòng vật lý.

    Đọc các dòng CSV (hỗ trợ cả các ô có ký tự xuống dòng thực tế) rồi ghi lại
    ra file đích với mot_dong_vat_ly=True. Trả về số dòng đã xử lý.
    """
    duong_dan = Path(duong_dan_csv)
    if not duong_dan.is_file():
        return 0
    dich = Path(duong_dan_dich) if duong_dan_dich else duong_dan
    cac_dong = doc_csv(duong_dan)
    if cac_dong:
        xuat_csv(dich, cac_dong, mot_dong_vat_ly=True)
    return len(cac_dong)


# ===========================================================================
# CÁC HÀM TIỆN ÍCH SCHEMA VÀ TÌM KIẾM
# ===========================================================================

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
    """Kiểm tra ánh xạ ANH_XA_COT có đủ 18 cột theo schema.json không.

    Trả về tập hợp các cột bắt buộc không được null.
    """
    required_cols = list(schema["required"])
    required_non_null = {c for c in required_cols if "null" not in schema["properties"][c]["type"]}
    mapped = list(ANH_XA_COT.values())
    extra = sorted(set(mapped) - set(required_cols))
    missing = sorted(set(required_cols) - set(mapped))
    duplicates = len(mapped) != len(set(mapped))
    if extra or missing or duplicates:
        raise ValueError(
            f"ANH_XA_COT sai schema: cột thừa={extra}, cột thiếu={missing}, mapping trùng={duplicates}"
        )
    return required_non_null


def _text(node: Tag | None) -> str | None:
    if not node:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def _trich_xuat_muc(root: Tag, markers: tuple[str, ...]) -> str | None:
    """Trích xuất nội dung của một mục (yêu cầu, quyền lợi) dựa trên heading."""
    for heading in root.select("h2, h3, h4, h5, h6, strong, b, div[class*='title'], p[class*='title']"):
        label = (_text(heading) or "").casefold()
        if not any(marker in label for marker in markers):
            continue
        parent = heading
        for _ in range(4):
            if not isinstance(parent.parent, Tag) or parent.parent.name in ("main", "body", "html"):
                break
            parent = parent.parent
            if parent.name in ("section", "article", "div") and len(parent.get_text(" ", strip=True)) > len(label) + 20:
                break
        copied = BeautifulSoup(str(parent), "lxml")
        for junk in copied.select("script, style, noscript, button"):
            junk.decompose()
        text = copied.get_text("\n", strip=True)
        if text and len(text) > len(label):
            return xu_ly_khoi_van_ban(text)
    return None


# ===========================================================================
# PARSE THẺ CARD VÀ TRANG CHI TIẾT
# ===========================================================================

def parse_cards(html: str) -> list[dict[str, Any]]:
    """Bóc các card TopDev, phân loại địa điểm, hình thức làm việc, kinh nghiệm."""
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
        card = item
        if item.name == "a":
            for _ in range(6):
                if not card.parent or card.parent.name in ("body", "html"):
                    break
                card = card.parent
                if len(card.get_text(" ", strip=True)) > len(item.get_text(" ", strip=True)) + 10:
                    break

        company_node = card.select_one("span.line-clamp-1")
        grid = card.select_one("div.mt-2.grid")
        grid_values = [x.get_text(" ", strip=True) for x in grid.select("span.line-clamp-1")] if grid else []
        salary_node = next((x for x in card.select("span") if "salary" in " ".join(x.get("class", [])).lower()), None)
        skills = [x.get_text(" ", strip=True) for x in card.select("a.line-clamp-1.h-6") if x.get_text(" ", strip=True)]
        posted_node = card.select_one("span.text-xs.text-text-500")

        # Phân loại grid_values thành location, work_type, experience
        locations: list[str] = []
        work_types: list[str] = []
        experiences: list[str] = []
        for val in grid_values:
            val_clean = xu_ly_dong_van_ban(val)
            if not val_clean:
                continue
            val_lower = val_clean.lower()
            if any(wt in val_lower for wt in ["fulltime", "full-time", "full time", "parttime", "part-time", "part time", "remote", "hybrid", "freelance", "internship", "thực tập"]):
                work_types.append(val_clean)
            elif any(kw in val_lower for kw in ["year", "năm", "chuyên viên", "senior", "junior", "lead", "manager", "intern", "kinh nghiệm"]):
                experiences.append(val_clean)
            elif not locations:
                locations.append(val_clean)
            else:
                experiences.append(val_clean)

        raw_salary = _text(salary_node)
        if raw_salary and re.search(r"login|đăng nhập|log in", raw_salary, re.IGNORECASE):
            raw_salary = None

        match_id = re.search(r"(\d+)(?:\.html)?$", url.rstrip("/"))
        job_id = match_id.group(1) if match_id else None

        rows.append({
            "url": url,
            "key": key,
            "id": job_id,
            "title": xu_ly_dong_van_ban(_text(link)),
            "company": xu_ly_dong_van_ban(_text(company_node)),
            "location": locations[0] if locations else None,
            "work_type": ", ".join(work_types) if work_types else None,
            "experience": ", ".join(experiences) if experiences else None,
            "salary": xu_ly_dong_van_ban(raw_salary),
            "posted": xu_ly_dong_van_ban(_text(posted_node)),
            "skills": list(dict.fromkeys(skills)) or None,
            "listing_text": xu_ly_khoi_van_ban(card.get_text("\n", strip=True)),
        })
    return rows


def parse_detail(html: str) -> dict[str, Any]:
    """Bóc các trường chi tiết từ HTML trang tuyển dụng TopDev."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not isinstance(main, Tag):
        return {}

    title_node = main.select_one("h1")
    title = xu_ly_dong_van_ban(_text(title_node))
    company_node = main.select_one("a[href*='/company/'], a[href*='/companies/'], [class*='company']")
    company = xu_ly_dong_van_ban(_text(company_node))

    salary_node = next((node for node in main.select("[class*='salary'], [class*='wage']") if _text(node)), None)
    salary = xu_ly_dong_van_ban(_text(salary_node))
    if salary and re.search(r"login|đăng nhập|log in", salary, re.IGNORECASE):
        salary = None

    location_node = main.select_one("[class*='location'], [class*='address']")
    location = xu_ly_dong_van_ban(_text(location_node))

    exp_node = main.select_one("[class*='experience'], [class*='exp']")
    experience = xu_ly_dong_van_ban(_text(exp_node))

    work_type_node = main.select_one("[class*='work-type'], [class*='employment']")
    work_type = xu_ly_dong_van_ban(_text(work_type_node))

    posted_node = main.select_one("[class*='posted'], [class*='created-at'], time")
    posted = xu_ly_dong_van_ban(_text(posted_node))

    skill_nodes = main.select("a[class*='skill'], [class*='skill-tag'], a[class*='tag']")
    skills = list(dict.fromkeys(x.get_text(" ", strip=True) for x in skill_nodes if x.get_text(" ", strip=True))) or None

    description_container = (
        main.select_one("[class*='job-description']")
        or main.select_one("[class*='description']")
        or main.select_one("[class*='job-detail']")
        or main.select_one("[class*='detail-job']")
        or main.select_one("[class*='detail-content']")
    )

    description_text = None
    target_node = description_container or main
    if target_node:
        copied = BeautifulSoup(str(target_node), "lxml")
        for junk in copied.select("script, style, noscript, nav, footer, aside, form, button"):
            junk.decompose()
        for heading in copied.select("h1"):
            heading.decompose()
        raw_desc = copied.get_text("\n", strip=True)
        if raw_desc and len(raw_desc) > 30:
            description_text = xu_ly_khoi_van_ban(raw_desc)

    requirements_text = _trich_xuat_muc(
        target_node,
        markers=("yêu cầu", "yeu cau", "requirement", "qualification", "kỹ năng & kinh nghiệm", "skills & experience"),
    )
    benefits_text = _trich_xuat_muc(
        target_node,
        markers=("quyền lợi", "quyen loi", "phúc lợi", "phuc loi", "benefit", "what we offer", "chế độ", "đãi ngộ"),
    )

    return {
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "experience": experience,
        "work_type": work_type,
        "posted": posted,
        "description": description_text,
        "requirements": requirements_text,
        "benefits": benefits_text,
        "skills": skills,
    }


def kiem_thu_robot_playwright(
    page: Any, trang_chu: str, url_muc_tieu: list[str], ten_bot: str
) -> tuple[RobotFileParser | None, str]:
    """Fallback kiểm tra robots.txt qua Playwright khi urllib bị chặn TLS Handshake bởi WAF/Cloudflare."""
    thanh_phan = urlsplit(trang_chu)
    if not thanh_phan.scheme or not thanh_phan.netloc:
        return None, "trang_chu không hợp lệ"
    goc = f"{thanh_phan.scheme}://{thanh_phan.netloc}"
    robots_url = f"{goc}/robots.txt"
    noi_dung = ""

    try:
        response = page.goto(robots_url, wait_until="domcontentloaded", timeout=20000)
        ma = response.status if response else 0
        if ma == 404:
            return None, "không tìm thấy robots.txt (HTTP 404)"
        if ma != 200 and ma != 0:
            return None, f"không tải được robots.txt qua Playwright (HTTP {ma})"
        noi_dung = page.inner_text("body")
    except Exception as loi:
        return None, f"lỗi khi tải robots.txt qua Playwright: {loi}"

    if not noi_dung or not noi_dung.strip():
        return None, "nội dung robots.txt trống"

    rp = RobotFileParser()
    rp.parse(noi_dung.splitlines())
    for url in url_muc_tieu or [f"{goc}/"]:
        if not rp.can_fetch(ten_bot, url):
            return None, f"robots.txt không cho phép: {url}"
    return rp, ""


def doi_dang_nhap(page: Any, url_dang_nhap: str) -> bool:
    """Mở trình duyệt cho người dùng đăng nhập thủ công và chờ nhấn Enter trước khi bắt đầu cào."""
    print(f"Đang mở TopDev ({url_dang_nhap}). Hãy đăng nhập trong cửa sổ trình duyệt.")
    try:
        page.goto(url_dang_nhap, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightError as error:
        print(f"Không mở được TopDev để đăng nhập: {error}")
        return False
    try:
        input("Đăng nhập xong, nhấn Enter tại terminal để bắt đầu cào...")
    except EOFError:
        print("Không nhận được tương tác từ bàn phím (EOF), tiếp tục cào...")
    return True


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
    """Tạo một dòng dữ liệu theo đúng schema và thứ tự cột.

    - Đảm bảo Timestamp bắt buộc có giá trị ISO 8601 có múi giờ.
    - Làm sạch ký tự xuống dòng cho các trường một dòng.
    - Chuẩn hóa văn bản cho các trường nhiều dòng (Mo_Ta_Cong_Viec, Yeu_Cau_Chi_Tiet, Quyen_Loi).
    """
    ts = timestamp or danh_dau_bat_dau()
    job_id = card.get("id") or detail.get("id")
    if not job_id and card.get("url"):
        match = re.search(r"(\d+)(?:\.html)?$", card["url"].rstrip("/"))
        job_id = match.group(1) if match else None

    # Lương: loại bỏ chuỗi login nếu có
    salary = detail.get("salary") or card.get("salary")
    if salary and re.search(r"login|đăng nhập|log in", salary, re.IGNORECASE):
        salary = None

    # Mô tả công việc: ưu tiên detail, fallback sang card listing_text
    description = detail.get("description") or card.get("listing_text")

    skills = detail.get("skills") or card.get("skills")

    values = {
        "web": "topdev",
        "id": str(job_id) if job_id is not None else None,
        "url": card["url"],
        "search_url": search_url,
        "search_keyword": keyword,
        "timestamp": ts,
        "title": xu_ly_dong_van_ban(detail.get("title") or card.get("title")),
        "company": xu_ly_dong_van_ban(detail.get("company") or card.get("company")),
        "location": xu_ly_dong_van_ban(detail.get("location") or card.get("location")),
        "salary": xu_ly_dong_van_ban(salary),
        "experience": xu_ly_dong_van_ban(detail.get("experience") or card.get("experience")),
        "work_type": xu_ly_dong_van_ban(detail.get("work_type") or card.get("work_type")),
        "contract": xu_ly_dong_van_ban(detail.get("contract") or card.get("contract")),
        "posted": xu_ly_dong_van_ban(detail.get("posted") or card.get("posted")),
        "description": xu_ly_khoi_van_ban(description),
        "requirements": xu_ly_khoi_van_ban(detail.get("requirements")),
        "benefits": xu_ly_khoi_van_ban(detail.get("benefits")),
        "skills": skills,
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
    parser.add_argument("--fix-csv", type=Path, help="Xử lý chuẩn hóa file CSV bị xuống dòng thành một dòng vật lý rồi thoát")
    args = parser.parse_args(argv)

    # Tiện ích chuyển đổi file CSV bị xuống dòng nếu được chỉ định qua --fix-csv
    if args.fix_csv:
        count = xu_ly_xuong_dong_csv(args.fix_csv, args.out if args.out != OUT_MAC_DINH else args.fix_csv)
        print(f"Đã xử lý xuống dòng cho file CSV {args.fix_csv}: {count} bản ghi.")
        return 0

    if args.max_pages < 1 or args.target < 1 or args.checkpoint < 1 or args.delay_min < 2 or args.delay_max < args.delay_min:
        parser.error("Kiểm tra max-pages, target, checkpoint và delay (tối thiểu 2 giây)")

    schema = doc_schema()
    required = kiem_tra_anh_xa(schema)
    keywords = doc_keywords(args.keywords)
    if not keywords:
        parser.error("keyword.json không có từ khóa")

    target_urls = [tao_url_tim_kiem(k, 1) for k in keywords]
    rp, reason = kiem_thu_robot(TRANG_CHU, target_urls, TEN_BOT)
    if rp is None:
        print(f"Cảnh báo: urllib không tải được robots.txt ({reason}).")
        print("Sẽ tự động kiểm tra lại robots.txt qua Playwright khi khởi động trình duyệt...")

    rows = doc_csv(args.out)
    row_by_key = {khoa_url(str(row["URL_Goc"])): row for row in rows if row.get("URL_Goc")}

    # Đảm bảo các dòng cũ đã đọc lên không bị thiếu Timestamp bắt buộc
    for r in rows:
        if not r.get("Timestamp"):
            r["Timestamp"] = danh_dau_bat_dau()

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
                if rp is None:
                    print("Đang tải và kiểm tra robots.txt qua Playwright...")
                    rp, reason = kiem_thu_robot_playwright(page, TRANG_CHU, target_urls, TEN_BOT)
                    if rp is None:
                        print(f"Kiểm tra robots.txt qua Playwright thất bại: {reason}")
                        return 2
                    print("Kiểm tra robots.txt qua Playwright thành công: các URL đều được phép.")

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
                    if not doi_dang_nhap(page, login_url):
                        return 2

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
                        html, code = tai_thu_lai(
                            lambda u: _mo_trang(page, u, "danh_sach", pause),
                            search_url, stats, khoang_nghi=pause,
                        )
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

                            # Thời điểm đánh dấu bắt đầu xử lý tin
                            thoi_diem = danh_dau_bat_dau()

                            if existing is not None and card.get("salary"):
                                existing["Luong"] = card["salary"]
                                if not existing.get("Timestamp"):
                                    existing["Timestamp"] = thoi_diem
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

                            # Ghi nhận thời điểm ngay trước khi tải trang chi tiết
                            thoi_diem_chi_tiet = danh_dau_bat_dau()
                            detail_html, detail_code = tai_thu_lai(
                                lambda u: _mo_trang(page, u, "chi_tiet", pause),
                                card["url"], stats, khoang_nghi=pause,
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
                                if not existing.get("Timestamp"):
                                    existing["Timestamp"] = thoi_diem_chi_tiet
                                changes_since_checkpoint += 1
                                if changes_since_checkpoint >= args.checkpoint:
                                    xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                                    changes_since_checkpoint = 0
                                continue

                            row = _row(schema, card, detail, search_url, keyword, thoi_diem_chi_tiet)
                            missing = [
                                c for c in required
                                if row.get(c) is None or (isinstance(row.get(c), str) and not row[c].strip())
                            ]
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
