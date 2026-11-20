"""Crawler tin tuyển dụng Saramin Vietnam theo schema chung của project."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from crawlers import (
    DUNG, danh_dau_bat_dau, doc_csv, doc_schema, duoc_phep,
    kiem_thu_robot, khoa_url, nghi_ngau_nhien, tai_thu_lai, xuat_csv,
)

TRANG_CHU = "https://saramin.vn"
TEN_BOT = "DataMining-Crawler/1.0"
THU_MUC = Path(__file__).resolve().parent.parent
KEYWORDS_MAC_DINH = THU_MUC / "keyword.json"
OUT_MAC_DINH = THU_MUC / "data" / "raw" / "raw_saramin.csv"
SO_LAN_CUON = 8

ANH_XA_COT = {
    "web": "Web", "id": "Ma_Tin_Nguon", "url": "URL_Goc",
    "search_url": "URL_Tim_Kiem", "search_keyword": "Tu_Khoa_Tim_Kiem",
    "timestamp": "Timestamp", "title": "Tieu_De", "company": "Ten_Cong_Ty",
    "location": "Dia_Diem", "salary": "Luong", "experience": "Kinh_Nghiem",
    "work_type": "Hinh_Thuc_Lam_Viec", "contract": "Loai_Hop_Dong",
    "posted": "Ngay_Dang", "description": "Mo_Ta_Cong_Viec",
    "requirements": "Yeu_Cau_Chi_Tiet", "benefits": "Quyen_Loi", "skills": "Ky_Nang",
}


def tao_url_tim_kiem(keyword: str, page_num: int) -> str:
    """Saramin Vietnam nhận keyword và page trên /jobs/search."""
    return f"{TRANG_CHU}/jobs/search?{urlencode({'keyword': keyword, 'page': page_num})}"


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
    if extra or missing or len(mapped) != len(set(mapped)):
        raise ValueError(f"Ánh xạ Saramin sai schema: cột thừa={extra}, cột bắt buộc chưa ánh xạ={missing}")
    return required


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def _url_tin(href: str) -> str | None:
    url = urljoin(TRANG_CHU, href.split("#", 1)[0])
    parts = urlsplit(url)
    if (parts.hostname or "").lower().removeprefix("www.") != "saramin.vn":
        return None
    if not (parts.path.startswith("/detail-jobs/") or parts.path.startswith("/viec-lam/")):
        return None
    return f"https://saramin.vn{parts.path}"


def _khung_tin(link: Tag) -> Tag:
    """Tìm card gần link tin, tránh gom cả danh sách khi chọn thông tin phụ."""
    node = link
    best = link
    for _ in range(8):
        parent = node.parent
        if not isinstance(parent, Tag) or parent.name in ("body", "html"):
            break
        job_links = parent.select("a[href*='/detail-jobs/'], a[href*='/viec-lam/']")
        if len(job_links) > 1:
            break
        node = best = parent
        if parent.css.match(
            "article, li, [class*='job-card' i], [class*='job-item' i], "
            "[class*='job-list' i], [class*='posting' i]"
        ):
            break
    return best


def _gia_tri_the(card: Tag, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        node = card.select_one(selector)
        value = _text(node)
        if value:
            return value
    return None


def _dong_phu_hop(text: str, pattern: re.Pattern) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line and pattern.search(line):
            return line
    return None


def parse_cards(html: str) -> list[dict[str, Any]]:
    """Bóc các tin Saramin từ link detail-jobs/viec-lam trên trang kết quả."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in soup.select("a[href*='/detail-jobs/'], a[href*='/viec-lam/']"):
        href = str(link.get("href", ""))
        url = _url_tin(href)
        title = _text(link)
        if not url or not title or url in seen:
            continue
        seen.add(url)
        card = _khung_tin(link)
        card_text = card.get_text("\n", strip=True)
        lines = [line.strip() for line in card_text.splitlines() if line.strip()]

        company = _gia_tri_the(card, (
            "[class*='company-name']", "[class*='company_name']",
            "[class*='companyName']", "a[href*='/company/']", "a[href*='/companies/']",
        ))
        if not company:
            for candidate in card.select("a"):
                candidate_url = str(candidate.get("href", ""))
                candidate_text = _text(candidate)
                if candidate_text and candidate_text != title and "/detail-jobs/" not in candidate_url and "/viec-lam/" not in candidate_url:
                    if not candidate.css.match("[class*='tag' i], [class*='skill' i]"):
                        company = candidate_text
                        break

        location = _gia_tri_the(card, (
            "[class*='location']", "[class*='address']", "[class*='region']",
        ))
        if not location:
            location = _dong_phu_hop(card_text, re.compile(
                r"Hồ Chí Minh|TP\.?\s*HCM|Hà Nội|Đà Nẵng|Cần Thơ|Bình Dương|Đồng Nai|"
                r"Remote|Hybrid|On-site|Toàn quốc", re.IGNORECASE,
            ))

        salary = _gia_tri_the(card, ("[class*='salary']", "[class*='wage']"))
        if salary and re.search(r"login|đăng nhập|log in", salary, re.IGNORECASE):
            salary = None
        if not salary:
            salary = _dong_phu_hop(card_text, re.compile(
                r"thỏa thuận|thoả thuận|triệu|\bVND\b|\bUSD\b|\$|₫|\bM/tháng", re.IGNORECASE,
            ))
        if salary and re.search(r"login|đăng nhập|log in", salary, re.IGNORECASE):
            salary = None

        experience = _gia_tri_the(card, ("[class*='experience']", "[class*='exp-level']"))
        if not experience:
            experience = _dong_phu_hop(card_text, re.compile(
                r"(?:\d+\s*(?:-|–|to)\s*\d+\s*)?(?:years?|năm)\b|"
                r"kinh nghiệm|experience|not required|không yêu cầu", re.IGNORECASE,
            ))
        work_type = _gia_tri_the(card, ("[class*='work-type']", "[class*='employment']"))
        if not work_type:
            work_type = _dong_phu_hop(card_text, re.compile(
                r"full.?time|part.?time|freelance|internship|thực tập|toàn thời gian|bán thời gian|hybrid|remote", re.IGNORECASE,
            ))
        posted = _gia_tri_the(card, ("[class*='posted']", "[class*='created-at']", "time"))
        if not posted:
            posted = _dong_phu_hop(card_text, re.compile(
                r"\b(?:\d+\s*(?:minutes?|hours?|days?|weeks?|months?|phút|giờ|ngày|tuần|tháng)\s*ago|"
                r"\d+\s*(?:phút|giờ|ngày|tuần|tháng)\s*trước|hôm qua|today|yesterday)\b", re.IGNORECASE,
            ))

        skill_nodes = card.select("a[class*='skill'], a[class*='tag'], [class*='skill-tag']")
        skills = list(dict.fromkeys(value for node in skill_nodes if (value := _text(node)))) or None
        match = re.search(r"-(\d+)(?:\.html)?$", urlsplit(url).path)
        rows.append({
            "url": url, "key": khoa_url(url), "id": match.group(1) if match else None,
            "title": title, "company": company, "location": location, "salary": salary,
            "experience": experience, "work_type": work_type, "posted": posted,
            "skills": skills, "listing_text": card_text or None,
        })
    return rows


def _text_block(node: Tag, title: str | None = None) -> str | None:
    """Lấy văn bản trong khối tin, bỏ điều khiển trang và tiêu đề lặp."""
    copied = BeautifulSoup(str(node), "lxml")
    for junk in copied.select("script, style, noscript, nav, footer, aside, form, button"):
        junk.decompose()
    title_text = title.strip() if title else None
    for heading in copied.select("h1, h2, h3, h4, h5, h6"):
        if heading.name == "h1" or (title_text and _text(heading) == title_text):
            heading.decompose()
    text = copied.get_text("\n", strip=True)
    return text or None


def _section_text(root: Tag, markers: tuple[str, ...], title: str | None) -> str | None:
    for heading in root.select("h2, h3, h4, h5, strong, b"):
        label = (_text(heading) or "").casefold()
        if not any(marker in label for marker in markers):
            continue
        section: Tag | None = heading
        for _ in range(4):
            if not isinstance(section.parent, Tag) or section.parent.name in ("main", "body", "html"):
                break
            section = section.parent
            if section.css.match(
                "section, article, [class*='description' i], [class*='content' i], "
                "[class*='section' i], [class*='detail' i]"
            ):
                break
        value = _text_block(section, title) if section else None
        if value and len(value) > len(label):
            return value
    return None


def _muc_mo_ta_tu_tieu_de(root: Tag, labels: tuple[str, ...]) -> list[tuple[str, str]]:
    """Lấy từng mục trong mô tả theo tiêu đề, kể cả tiêu đề nằm trong span của giao diện React."""
    def chuan_hoa(line: str) -> str:
        line = re.sub(r"^\s*\d+\s*[.)-]?\s*", "", line)
        return " ".join(line.casefold().strip().rstrip(":.").split())

    muc_tieu = {chuan_hoa(label) for label in labels}
    # Dùng các tiêu đề phổ biến làm ranh giới để không kéo nội dung của mục sau vào mục trước.
    tieu_de_muc = {
        *muc_tieu,
        "mô tả công việc", "job description", "yêu cầu", "yêu cầu ứng viên",
        "your skills and experience", "requirements", "qualification", "about the company",
        "quyền lợi", "phúc lợi", "benefits", "what we offer",
        "thông tin khác", "other information", "địa điểm làm việc", "apply now",
    }
    lines = [" ".join(line.split()) for line in root.get_text("\n", strip=True).splitlines() if line.strip()]
    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        label = chuan_hoa(line)
        if label in muc_tieu:
            found.append((index, label))

    sections: list[tuple[str, str]] = []
    for index, label in found:
        end = next((i for i in range(index + 1, len(lines)) if chuan_hoa(lines[i]) in tieu_de_muc), len(lines))
        section = "\n".join(lines[index:end]).strip()
        if section and (not sections or section != sections[-1][1]):
            sections.append((label, section))
    return sections


def parse_detail(html: str) -> dict[str, Any]:
    """Bóc thông tin trang chi tiết; giữ toàn văn khối mô tả theo thứ tự nguồn."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not isinstance(main, Tag):
        return {}
    title = _text(main.select_one("h1"))
    company = _gia_tri_the(main, (
        "[class*='company-name']", "[class*='company_name']",
        "[class*='companyName']", "a[href*='/company/']", "a[href*='/companies/']",
    ))
    description = None
    for selector in (
        "[class*='job-description']", "[class*='job_detail']",
        "[class*='job-detail']", "[class*='detail-content']", "[class*='description']",
    ):
        node = main.select_one(selector)
        value = _text_block(node, title) if node else None
        if value and len(value) > 40:
            description = value
            break
    if not description:
        description = _text_block(main, title)

    # Saramin đặt tên mục trong các span; tìm trên main để không bỏ sót mục do khối description bị lồng.
    # Gộp nguyên văn trách nhiệm, kỹ năng/trình độ và quyền lợi vào mô tả chi tiết.
    cac_muc_mo_ta = _muc_mo_ta_tu_tieu_de(main, (
        "vai trò & trách nhiệm của bạn", "vai trò và trách nhiệm của bạn",
        "your role and responsibilities", "role & responsibilities", "responsibilities",
        "kỹ năng & trình độ của bạn", "kỹ năng và trình độ của bạn",
        "your skills and qualifications", "your skills and experience", "qualifications",
        "quyền lợi", "phúc lợi", "benefits", "what we offer",
    ))
    muc_theo_tieu_de: dict[str, str] = {}
    for label, section in cac_muc_mo_ta:
        muc_theo_tieu_de.setdefault(label, section)
    vai_tro = next((muc_theo_tieu_de.get(label) for label in (
        "vai trò & trách nhiệm của bạn", "vai trò và trách nhiệm của bạn",
        "your role and responsibilities", "role & responsibilities", "responsibilities",
    ) if muc_theo_tieu_de.get(label)), None)
    ky_nang_trinh_do = next((muc_theo_tieu_de.get(label) for label in (
        "kỹ năng & trình độ của bạn", "kỹ năng và trình độ của bạn",
        "your skills and qualifications", "your skills and experience", "qualifications",
    ) if muc_theo_tieu_de.get(label)), None)
    quyen_loi_muc = next((muc_theo_tieu_de.get(label) for label in (
        "quyền lợi", "phúc lợi", "benefits", "what we offer",
    ) if muc_theo_tieu_de.get(label)), None)
    if vai_tro and ky_nang_trinh_do and quyen_loi_muc:
        # Giữ thứ tự hiển thị của các mục trong HTML nguồn.
        cac_phan, da_gop = [], set()
        for _, section in cac_muc_mo_ta:
            if section in {vai_tro, ky_nang_trinh_do, quyen_loi_muc} and section not in da_gop:
                cac_phan.append(section)
                da_gop.add(section)
        description = "\n\n".join(cac_phan)

    body_text = main.get_text("\n", strip=True)
    salary = _gia_tri_the(main, ("[class*='salary']", "[class*='wage']"))
    if salary and re.search(r"login|đăng nhập|log in", salary, re.IGNORECASE):
        salary = None
    if not salary:
        salary = _dong_phu_hop(body_text, re.compile(
            r"thỏa thuận|thoả thuận|triệu|\bVND\b|\bUSD\b|\$|₫|\bM/tháng", re.IGNORECASE,
        ))
    experience = _gia_tri_the(main, ("[class*='experience']", "[class*='exp-level']"))
    if not experience:
        experience = _dong_phu_hop(body_text, re.compile(
            r"(?:\d+\s*(?:-|–|to)\s*\d+\s*)?(?:years?|năm)\b|"
            r"kinh nghiệm|experience|not required|không yêu cầu", re.IGNORECASE,
        ))
    location = _gia_tri_the(main, ("[class*='location']", "[class*='address']", "[class*='region']"))
    if not location:
        location = _dong_phu_hop(body_text, re.compile(
            r"Hồ Chí Minh|TP\.?\s*HCM|Hà Nội|Đà Nẵng|Cần Thơ|Bình Dương|Đồng Nai|"
            r"Remote|Hybrid|On-site|Toàn quốc", re.IGNORECASE,
        ))
    posted = _gia_tri_the(main, ("[class*='posted']", "[class*='created-at']", "time"))
    if not posted:
        posted = _dong_phu_hop(body_text, re.compile(
            r"\b(?:\d+\s*(?:minutes?|hours?|days?|weeks?|months?|phút|giờ|ngày|tuần|tháng)\s*ago|"
            r"\d+\s*(?:phút|giờ|ngày|tuần|tháng)\s*trước|hôm qua|today|yesterday)\b", re.IGNORECASE,
        ))
    requirements = vai_tro or _section_text(main, (
        "requirement", "yêu cầu", "yeu cau", "điều kiện", "qualification",
    ), title)
    benefits = quyen_loi_muc or _section_text(main, (
        "benefit", "what we offer", "compensation", "phúc lợi", "phuc loi", "quyền lợi", "quyen loi",
    ), title)
    skill_nodes = main.select("a[class*='skill'], a[class*='tag'], [class*='skill-tag']")
    skills = ky_nang_trinh_do or (
        list(dict.fromkeys(value for node in skill_nodes if (value := _text(node)))) or None
    )

    return {
        "title": title, "company": company, "location": location, "salary": salary,
        "experience": experience, "posted": posted, "description": description,
        "requirements": requirements, "benefits": benefits, "skills": skills,
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
            return None, "bi_cam" if loai == "chi_tiet" else "bi_chan"
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
                    "a[href*='/detail-jobs/'], a[href*='/viec-lam/']" if loai == "danh_sach" else "main h1, article h1")
        try:
            page.wait_for_selector(selector, timeout=15000)
        except PlaywrightTimeoutError:
            pass
        html = page.content()
        title = (page.title() or "").casefold()
        text = html.casefold()
        if "verify you are human" in text or "cf-chl-" in text or ("access denied" in title and not page.locator(selector).count()):
            return None, "bi_chan"
        if loai == "danh_sach":
            old_count, stagnant = page.locator("a[href*='/detail-jobs/'], a[href*='/viec-lam/']").count(), 0
            for _ in range(SO_LAN_CUON):
                if stagnant >= 2:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                nghi_ngau_nhien(khoang_nghi)
                new_count = page.locator("a[href*='/detail-jobs/'], a[href*='/viec-lam/']").count()
                stagnant = stagnant + 1 if new_count <= old_count else 0
                old_count = new_count
            html = page.content()
        return html, "ok"
    except (PlaywrightError, OSError):
        return None, "loi_tam_thoi"


def _row(schema: dict[str, Any], card: dict[str, Any], detail: dict[str, Any],
         search_url: str, keyword: str, timestamp: str) -> dict[str, Any]:
    values = {
        "web": "saramin", "id": detail.get("id") or card.get("id"),
        "url": card["url"], "search_url": search_url, "search_keyword": keyword,
        "timestamp": timestamp, "title": detail.get("title") or card.get("title"),
        "company": detail.get("company") or card.get("company"),
        "location": detail.get("location") or card.get("location"),
        "salary": detail.get("salary") or card.get("salary"),
        "experience": detail.get("experience") or card.get("experience"),
        "work_type": card.get("work_type"), "contract": None,
        "posted": detail.get("posted") or card.get("posted"),
        "description": detail.get("description"),
        "requirements": detail.get("requirements"), "benefits": detail.get("benefits"),
        "skills": detail.get("skills") or card.get("skills"),
    }
    row = {column: None for column in schema["required"]}
    for key, column in ANH_XA_COT.items():
        row[column] = values.get(key)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawler Saramin Vietnam theo keyword.json")
    parser.add_argument("--out", type=Path, default=OUT_MAC_DINH)
    parser.add_argument("--keywords", type=Path, default=KEYWORDS_MAC_DINH)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--target", type=int, default=1500)
    parser.add_argument("--checkpoint", type=int, default=10)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--login", action="store_true", help="Đăng nhập thủ công trước khi cào")
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
    forbidden_run = 0
    salary_updates = changes_since_checkpoint = 0
    detail_checked: set[tuple] = set()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=args.headless and not args.login)
            context = browser.new_context(
                user_agent=TEN_BOT, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            try:
                if duoc_phep(rp, TRANG_CHU, TRANG_CHU, TEN_BOT):
                    pause = (args.delay_min, args.delay_max)
                    _, home_code = tai_thu_lai(
                        lambda u: _mo_trang(page, u, "trang_chu", pause),
                        TRANG_CHU, stats, khoang_nghi=pause,
                    )
                    if home_code != "ok":
                        print(f"Không mở được trang chủ Saramin ({home_code}); dừng trước khi tìm kiếm.")
                        return 2
                else:
                    print("robots.txt không cho phép trang chủ Saramin; bỏ qua bước mở trang chủ.")
                if args.login:
                    login_url = tao_url_tim_kiem(keywords[0], 1)
                    print("Đang mở Saramin. Hãy đăng nhập trong cửa sổ trình duyệt.")
                    try:
                        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                    except PlaywrightError as error:
                        print(f"Không mở được Saramin để đăng nhập: {error}")
                        return 2
                    input("Đăng nhập xong, nhấn Enter để bắt đầu cào...")

                for keyword in keywords:
                    if len(rows) >= args.target:
                        break
                    empty_pages = 0
                    print(f"Từ khóa: {keyword}")
                    for page_num in range(1, args.max_pages + 1):
                        search_url = tao_url_tim_kiem(keyword, page_num)
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
                                    changes_since_checkpoint += 1
                                    if changes_since_checkpoint >= args.checkpoint:
                                        xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                                        changes_since_checkpoint = 0
                                continue
                            row = _row(schema, card, detail, search_url, keyword, danh_dau_bat_dau())
                            missing = [
                                column for column in required
                                if row.get(column) is None or isinstance(row.get(column), str) and not row[column].strip()
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
                        print(f"  Trang {page_num}: {len(cards)} thẻ; tin mới {fresh}; tổng {len(rows)}")
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
