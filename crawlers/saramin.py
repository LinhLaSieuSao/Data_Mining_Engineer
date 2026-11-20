"""Crawler Saramin Vietnam. Cào HTML công khai, CSV theo schema chung."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers.base_crawler import (
    DUNG, THU_MUC_GOC, danh_dau_bat_dau, doc_csv, doc_schema, duoc_phep, kiem_thu_robot,
    nghi_ngau_nhien, tai_thu_lai, xuat_csv,
)
from crawlers.browser import (
    du_lieu_nhung_saramin, duyet_trang_saramin, phien_luong_saramin, tai_trang_luong_saramin,
)
from crawlers.itviec import bi_thu_thach, la_thu_thach_cloudflare

TRANG_CHU = "https://saramin.vn"
TRANG_TIM_KIEM = TRANG_CHU + "/viec-lam/tim-kiem"
TRANG_DANG_NHAP = TRANG_CHU + "/ung-vien/dang-nhap"
TEN_BOT = "DataMining-Crawler/1.0"
KEYWORDS_MAC_DINH = THU_MUC_GOC / "keyword.json"
OUT_MAC_DINH = THU_MUC_GOC / "data" / "raw" / "raw_saramin.csv"
DUONG_DAN_TIN = re.compile(r"/(?:viec-lam|detail-jobs)/(?P<slug>[^/]+-(?P<id>\d+))/?")
THE_TIN = "div.text-card-foreground.cursor-pointer"
THE_KY_NANG = 'a[href^="/jobs/search?keyword="], a[href^="/viec-lam/tim-kiem?keyword="]'
O_LUONG = 'span[class~="text-[#E4007F]"], span[class~="text-[#e4007f]"]'
KHOA_LUONG = re.compile(r"đăng nhập|sign in|log ?in", re.I)
KINH_NGHIEM = re.compile(r"\b\d+[+]?\s*(?:năm|tháng|years?|months?)\b|không yêu cầu|not required|no experience", re.I)
HINH_THUC = re.compile(r"on[\s-]*site|hybrid|remote|tại văn phòng|trực tiếp|từ xa|kết hợp|làm việc tại nhà", re.I)
HOP_DONG = re.compile(
    r"full[\s-]*time|part[\s-]*time|toàn thời gian|bán thời gian|"
    r"freelance(?:r)?|thời vụ|hợp đồng|contract(?:or)?|temporary|permanent|internship|thực tập",
    re.I,
)
NGAY_TUONG_DOI = re.compile(
    r"(?:\d+\s+(?:phút|giờ|ngày|tuần|tháng|minutes?|hours?|days?|weeks?|months?)\s+(?:trước|ago)"
    r"|vừa xong|hôm nay|hôm qua|today|yesterday|just now)",
    re.I,
)
CAC_NHAN = {
    "vai trò & trách nhiệm của bạn": "vai_tro", "your role & responsibilities": "vai_tro",
    "kỹ năng & trình độ của bạn": "Yeu_Cau_Chi_Tiet", "your skills & qualifications": "Yeu_Cau_Chi_Tiet",
    "your skills & experience": "Yeu_Cau_Chi_Tiet",
    "quyền lợi": "Quyen_Loi", "benefits": "Quyen_Loi",
}
KHOI_VAN_BAN = {"address", "blockquote", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                "li", "ol", "p", "section", "table", "tr", "ul"}


def tao_url_tim_kiem(keyword: str, page_num: int = 1) -> str:
    params = {"keyword": keyword} if keyword else {}
    if page_num > 1:
        params["page"] = str(page_num)
    return f"{TRANG_TIM_KIEM}?{urlencode(params)}" if params else TRANG_TIM_KIEM


def doc_keywords(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig") as tep:
        data = json.load(tep)
    roles = data.get("Nhom_Nghanh") if isinstance(data, dict) else None
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise ValueError("keyword.json cần Nhom_Nghanh là danh sách chuỗi")
    return list(dict.fromkeys(role.strip() for role in roles if role.strip()))


def doc_skills(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig") as tep:
            data = json.load(tep)
        skills = data.get("Ki_Nang") if isinstance(data, dict) else None
        if isinstance(skills, list):
            return [s.strip() for s in skills if isinstance(s, str) and s.strip()]
    except Exception:
        pass
    return []


def co_ky_nang_phu_hop(row: dict, danh_sach_kn: list[str]) -> bool:
    if not danh_sach_kn:
        return True
    tags = row.get("Ky_Nang") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [tags]
    tags_lower = {t.casefold() for t in tags if isinstance(t, str)}
    for kn in danh_sach_kn:
        if kn.casefold() in tags_lower:
            return True
    van_ban = f"{row.get('Tieu_De', '')} {row.get('Yeu_Cau_Chi_Tiet', '')} {row.get('Mo_Ta_Cong_Viec', '')}"
    for kn in danh_sach_kn:
        mau = rf"\b{re.escape(kn)}\b"
        if re.search(mau, van_ban, re.I):
            return True
    return False


def _url_saramin(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme == "https" and p.netloc.lower() == "saramin.vn"


def _tin(href: object) -> tuple[str, str] | None:
    if not isinstance(href, str) or not href.strip():
        return None
    try:
        url = urljoin(TRANG_CHU, href)
        if not _url_saramin(url):
            return None
    except ValueError:
        return None
    match = DUONG_DAN_TIN.fullmatch(urlsplit(url).path)
    if match:
        return f"{TRANG_CHU}/viec-lam/{match['slug']}", match["id"]
    return None


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    return " ".join(node.get_text(" ", strip=True).split()) or None


def _van_ban_khoi(node: Tag) -> str:
    """Giữ ngắt dòng của đoạn, tiêu đề và danh sách, kể cả HTML trong trình soạn tin."""
    def pieces(parent):
        for child in parent.children:
            if not isinstance(child, Tag):
                if type(child) is NavigableString:
                    yield re.sub(r"[\t\r\n ]+", " ", str(child))
                continue
            if child.name in {"script", "style"}:
                continue
            block = child.name in KHOI_VAN_BAN or child.name == "br"
            if block:
                yield "\n"
            yield from pieces(child)
            if block:
                yield "\n"
            elif child.name in {"td", "th"}:
                yield " "

    return "\n".join(line.strip() for line in "".join(pieces(node)).splitlines() if line.strip())


def _ky_nang(root: Tag) -> list[str]:
    return list(dict.fromkeys(text for node in root.select(THE_KY_NANG) if (text := _text(node))))


def _luong(root: Tag) -> str | None:
    value = _text(root.select_one(O_LUONG))
    return value if value and not KHOA_LUONG.search(value) else None


def luong_goc(html: str) -> str | None:
    return _luong(BeautifulSoup(html, "html.parser"))


def _thong_tin_the(root: Tag) -> dict:
    grid = root.select_one("div.grid.grid-cols-2:has(> span.items-center)")
    if grid is None:
        return {}
    result = {}
    for entry in grid.find_all("span", recursive=False):
        value = _text(entry)
        if not value:
            continue
        if entry.select_one('svg[viewbox="0 0 8 12"]'):
            result["Dia_Diem"] = value
            continue
        if KINH_NGHIEM.search(value):
            result["Kinh_Nghiem"] = value
            continue
        # Thẻ chức danh và ô loại hợp đồng có thể xuất hiện cạnh nhau.
        is_contract = entry.select_one('svg path[d^="M6 0C5.21207"]') is not None
        tokens = [part.strip() for part in value.split(",") if part.strip()]
        modes = [part for part in tokens if HINH_THUC.fullmatch(part)]
        contracts = [part for part in tokens if HOP_DONG.fullmatch(part)
                     and (is_contract or part.casefold() != "thực tập")]
        if modes:
            result["Hinh_Thuc_Lam_Viec"] = ", ".join(modes)
        if contracts:
            result["Loai_Hop_Dong"] = ", ".join(contracts)
    return result


def parse_cards(html: str | BeautifulSoup) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser") if isinstance(html, str) else html
    rows = {}
    for card in soup.select(THE_TIN):
        for link in card.select('a[href*="/viec-lam/"], a[href*="/detail-jobs/"]'):
            job = _tin(link.get("href"))
            title = _text(link)
            if job and title:
                break
        else:
            continue
        url, job_id = job
        if job_id in rows:
            continue
        company = _text(link.find_next_sibling("span")) or _text(card.select_one("[class*='company-name']"))
        posted = card.find(string=lambda text: isinstance(text, str) and bool(NGAY_TUONG_DOI.fullmatch(text.strip())))
        rows[job_id] = {
            "Ma_Tin_Nguon": job_id, "URL_Goc": url, "Tieu_De": title, "Ten_Cong_Ty": company,
            "Ngay_Dang": posted.strip() if posted else None, "Luong": _luong(card),
            "Ky_Nang": _ky_nang(card), **_thong_tin_the(card),
        }
    return list(rows.values())


def _jobposting(soup: BeautifulSoup) -> dict:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or "")
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
            return obj
    return {}


def _muc_mo_ta(soup: BeautifulSoup) -> dict[str, str]:
    # Các mục có số thứ tự trong span và phần nội dung nằm ở các nút cùng cấp.
    def nhan(text: str) -> str:
        label = text.casefold().replace(" và ", " & ")
        return re.sub(r"^\d+\s*[.)-]?\s*", "", label).rstrip(": ")

    for header in soup.select('span.font-semibold, h2, h3, h4'):
        parent = header.parent
        if isinstance(parent, Tag) and nhan(_text(header) or "") in CAC_NHAN and parent.select_one("div.mt-2"):
            box = parent
            break
    else:
        return {}

    result: dict[str, str] = {}
    description: list[str] = []
    column = None
    parts: list[str] = []
    for node in box.find_all(recursive=False):
        heading = _text(node)
        if heading and (next_column := CAC_NHAN.get(nhan(heading))):
            if column and len(parts) > 1:
                result[column] = "\n".join(parts)
            column, parts = next_column, [heading]
            description.append(heading)
        elif value := _van_ban_khoi(node):
            description.append(value)
            if column:
                parts.append(value)
    if column and len(parts) > 1:
        result[column] = "\n".join(parts)
    result.pop("vai_tro", None)
    result["Mo_Ta_Cong_Viec"] = "\n".join(description)
    return result


def _dia_diem_json(job: dict) -> str | None:
    locations = job.get("jobLocation")
    if isinstance(locations, dict):
        locations = [locations]
    if not isinstance(locations, list):
        return None
    values: list[str] = []
    for location in locations:
        address = location.get("address") if isinstance(location, dict) else None
        if isinstance(address, dict):
            value = address.get("addressLocality") or address.get("addressRegion") or address.get("streetAddress")
            if isinstance(value, str) and value.strip() and value not in values:
                values.append(value)
    return " - ".join(values) or None


def parse_detail(html: str, job_id: str | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    job = _jobposting(soup)
    target = job.get("potentialAction")
    if job_id and isinstance(target, dict) and isinstance(target.get("target"), str):
        source = _tin(target["target"])
        if not source or source[1] != job_id:
            return {}

    sections = _muc_mo_ta(soup)
    if not job and not sections:
        return {}
    if not sections and isinstance(job.get("description"), str):
        sections["Mo_Ta_Cong_Viec"] = _van_ban_khoi(BeautifulSoup(job["description"], "html.parser"))
    if not sections.get("Quyen_Loi") and isinstance(job.get("jobBenefits"), str):
        benefit = _van_ban_khoi(BeautifulSoup(job["jobBenefits"], "html.parser"))
        if benefit:
            sections["Quyen_Loi"] = benefit

    title_link = soup.select_one('a[href^="/detail-jobs/"].line-clamp-2, h1')
    header = title_link.find_parent(class_="text-card-foreground") if title_link else None
    company = job.get("hiringOrganization")
    job_data = next((data for data in du_lieu_nhung_saramin(soup, "jobData")
                     if isinstance(data, dict) and (job_id is None or str(data.get("id")) == job_id)), {})
    skills = job.get("skills")
    employment = job.get("employmentType")
    if isinstance(employment, str):
        employment = [employment]
    result = {
        "Tieu_De": _text(title_link) or job.get("title"),
        "Ten_Cong_Ty": company.get("name") if isinstance(company, dict) else None,
        "Ngay_Dang": job.get("datePosted"),
        "Ky_Nang": job_data.get("skills_arr") or (
            [term.strip() for term in skills.split(",") if term.strip()] if isinstance(skills, str) else []
        ),
        **sections,
    }
    if header:
        result.update(_thong_tin_the(header))
        result["Luong"] = _luong(header)
        if not result["Ky_Nang"]:
            result["Ky_Nang"] = _ky_nang(header)
    for column, field in (("Kinh_Nghiem", "experiences_str"), ("Hinh_Thuc_Lam_Viec", "job_types_str"),
                          ("Loai_Hop_Dong", "contract_types_str")):
        if isinstance(value := job_data.get(field), str) and value.strip():
            result[column] = value.strip()
    if not result.get("Kinh_Nghiem"):
        van_ban_tim = f"{sections.get('Yeu_Cau_Chi_Tiet') or ''} {sections.get('Mo_Ta_Cong_Viec') or ''}"
        match_kn = KINH_NGHIEM.search(van_ban_tim)
        if match_kn:
            result["Kinh_Nghiem"] = match_kn.group(0).strip()
    if not result.get("Dia_Diem"):
        addresses = job_data.get("addresses")
        location = addresses.get("sort_addresses") if isinstance(addresses, dict) else None
        result["Dia_Diem"] = (location.strip() if isinstance(location, str) else None) or _dia_diem_json(job)
    if not result.get("Hinh_Thuc_Lam_Viec") and isinstance(job.get("jobLocationType"), str):
        result["Hinh_Thuc_Lam_Viec"] = job["jobLocationType"]
    if not result.get("Loai_Hop_Dong") and isinstance(employment, list):
        result["Loai_Hop_Dong"] = ", ".join(value for value in employment
                                            if isinstance(value, str) and value != "OTHER") or None
    return result


def tai_trang(session, url, rp=None, *, khoang_nghi=(0, 0)):
    """Tải bằng requests. Kiểm tra quyền trước mỗi lần theo chuyển hướng."""
    for _ in range(5):
        if not _url_saramin(url) or (rp is not None and not duoc_phep(rp, TRANG_CHU, url, TEN_BOT)):
            print(f"Saramin từ chối đường dẫn theo phạm vi hoặc robots.txt: {url}")
            return None, "bi_cam"
        nghi_ngau_nhien(khoang_nghi)
        try:
            response = session.get(url, timeout=20, allow_redirects=False)
        except (requests.ConnectionError, requests.Timeout):
            return None, "loi_tam_thoi"

        status = response.status_code
        if status in (401, 403, 429) or la_thu_thach_cloudflare(response.headers):
            print(f"Saramin trả HTTP {status} hoặc yêu cầu xác minh tại {url}")
            return None, "bi_chan"
        if status in (404, 410):
            return None, "khong_ton_tai"
        if status >= 500:
            return None, "loi_tam_thoi"
        if response.is_redirect and rp is not None:
            url = urljoin(url, response.headers["Location"])
            continue
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if status != 200:
            return None, "bi_cam"
        if rp is None and content_type == "text/plain":
            return response.content, "ok"
        if rp is not None and content_type == "text/html":
            if bi_thu_thach(response.text):
                return None, "bi_chan"
            return response.text, "ok"
        return None, "bi_cam"
    return None, "loi_tam_thoi"


def _tao_dong(schema, card, detail, search_url, keyword, timestamp):
    row = dict.fromkeys(schema["required"])
    for source in (card, detail):
        row.update({field: value for field, value in source.items() if field in row and value})
    row.update(Web="saramin", URL_Tim_Kiem=search_url, Tu_Khoa_Tim_Kiem=keyword or None,
               Timestamp=timestamp)
    if not row.get("Hinh_Thuc_Lam_Viec"):
        row["Hinh_Thuc_Lam_Viec"] = "Offline"
    if not row.get("Loai_Hop_Dong"):
        row["Loai_Hop_Dong"] = "Full-time"
    return row


def _bo_sung_luong(args, rp, rows, stats, cdp_url: str | None = None):
    pending = []
    for row in rows:
        salary = row.get("Luong")
        if isinstance(salary, str) and salary and not KHOA_LUONG.search(salary):
            continue
        job = _tin(row.get("URL_Goc"))
        if job:
            pending.append((row, job[0]))
    if args.salary_limit:
        pending = pending[:args.salary_limit]
    if not pending:
        print("CSV không có tin Saramin cần bổ sung lương.")
        return 0

    def tai(page, url):
        if not duoc_phep(rp, TRANG_CHU, url, TEN_BOT):
            print(f"robots.txt không cho phép: {url}")
            return None, "bi_cam"
        return tai_thu_lai(
            lambda link: tai_trang_luong_saramin(page, link, O_LUONG, KHOA_LUONG.pattern),
            url, stats, khoang_nghi=(args.delay_min, args.delay_max), so_lan_thu=1,
        )

    def luu():
        xuat_csv(args.out, rows, mot_dong_vat_ly=True)

    locked = 0
    try:
        with phien_luong_saramin(TRANG_DANG_NHAP, rp, TEN_BOT, cdp_url=cdp_url) as page:
            for row, url in pending:
                html, code = tai(page, url)
                if code in (*DUNG, "bi_cam"):
                    return 2
                if code != "ok" or html is None:
                    continue
                value = luong_goc(html)
                if value:
                    row["Luong"] = value
                    stats["cap_nhat_luong"] += 1
                    locked = 0
                    if stats["cap_nhat_luong"] % args.checkpoint == 0:
                        luu()
                elif html:
                    locked += 1
                    if locked >= 3:
                        print("Dừng bổ sung lương vì nhiều trang liên tiếp yêu cầu đăng nhập.")
                        return 2
    except RuntimeError as error:
        print(f"Dừng bổ sung lương: {error}")
        return 2
    finally:
        if stats["cap_nhat_luong"]:
            luu()
    return 0


def _cao(args, rp, tai, keywords, rows, stats, skills_list: list[str] | None = None):
    schema = doc_schema()
    required = [field for field in schema["required"] if "null" not in schema["properties"][field]["type"]]
    saved = {job[1] for row in rows if row.get("URL_Goc") and (job := _tin(row["URL_Goc"]))}
    seen = set(saved)
    for keyword in keywords:
        if len(rows) >= args.target:
            break
        print(f"Tìm kiếm Saramin: {keyword or 'tất cả việc làm'}", flush=True)
        url = tao_url_tim_kiem(keyword)
        for search_url, cards, code in duyet_trang_saramin(url, tai, parse_cards, args.max_pages):
            if code in (*DUNG, "bi_cam"):
                return 2
            if code != "ok":
                if code != "khong_ton_tai":
                    stats["loi_tai_danh_sach"] += 1
                break
            print(f"  {len(cards)} thẻ từ {search_url}", flush=True)
            for card in cards:
                job_id = card["Ma_Tin_Nguon"]
                if job_id in seen:
                    continue
                timestamp = danh_dau_bat_dau()
                html, code = tai(card["URL_Goc"])
                if code in DUNG:
                    return 2
                if code != "ok" or not isinstance(html, str):
                    stats["loi_tai_chi_tiet"] += 1
                    continue
                detail = parse_detail(html, job_id)
                row = _tao_dong(schema, card, detail, search_url, keyword, timestamp)
                missing = [field for field in required if not row[field]]
                seen.add(job_id)
                if missing:
                    stats["thieu_cot"] += 1
                    print(f"  Bỏ tin {job_id} thiếu cột {', '.join(missing)}", flush=True)
                    continue
                if args.filter_skills and skills_list and not co_ky_nang_phu_hop(row, skills_list):
                    stats["ngoai_ky_nang"] += 1
                    print(f"  Bỏ qua {job_id} ({row.get('Tieu_De')}): Không chứa kỹ năng Data nào trong keyword.json", flush=True)
                    continue
                rows.append(row)
                stats["tin_moi"] += 1
                if stats["tin_moi"] % args.checkpoint == 0:
                    xuat_csv(args.out, rows, mot_dong_vat_ly=True)
                if len(rows) >= args.target:
                    return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cào tin Saramin bằng HTTP và xuất CSV UTF-8")
    parser.add_argument("--out", type=Path, default=OUT_MAC_DINH)
    parser.add_argument("--keywords", type=Path, default=KEYWORDS_MAC_DINH, help="Tệp keyword.json")
    search = parser.add_mutually_exclusive_group()
    search.add_argument("--keyword", action="append", help="Chỉ cào từ khóa này, có thể lặp lại")
    search.add_argument("--all-jobs", action="store_true", help="Duyệt danh sách không lọc từ khóa")
    parser.add_argument("--max-pages", type=int, default=30, help="Số lô tối đa cho mỗi từ khóa")
    parser.add_argument("--target", type=int, default=1500, help="Tổng số tin tối đa trong CSV")
    parser.add_argument("--checkpoint", type=int, default=10)
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--login", action="store_true", help="Đăng nhập Chrome thủ công để bổ sung lương")
    parser.add_argument("--cdp", action="store_true", help="Kết nối tới Chrome thật đang mở qua cổng Remote Debugging (port 9222)")
    parser.add_argument("--cdp-url", type=str, default="http://localhost:9222", help="URL CDP (mặc định: http://localhost:9222)")
    parser.add_argument("--filter-skills", action="store_true", help="Chỉ lưu tin có chứa ít nhất 1 kỹ năng trong keyword.json (loại tin ngoài ngành)")
    parser.add_argument("--salary-only", action="store_true", help="Chỉ bổ sung lương cho các tin đã có trong CSV, không cào tin mới")
    parser.add_argument("--salary-limit", type=int, default=20, help="Số tin bổ sung lương, 0 để bỏ giới hạn")
    args = parser.parse_args(argv)
    if (min(args.max_pages, args.target, args.checkpoint) < 1 or args.salary_limit < 0
            or not all(map(math.isfinite, (args.delay_min, args.delay_max)))
            or not 2 <= args.delay_min <= args.delay_max):
        parser.error("Kiểm tra max-pages, target, checkpoint, salary-limit và delay (tối thiểu 2 giây)")

    try:
        keywords = ([""] if args.all_jobs else
                    list(dict.fromkeys(k.strip() for k in args.keyword if k.strip())) if args.keyword
                    else doc_keywords(args.keywords))
        skills_list = doc_skills(args.keywords) if args.filter_skills else []
        rows = doc_csv(args.out)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if not keywords:
        parser.error("Danh sách từ khóa rỗng")

    stats = Counter()
    code = 0
    try:
        with requests.Session() as session:
            session.headers.update({"User-Agent": TEN_BOT, "Accept-Language": "vi-VN,vi;q=0.9"})
            rp, reason = kiem_thu_robot(
                TRANG_CHU, [tao_url_tim_kiem(k) for k in keywords], TEN_BOT,
                tai_robots=lambda url: tai_trang(session, url),
            )
            if rp is None:
                print(f"Dừng cào Saramin: {reason}")
                return 2
            minimum = max(args.delay_min, rp.crawl_delay(TEN_BOT) or 0)
            rate = rp.request_rate(TEN_BOT)
            if rate and rate.requests:
                minimum = max(minimum, rate.seconds / rate.requests)
            args.delay_min = minimum
            args.delay_max = max(minimum, args.delay_max)
            pause = (args.delay_min, args.delay_max)

            def tai(url):
                return tai_thu_lai(lambda link: tai_trang(session, link, rp, khoang_nghi=pause),
                                   url, stats, khoang_nghi=(0, 0))

            if not args.salary_only:
                code = _cao(args, rp, tai, keywords, rows, stats, skills_list=skills_list)
        if (args.login or args.cdp) and code == 0:
            cdp_endpoint = args.cdp_url if args.cdp else None
            code = _bo_sung_luong(args, rp, rows, stats, cdp_url=cdp_endpoint)
    except KeyboardInterrupt:
        code = 130
    finally:
        if stats["tin_moi"]:
            xuat_csv(args.out, rows, mot_dong_vat_ly=True)
        print(f"Saramin: {stats['tin_moi']} tin mới, {stats['cap_nhat_luong']} lương bổ sung, {len(rows)} tin tổng cộng.", flush=True)
        if stats:
            print(f"Thống kê {dict(stats)}. CSV {args.out.resolve()}", flush=True)

    return code or (2 if any(stats[key] for key in ("loi_tai_danh_sach", "loi_tai_chi_tiet", "thieu_cot")) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
