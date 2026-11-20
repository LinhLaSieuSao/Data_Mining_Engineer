"""Crawler CareerViet – thu thập tin tuyển dụng CNTT từ careerviet.vn.

Tìm kiếm theo từ khóa (keyword.json), phân trang tự động, bóc dữ liệu
trang chi tiết hoàn toàn từ HTML qua Playwright, lưu CSV tuân thủ schema.json.
Chỉ kiểm tra robots.txt theo đúng yêu cầu đề bài.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

_THU_MUC_GOC = Path(__file__).resolve().parent.parent
if str(_THU_MUC_GOC) not in sys.path:
    sys.path.insert(0, str(_THU_MUC_GOC))

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Response as PwResponse

from crawlers import (
    DUNG,
    doc_schema,
    kiem_thu_robot,
    duoc_phep,
    doc_csv,
    khoa_url,
    danh_dau_bat_dau,
    nghi_ngau_nhien,
    tai_thu_lai,
    xuat_csv,
)

# ---------------------------------------------------------------------------
# HẰNG SỐ
# ---------------------------------------------------------------------------
TRANG_CHU = "https://careerviet.vn"
TEN_BOT = "DataMining-Crawler/1.0"
DUONG_DAN_MAC_DINH = "data/raw/careerviet.csv"
DUONG_DAN_TU_KHOA = "keyword.json"

# ---------------------------------------------------------------------------
# SCHEMA HELPERS
# ---------------------------------------------------------------------------

def _lay_cac_cot() -> list[str]:
    """Lấy thứ tự cột từ schema (required)."""
    return doc_schema()["required"]


def _lay_cot_bat_buoc() -> set[str]:
    """Các cột bắt buộc (type không chứa 'null')."""
    schema = doc_schema()
    return {
        cot for cot in schema["required"]
        if "null" not in schema["properties"][cot]["type"]
    }

# ---------------------------------------------------------------------------
# TỪ KHÓA: ĐỌC & KHỚP
# ---------------------------------------------------------------------------

def _doc_tu_khoa(duong_dan: str) -> tuple[list[str], list[str]]:
    """Đọc keyword.json, trả về (nhom_nghanh, ki_nang)."""
    with open(duong_dan, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("Nhom_Nghanh", []), data.get("Ki_Nang", [])


def _xay_regex_tu_khoa(tu_khoa: str) -> re.Pattern:
    """Xây regex ranh giới từ cho một từ khóa."""
    escaped = re.escape(tu_khoa)
    return re.compile(
        r"(?<![a-zA-Z0-9_\-])" + escaped + r"(?![a-zA-Z0-9_\-])",
        re.IGNORECASE,
    )


def _khop_tu_khoa(
    van_ban: str,
    nhom_nghanh: list[str],
    ki_nang: list[str],
    cache_regex: dict[str, re.Pattern],
) -> tuple[list[str], list[str]]:
    """Trả danh sách (vi_tri_khop, ky_nang_khop) tìm thấy trong văn bản."""
    vi_tri_khop: list[str] = []
    ky_nang_khop: list[str] = []
    for tk in nhom_nghanh:
        if tk in cache_regex and cache_regex[tk].search(van_ban):
            vi_tri_khop.append(tk)
    for tk in ki_nang:
        if tk in cache_regex and cache_regex[tk].search(van_ban):
            ky_nang_khop.append(tk)
    return vi_tri_khop, ky_nang_khop

# ---------------------------------------------------------------------------
# URL TÌM KIẾM
# ---------------------------------------------------------------------------

def _bo_dau(text: str) -> str:
    """Chuyển Unicode có dấu thành ASCII không dấu."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def tao_slug(tu_khoa: str) -> str:
    """Tạo slug chuẩn SEO từ từ khóa tìm kiếm."""
    slug = _bo_dau(tu_khoa).lower().strip()
    slug = re.sub(r"[\s/_+]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def tao_url_tim_kiem(tu_khoa: str, trang: int) -> str:
    """Tạo URL tìm kiếm CareerViet cho từ khóa và số trang.

    Mẫu:
      Trang 1: https://careerviet.vn/viec-lam/{slug}-k-vi.html
      Trang n: https://careerviet.vn/viec-lam/{slug}-k-trang-{n}-vi.html
    """
    slug = tao_slug(tu_khoa)
    if trang <= 1:
        return f"{TRANG_CHU}/viec-lam/{slug}-k-vi.html"
    return f"{TRANG_CHU}/viec-lam/{slug}-k-trang-{trang}-vi.html"

# ---------------------------------------------------------------------------
# CHUẨN HÓA URL TIN
# ---------------------------------------------------------------------------

def _chuan_hoa_url_tin(url_goc: str) -> str:
    """Chuẩn hóa URL tin: bỏ query tracking, giữ nguyên scheme, host và path."""
    parts = urlsplit(url_goc)
    base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    if not base.startswith("http"):
        base = TRANG_CHU + parts.path
    return base

# ---------------------------------------------------------------------------
# BÓC TÁCH DANH SÁCH THẺ TIN (LISTING CARDS)
# ---------------------------------------------------------------------------

def parse_cards(html: str) -> list[dict]:
    """Bóc tách các thẻ tin từ trang danh sách kết quả tìm kiếm CareerViet."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.job-item")
    if not cards:
        cards = soup.select("div[class*='job-item']")

    ket_qua: list[dict] = []
    seen_urls: set[str] = set()

    for card in cards:
        title_el = card.select_one(
            "a.job_link, a.job-title, h2 a, h3 a, a[href*='/vi/tim-viec-lam/']"
        )
        if not title_el:
            continue
        href = title_el.get("href", "").strip()
        if not href or href == "#" or href.startswith("javascript"):
            continue
        if not href.startswith("http"):
            url = urljoin(TRANG_CHU, href)
        else:
            url = href

        url = _chuan_hoa_url_tin(url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Trích xuất mã tin từ URL hoặc thuộc tính thẻ
        ma_tin = None
        m = re.search(r"\.([0-9A-Za-z]+)\.html$", urlsplit(url).path)
        if m:
            ma_tin = m.group(1)
        if not ma_tin and card.get("id"):
            m2 = re.search(r"job-item-([0-9A-Za-z]+)", card.get("id"))
            if m2:
                ma_tin = m2.group(1)

        company_el = card.select_one(
            "a.company-name, [class*='company'], a[href*='/vi/nha-tuyen-dung/']"
        )
        salary_el = card.select_one("div.salary, span.salary, [class*='salary']")
        location_el = card.select_one("div.location, [class*='location']")
        posted_el = card.select_one("div.time, [class*='time'], [class*='date']")

        ket_qua.append({
            "url": url,
            "ma_tin": ma_tin,
            "tieu_de": title_el.get_text(strip=True) if title_el else None,
            "cong_ty": company_el.get_text(strip=True) if company_el else None,
            "luong": salary_el.get_text(strip=True) if salary_el else None,
            "dia_diem": location_el.get_text(strip=True) if location_el else None,
            "ngay_dang": posted_el.get_text(strip=True) if posted_el else None,
            "listing_text": card.get_text("\n", strip=True) or None,
        })

    return ket_qua

# ---------------------------------------------------------------------------
# BÓC TÁCH TRANG CHI TIẾT
# ---------------------------------------------------------------------------

def _lay_text_or_none(soup: BeautifulSoup, selectors: list[str]) -> Optional[str]:
    """Thử lấy text từ nhiều selector, trả None nếu không có."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text("\n", strip=True)
            if text:
                return text
    return None


def parse_chi_tiet(html: str) -> dict:
    """Bóc tách thông tin chi tiết từ HTML trang tuyển dụng CareerViet."""
    soup = BeautifulSoup(html, "lxml")
    ket_qua: dict = {}

    # 1. Tiêu đề tin
    ket_qua["tieu_de"] = _lay_text_or_none(soup, [
        "h1.title", "h1.job-title", "div.job-title h1", "h1",
    ])

    # 2. Tên công ty
    ket_qua["cong_ty"] = _lay_text_or_none(soup, [
        "a.job-company-name", "a.employer", "a[href*='/vi/nha-tuyen-dung/']",
        "a.company-name", "div.company-name a", "div.company-name",
    ])

    # 3. Lương
    ket_qua["luong"] = _lay_text_or_none(soup, [
        "span.meta-salary", "div.salary", "span.salary",
    ])

    # 4. Địa điểm
    ket_qua["dia_diem"] = _lay_text_or_none(soup, [
        "span.meta-location-text", "span.meta-location", "div.location",
    ])

    # 5. Các thông tin tóm tắt từ khung Overview (Kinh nghiệm, Hình thức, Cấp bậc, Ngày cập nhật)
    overview_items = soup.select("div.job-overview-item")
    for item in overview_items:
        label_el = item.select_one("span.overview-label")
        val_el = item.select_one("strong.overview-value")
        if not label_el or not val_el:
            continue
        label = label_el.get_text(" ", strip=True).lower()
        val = val_el.get_text(" ", strip=True)
        if not val:
            continue

        if "kinh nghiệm" in label or "kinh nghiem" in label:
            ket_qua["kinh_nghiem"] = val
        elif "hình thức" in label or "hinh thuc" in label:
            ket_qua["hinh_thuc"] = val
        elif "cấp bậc" in label or "cap bac" in label:
            ket_qua["cap_bac"] = val
        elif any(w in label for w in ["ngày cập nhật", "ngay cap nhat", "ngày đăng"]):
            ket_qua["ngay_dang"] = val
        elif "hết hạn" in label:
            ket_qua["han_nop"] = val

    # Fallback địa điểm từ detail-row nếu khung top chưa có
    if not ket_qua.get("dia_diem"):
        for row in soup.select("div.detail-row"):
            h = row.select_one("h2, h3, h4")
            if h and "địa điểm" in h.get_text().lower():
                val = row.get_text(" ", strip=True).replace(h.get_text(), "").strip()
                if val:
                    ket_qua["dia_diem"] = val
                    break

    # 6. Mô tả công việc (toàn văn khối mô tả, giữ nguyên thứ tự và ký tự xuống dòng)
    desc_container = soup.select_one(
        "div.job-detail-content, section.job-detail-content, div.job-desc"
    )
    if desc_container:
        ket_qua["mo_ta"] = desc_container.get_text("\n", strip=True)
    else:
        rows_text = [
            r.get_text("\n", strip=True) for r in soup.select("div.detail-row")
            if r.get_text("\n", strip=True)
        ]
        ket_qua["mo_ta"] = "\n\n".join(rows_text) if rows_text else None

    # 7. Phân tách riêng: Yêu cầu chi tiết & Quyền lợi/Phúc lợi
    ket_qua["yeu_cau"] = None
    ket_qua["quyen_loi"] = None

    for row in soup.select("div.detail-row"):
        heading = row.select_one(
            "h2.detail-title, h3.detail-title, h4.detail-title, h2, h3"
        )
        if not heading:
            continue
        h_text = heading.get_text(strip=True).lower()
        content = row.get_text("\n", strip=True)
        if any(w in h_text for w in ["yêu cầu", "yeu cau", "điều kiện"]):
            ket_qua["yeu_cau"] = content
        elif any(w in h_text for w in ["phúc lợi", "phuc loi", "quyền lợi", "quyen loi", "chế độ"]):
            ket_qua["quyen_loi"] = content

    # 8. Kỹ năng / Thẻ kỹ năng
    tags = soup.select(
        "div.tag-list a, a.tag, div.job-tags a, [class*='skill'] a, div.tags a"
    )
    if tags:
        ket_qua["ky_nang"] = [
            t.get_text(strip=True) for t in tags if t.get_text(strip=True)
        ]
    else:
        ket_qua["ky_nang"] = None

    return ket_qua

# ---------------------------------------------------------------------------
# XÂY DỰNG DÒNG DỮ LIỆU THÔ THEO SCHEMA
# ---------------------------------------------------------------------------

def _xay_dong_tho(
    card: dict,
    chi_tiet: dict,
    url_tin: str,
    url_tim_kiem: str,
    tu_khoa_tim: str,
    thoi_diem: str,
    vi_tri_khop: list[str],
    ky_nang_khop: list[str],
) -> dict:
    """Dựng một dòng dữ liệu thô đúng thứ tự cột schema.json."""
    cac_cot = _lay_cac_cot()
    # Kỹ năng ưu tiên thẻ hiển thị trên web, nếu không có thì gán kỹ năng khớp từ keyword.json
    ky_nang_gia_tri = chi_tiet.get("ky_nang") or (ky_nang_khop if ky_nang_khop else None)

    anh_xa: dict[str, object] = {
        "Web": "careerviet",
        "Ma_Tin_Nguon": chi_tiet.get("ma_tin") or card.get("ma_tin"),
        "URL_Goc": url_tin,
        "URL_Tim_Kiem": url_tim_kiem,
        "Tu_Khoa_Tim_Kiem": tu_khoa_tim,
        "Timestamp": thoi_diem,
        "Tieu_De": chi_tiet.get("tieu_de") or card.get("tieu_de"),
        "Ten_Cong_Ty": chi_tiet.get("cong_ty") or card.get("cong_ty"),
        "Dia_Diem": chi_tiet.get("dia_diem") or card.get("dia_diem"),
        "Luong": chi_tiet.get("luong") or card.get("luong"),
        "Kinh_Nghiem": chi_tiet.get("kinh_nghiem") or card.get("kinh_nghiem"),
        "Hinh_Thuc_Lam_Viec": chi_tiet.get("hinh_thuc"),
        "Loai_Hop_Dong": chi_tiet.get("loai_hop_dong"),
        "Ngay_Dang": chi_tiet.get("ngay_dang") or card.get("ngay_dang"),
        "Mo_Ta_Cong_Viec": chi_tiet.get("mo_ta") or card.get("listing_text"),
        "Yeu_Cau_Chi_Tiet": chi_tiet.get("yeu_cau"),
        "Quyen_Loi": chi_tiet.get("quyen_loi"),
        "Ky_Nang": ky_nang_gia_tri,
    }

    dong: dict = {}
    for cot in cac_cot:
        dong[cot] = anh_xa.get(cot)
    return dong

# ---------------------------------------------------------------------------
# HÀM TẢI TRANG (PLAYWRIGHT CLOSURES)
# ---------------------------------------------------------------------------

def _phat_hien_chan(page: Page) -> bool:
    """Kiểm tra trang có dấu hiệu bị chặn / captcha không."""
    try:
        title = (page.title() or "").lower()
        body_text = page.inner_text("body")[:2000].lower()
    except Exception:
        return False
    keywords = [
        "just a moment", "verify you are human", "captcha",
        "access denied", "are you a robot", "blocked"
    ]
    for kw in keywords:
        if kw in title or kw in body_text:
            return True
    return False


def _anh_xa_trang_thai(response: Optional[PwResponse], page: Page) -> str:
    """Chuyển HTTP status và nội dung thành mã trạng thái nội bộ."""
    if response is None:
        return "loi_tam_thoi"
    status = response.status
    if status in (404, 410):
        return "khong_ton_tai"
    if status == 403:
        return "bi_cam"
    if status == 429:
        return "bi_chan"
    if 500 <= status < 600:
        return "loi_tam_thoi"
    if status == 200:
        if _phat_hien_chan(page):
            return "bi_chan"
        return "ok"
    if 400 <= status < 500:
        return "khong_ton_tai"
    return "loi_tam_thoi"


def _tao_ham_tai_danh_sach(page: Page, khoang_nghi: tuple[float, float]) -> Callable:
    """Tải trang danh sách kết quả tìm kiếm CareerViet."""
    def ham_tai_danh_sach(url: str) -> tuple[Optional[str], str]:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            return None, "loi_tam_thoi"

        ma = _anh_xa_trang_thai(response, page)
        if ma != "ok":
            return None, ma

        # Chờ container danh sách thẻ tin
        try:
            page.wait_for_selector(
                "div.job-item, div[class*='job-item']",
                timeout=15_000,
            )
        except Exception:
            pass

        # Cuộn trang nhẹ để kích hoạt nội dung
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            nghi_ngau_nhien((1.0, 2.0))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass

        return page.content(), "ok"

    return ham_tai_danh_sach


def _tao_ham_tai_chi_tiet(page: Page) -> Callable:
    """Tải trang chi tiết tin tuyển dụng CareerViet."""
    def ham_tai_chi_tiet(url: str) -> tuple[Optional[str], str]:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception:
            return None, "loi_tam_thoi"

        ma = _anh_xa_trang_thai(response, page)
        if ma != "ok":
            return None, ma

        # Chờ các khối thông tin chính
        try:
            page.wait_for_selector(
                "h1, div.job-detail-content, section.job-detail-content, div.job-desc, div.detail-row",
                timeout=15_000,
            )
        except Exception:
            pass

        return page.content(), "ok"

    return ham_tai_chi_tiet

# ---------------------------------------------------------------------------
# MAIN CRAWLER PIPELINE
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Hàm chạy chính của crawler CareerViet."""
    parser = argparse.ArgumentParser(
        description="Crawler CareerViet – thu thập tin tuyển dụng CNTT theo schema dự án"
    )
    parser.add_argument(
        "--out", type=str, default=DUONG_DAN_MAC_DINH,
        help="Đường dẫn file CSV đầu ra (mặc định: data/raw/careerviet.csv)",
    )
    parser.add_argument(
        "--keywords", type=str, default=DUONG_DAN_TU_KHOA,
        help="Đường dẫn file keyword.json",
    )
    parser.add_argument(
        "--max-pages", type=int, default=30,
        help="Số trang tối đa cho mỗi từ khóa",
    )
    parser.add_argument(
        "--target", type=int, default=1500,
        help="Số lượng tin mục tiêu cần thu thập",
    )
    parser.add_argument(
        "--checkpoint", type=int, default=10,
        help="Lưu checkpoint CSV sau mỗi N tin mới",
    )
    parser.add_argument(
        "--delay-min", type=float, default=2.0,
        help="Thời gian nghỉ tối thiểu giữa các request (giây, >= 2.0)",
    )
    parser.add_argument(
        "--delay-max", type=float, default=4.0,
        help="Thời gian nghỉ tối đa giữa các request (giây)",
    )
    parser.add_argument(
        "--headless", action="store_true", default=True,
        help="Chạy trình duyệt ẩn (mặc định bật)",
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Hiển thị cửa sổ trình duyệt",
    )
    parser.add_argument(
        "--login", action="store_true",
        help="Mở trình duyệt để tương tác thủ công nếu cần trước khi cào",
    )
    args = parser.parse_args(argv)

    # Đảm bảo delay tuân thủ đề bài (tối thiểu 2 giây)
    if args.delay_min < 2.0:
        print("CẢNH BÁO: delay-min tối thiểu là 2.0 giây theo đề bài. Tự động điều chỉnh lên 2.0s.")
        args.delay_min = 2.0
    if args.delay_max < args.delay_min:
        args.delay_max = args.delay_min + 1.0
    khoang_nghi: tuple[float, float] = (args.delay_min, args.delay_max)

    duong_dan_ra = args.out

    # 1. Đọc từ khóa
    duong_dan_kw = Path(args.keywords)
    if not duong_dan_kw.is_absolute():
        duong_dan_kw = Path(__file__).resolve().parent.parent / args.keywords
    nhom_nghanh, ki_nang = _doc_tu_khoa(str(duong_dan_kw))
    tu_khoa_tim_kiem = nhom_nghanh
    if not tu_khoa_tim_kiem:
        print("LỖI: keyword.json không chứa nhóm ngành tìm kiếm.")
        return 1
    print(f"Đã đọc {len(nhom_nghanh)} nhóm ngành từ {duong_dan_kw}: {nhom_nghanh}")

    # Tạo regex cache để quét kỹ năng trong mô tả
    cache_regex: dict[str, re.Pattern] = {}
    for tk in dict.fromkeys(nhom_nghanh + ki_nang):
        cache_regex[tk] = _xay_regex_tu_khoa(tk)

    # 2. Kiểm tra robots.txt
    url_mau = [tao_url_tim_kiem(tu_khoa_tim_kiem[0], 1)]
    print(f"Đang kiểm tra robots.txt tại {TRANG_CHU}...")
    rp, ly_do = kiem_thu_robot(TRANG_CHU, url_mau, TEN_BOT)
    if rp is None:
        print(f"DỪNG: robots.txt không cho phép truy cập: {ly_do}")
        return 2
    print("Kiểm tra robots.txt thành công! Tiến hành thu thập dữ liệu...")

    # 3. Đọc CSV cũ (Resume mechanism)
    cac_dong: list[dict] = doc_csv(duong_dan_ra)
    da_luu: set[tuple] = {khoa_url(d["URL_Goc"]) for d in cac_dong if d.get("URL_Goc")}
    print(f"Đã nạp {len(cac_dong)} tin từ trước. URL đã lưu: {len(da_luu)}.")

    cot_bat_buoc = _lay_cot_bat_buoc()
    thong_ke: collections.Counter = collections.Counter()
    for k in ("ok", "khong_ton_tai", "bi_cam", "bi_chan", "ngat_mach", "that_bai", "loi_lien_tiep"):
        thong_ke.setdefault(k, 0)

    so_tin_moi = 0
    tong_moi_phien = 0
    dung_toan_bo = False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=args.headless and not args.login,
            )
            context = browser.new_context(
                user_agent=TEN_BOT,
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            if args.login:
                url_mo_dau = tao_url_tim_kiem(tu_khoa_tim_kiem[0], 1)
                print(f"Đang mở {url_mo_dau} để tương tác...")
                page.goto(url_mo_dau, wait_until="domcontentloaded", timeout=60_000)
                input("Sau khi chuẩn bị xong trên trình duyệt, nhấn Enter để tiếp tục cào...")

            ham_tai_danh_sach = _tao_ham_tai_danh_sach(page, khoang_nghi)
            ham_tai_chi_tiet = _tao_ham_tai_chi_tiet(page)

            for tu_khoa in tu_khoa_tim_kiem:
                if dung_toan_bo or len(cac_dong) >= args.target:
                    break

                print(f"\n==========================================")
                print(f"BẮT ĐẦU TỪ KHÓA: {tu_khoa}")
                print(f"==========================================")
                trang_trung_lien_tiep = 0

                for n in range(1, args.max_pages + 1):
                    if dung_toan_bo or len(cac_dong) >= args.target:
                        break

                    url_trang = tao_url_tim_kiem(tu_khoa, n)
                    if not duoc_phep(rp, TRANG_CHU, url_trang, TEN_BOT):
                        print(f"  robots.txt cấm trang tìm kiếm: {url_trang}")
                        break

                    noi_dung, ma = tai_thu_lai(
                        ham_tai_danh_sach, url_trang, thong_ke,
                        khoang_nghi=khoang_nghi,
                    )
                    if ma in DUNG:
                        print(f"  DỪNG HỆ THỐNG ({ma}): {url_trang}")
                        dung_toan_bo = True
                        break
                    if ma == "khong_ton_tai":
                        print(f"  Hết trang cho từ khóa '{tu_khoa}' tại trang {n}")
                        break
                    if ma != "ok" or not noi_dung:
                        print(f"  Bỏ qua trang {n} (mã: {ma})")
                        continue

                    cards = parse_cards(noi_dung)
                    if not cards:
                        print(f"  Trang {n}: Không tìm thấy thẻ tin nào. Kết thúc từ khóa '{tu_khoa}'.")
                        break

                    so_tin_moi_trang = 0
                    for card in cards:
                        if dung_toan_bo or len(cac_dong) >= args.target:
                            break

                        url_tin = card["url"]
                        key = khoa_url(url_tin)
                        if key in da_luu:
                            continue

                        if not duoc_phep(rp, TRANG_CHU, url_tin, TEN_BOT):
                            continue

                        thoi_diem = danh_dau_bat_dau()

                        # Tải trang chi tiết hoàn toàn từ HTML
                        html_chi_tiet, ma_ct = tai_thu_lai(
                            ham_tai_chi_tiet, url_tin, thong_ke,
                            khoang_nghi=khoang_nghi,
                        )
                        if ma_ct in DUNG:
                            print(f"  DỪNG ({ma_ct}) khi tải chi tiết: {url_tin}")
                            dung_toan_bo = True
                            break

                        chi_tiet = {}
                        if ma_ct == "ok" and html_chi_tiet:
                            chi_tiet = parse_chi_tiet(html_chi_tiet)

                        # Khớp kỹ năng từ toàn văn nội dung
                        van_ban_khop = " ".join(filter(None, [
                            chi_tiet.get("tieu_de"),
                            card.get("tieu_de"),
                            chi_tiet.get("mo_ta"),
                            chi_tiet.get("yeu_cau"),
                            card.get("listing_text"),
                        ]))
                        vi_tri_khop, ky_nang_khop = _khop_tu_khoa(
                            van_ban_khop, nhom_nghanh, ki_nang, cache_regex,
                        )

                        dong = _xay_dong_tho(
                            card=card,
                            chi_tiet=chi_tiet,
                            url_tin=url_tin,
                            url_tim_kiem=url_trang,
                            tu_khoa_tim=tu_khoa,
                            thoi_diem=thoi_diem,
                            vi_tri_khop=vi_tri_khop,
                            ky_nang_khop=ky_nang_khop,
                        )

                        # Kiểm tra các cột bắt buộc
                        thieu = [
                            c for c in cot_bat_buoc
                            if dong.get(c) is None or (isinstance(dong[c], str) and not dong[c].strip())
                        ]
                        if thieu:
                            print(f"  Bỏ qua tin thiếu cột bắt buộc {thieu}: {url_tin}")
                            continue

                        cac_dong.append(dong)
                        da_luu.add(key)
                        so_tin_moi += 1
                        tong_moi_phien += 1
                        so_tin_moi_trang += 1

                        print(f"  [+{tong_moi_phien}] {dong['Tieu_De']} | {dong['Ten_Cong_Ty']} | {dong['Luong']}")

                        # Checkpoint lưu định kỳ
                        if so_tin_moi >= args.checkpoint:
                            xuat_csv(duong_dan_ra, cac_dong)
                            print(f"  >>> CHECKPOINT: Đã lưu {len(cac_dong)} tin ({tong_moi_phien} mới) vào {duong_dan_ra}")
                            so_tin_moi = 0

                    if so_tin_moi_trang == 0:
                        trang_trung_lien_tiep += 1
                        if trang_trung_lien_tiep >= 2:
                            print(f"  2 trang liên tiếp toàn tin trùng -> Chuyển sang từ khóa tiếp theo.")
                            break
                    else:
                        trang_trung_lien_tiep = 0

                    print(f"  Trang {n}: +{so_tin_moi_trang} tin mới | Tổng cộng: {len(cac_dong)}")

            context.close()
            browser.close()

    except KeyboardInterrupt:
        print("\nNgười dùng dừng tiến trình (Ctrl+C).")
    finally:
        # Lưu file CSV lần cuối trước khi thoát
        try:
            xuat_csv(duong_dan_ra, cac_dong)
            print(f"\nHOÀN THÀNH: Đã lưu tổng cộng {len(cac_dong)} dòng dữ liệu vào {Path(duong_dan_ra).resolve()}")
            print(f"Thống kê phiên: {dict(thong_ke)} | Tin mới thu thập: {tong_moi_phien}")
        except Exception as e:
            print(f"Lỗi khi lưu file CSV cuối cùng: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
