"""Cào ITviec theo keyword.json và ghi CSV một dòng vật lý cho mỗi tin.

Các bước chuẩn hóa lương, ngày đăng, kinh nghiệm và kỹ năng thuộc giai đoạn làm sạch.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as LoiPlaywright, TimeoutError as HetGio, sync_playwright

if __package__ in (None, ""):
    # Cho phép chạy: python crawlers/itviec_crawler.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers.base_crawler import (
    DUNG, THU_MUC_GOC, danh_dau_bat_dau, doc_csv, doc_schema,
    duoc_phep, khoa_url, kiem_thu_robot, tai_thu_lai, xuat_csv,
)

TRANG_CHU = "https://itviec.com"
TEN_BOT = "ITEC3417-ITviecResearchBot/1.0 (academic project)"
# Trang danh mục của từng nhóm ngành trong keyword.json (tên ITviec đặt có thể rộng hơn).
DUONG_DAN_NHOM = {
    "Data Analyst": "data-analyst",
    "Data Scientist": "data-scientist",
    "Data Engineer": "data-engineer",
    "AI Engineer": "ai-machine-learning-engineer",
    "Database Administrator": "database-administrator",
}
BIEN_THE_NHOM = {
    "Data Analyst": ("data analysis", "chuyên viên phân tích dữ liệu"),
    "Data Scientist": ("data science", "nhà khoa học dữ liệu"),
    "Data Engineer": ("data engineering", "kỹ sư dữ liệu"),
    "AI Engineer": ("ML engineer", "machine learning engineer", "kỹ sư AI"),
    "Database Administrator": ("DBA", "quản trị cơ sở dữ liệu"),
}
KHOANG_NGHI = (3.0, 7.0)
MAX_PAGES = 50
CHECKPOINT = 10
DUONG_DAN_CSV = THU_MUC_GOC / "data" / "raw_data" / "raw_data_itviec.csv"
TU_KHOA = THU_MUC_GOC / "keyword.json"
THU_MUC_PHIEN = THU_MUC_GOC / ".itviec_chrome_profile"
THOI_GIAN_DANG_NHAP = 180
NGUONG_KHOA_LUONG = 3
TRANG_DANG_NHAP = f"{TRANG_CHU}/sign_in"

# ---------- Phiên đăng nhập thủ công ----------

def mo_phien(playwright):
    """Mở profile riêng; dùng Chrome nếu có, không thay đổi cờ automation."""
    try:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(THU_MUC_PHIEN), channel="chrome", headless=False,
        )
    except LoiPlaywright as loi:
        if not any(dau in str(loi).casefold() for dau in ("not found", "doesn't exist", "executable doesn't exist")):
            raise
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(THU_MUC_PHIEN), headless=False,
        )

def kiem_tra_phien(trang):
    """Xác minh tại /sign_in: input[type=password] là form khi chưa đăng nhập."""
    phan_hoi = trang.goto(TRANG_DANG_NHAP, wait_until="domcontentloaded", timeout=15000)
    if phan_hoi is None:
        raise RuntimeError("Trang xác minh phiên không có phản hồi HTTP")
    url = _tach_url(trang.url)
    ma = phan_hoi.status
    duong_dan = url.path or "/"
    if _la_thu_thach_cloudflare(phan_hoi.headers):
        ray_id = phan_hoi.headers.get("cf-ray")
        tham_chieu = f", Ray ID {ray_id}" if ray_id else ""
        raise RuntimeError(f"Cloudflare yêu cầu xác minh tại {duong_dan} (HTTP {ma}{tham_chieu})")
    if ma in (401, 403, 429):
        raise RuntimeError(f"Trang xác minh phiên bị từ chối tại {duong_dan} (HTTP {ma})")
    if _bi_thu_thach(trang.content()):
        raise RuntimeError(f"Phát hiện trang xác minh hoặc CAPTCHA tại {duong_dan} (HTTP {ma})")
    if ma != 200:
        raise RuntimeError(f"Trang xác minh phiên trả HTTP {ma} tại {duong_dan}")
    if url.hostname != "itviec.com":
        raise RuntimeError("Trang xác minh phiên chuyển ra ngoài ITviec")
    khong_con_form = trang.locator('input[type="password"]').count() == 0
    return url.path.rstrip("/") != "/sign_in" and khong_con_form

def dang_nhap_tay(trang):
    """Chờ người dùng đăng nhập trong cửa sổ đã mở, có thời hạn."""
    print("Đăng nhập thủ công trên ITviec bằng Email + Mật khẩu trong cửa sổ Chrome.")
    print("Chỉ thử Google một lần; nếu gặp 'This browser or app may not be secure', dừng.")
    han = time.monotonic() + THOI_GIAN_DANG_NHAP
    while time.monotonic() < han:
        for cua_so in trang.context.pages:
            if (_tach_url(cua_so.url).hostname == "accounts.google.com"
                    and "this browser or app may not be secure" in cua_so.content().casefold()):
                print("Google từ chối trình duyệt automation; dừng. Hãy dùng đăng nhập Email của ITviec.")
                return False
        url = _tach_url(trang.url)
        if url.hostname == "itviec.com" and url.path.rstrip("/") != "/sign_in":
            return True
        trang.wait_for_timeout(1000)
    print("Hết thời gian chờ đăng nhập; chưa bắt đầu cào.")
    return False


# ---------- Bóc tách HTML ----------

def _text(tag):
    return (" ".join(tag.get_text(" ", strip=True).split()) or None) if tag else None

def _attr(tag, ten):
    gia_tri = tag.get(ten) if tag else None
    return gia_tri if isinstance(gia_tri, str) else None

def luong_goc(html):
    """Lấy nguyên văn .salary; câu khóa/không công bố/lỗi trả null."""
    van_ban = _text(BeautifulSoup(html, "html.parser").select_one(".salary"))
    return None if can_bo_sung_luong(van_ban) else van_ban

def can_bo_sung_luong(van_ban):
    """Nhận diện ô lương cũ còn trống hoặc chứa câu giữ chỗ."""
    if not van_ban:
        return True
    chu_thuong = str(van_ban).strip().casefold().replace("’", "'")
    cau_khong_co_muc_luong = {"you'll love it", "you will love it",
                             "you'll love this", "you will love this"}
    return chu_thuong.rstrip("!.") in cau_khong_co_muc_luong or chu_thuong in {
        "error", "lỗi", "n/a", "unknown"
    } or any(
        dau in chu_thuong for dau in (
            "sign in to view", "đăng nhập để xem",
            "không công bố", "chưa công bố", "not disclosed", "not available",
        )
    )

def bi_khoa_luong(html):
    """Phân biệt lương bị khóa với tin không công bố lương."""
    van_ban = _text(BeautifulSoup(html, "html.parser").select_one(".salary")) or ""
    return any(dau in van_ban.casefold() for dau in ("sign in to view", "đăng nhập để xem"))


def _tach_url(url: str):
    # Pylance báo thiếu tham số tùy chọn của Python 3.15; Python 3.13 chưa có tham số đó.
    return urlsplit(url)  # pyright: ignore[reportCallIssue]

def _url_tin(href):
    """URL chi tiết tin, bỏ query/fragment; None nếu không phải tin của ITviec."""
    if not href:
        return None
    p = _tach_url(urljoin(TRANG_CHU, href))
    if p.scheme != "https" or p.hostname != "itviec.com" or not p.path.startswith("/it-jobs/"):
        return None
    return urlunsplit(("https", "itviec.com", p.path.rstrip("/"), "", ""))

def _van_ban_khoi(tag):
    """Giữ ranh giới khối và thứ tự (xuống dòng, gạch đầu dòng) thay vì gộp JD thành một dòng."""
    soup = BeautifulSoup(str(tag), "html.parser")  # bản sao, không làm hỏng cây gốc
    for br in soup.select("br"):
        br.replace_with("\n")
    for li in soup.select("li"):
        li.insert_before("\n• ")
    for khoi in soup.select("h2, h3, h4, p, li"):
        khoi.insert_after("\n")
    dong = [" ".join(d.split()) for d in soup.get_text(" ").split("\n")]
    return "\n".join(d for d in dong if d) or None

def doc_the_tin(card):
    """Một thẻ .job-card -> dict các cột schema lấy được từ trang danh sách."""
    tieu_de = card.select_one("h3 a[href]")
    url = _url_tin(_attr(tieu_de, "href"))
    if not _text(tieu_de) or not url:
        return None
    dia_diem = card.select_one("div.text-truncate.text-nowrap[title]")
    hinh_thuc = [_text(t) for t in card.select("div.text-rich-grey.flex-shrink-0")]
    slug = url.rsplit("/", 1)[-1]
    ma = re.search(r"-(\d+)$", slug)
    return {
        "URL_Goc": url,
        "Ma_Tin_Nguon": ma.group(1) if ma else None,
        "Tieu_De": _text(tieu_de),
        "Ten_Cong_Ty": _text(card.select_one('span.text-hover-underline a[href^="/companies/"]')),
        "Dia_Diem": _attr(dia_diem, "title") or _text(dia_diem),
        "Luong": luong_goc(str(card)),
        "Hinh_Thuc_Lam_Viec": next((h for h in hinh_thuc if h in {"At office", "Remote", "Hybrid"}), None),
        "Ngay_Dang": _text(card.select_one("span.small-text.text-dark-grey")),
        "Ky_Nang": [t for t in (_text(x) for x in card.select('[data-responsive-tag-list-target="tag"]')) if t],
    }

def doc_danh_sach(html):
    """HTML danh sách -> list thẻ tin, không trùng URL."""
    ket_qua, da_thay = [], set()
    for card in BeautifulSoup(html, "html.parser").select(".job-card"):
        the = doc_the_tin(card)
        if the and the["URL_Goc"] not in da_thay:
            da_thay.add(the["URL_Goc"])
            ket_qua.append(the)
    return ket_qua

KHOI_DATALAYER_RE = re.compile(r"\bdataLayer\.push\s*\(\s*\{(.*?)\}\s*\)", re.DOTALL)

def _truong_datalayer(khoi, ten):
    khop = re.search(rf"""['"]{re.escape(ten)}['"]\s*:\s*(['"])(.*?)\1""", khoi, re.DOTALL)
    return khop.group(2).strip() if khop else None

def _luong_datalayer(html, slug):
    """Lương nằm sẵn trong script dataLayer, ví dụ 'salary_range': '600 - 1,600 USD'.
    Chỉ nhận khối có job_title_id trùng slug của tin đang đọc, tránh lấy nhầm lương tin khác."""
    # TODO: Chưa kiểm chứng live dataLayer có trong HTML mà requests ẩn danh nhận.
    if not slug:
        return None
    for khoi in KHOI_DATALAYER_RE.findall(html):
        luong = _truong_datalayer(khoi, "salary_range")
        if luong and _truong_datalayer(khoi, "job_title_id") == slug and "sign in" not in luong.casefold():
            return luong
    return None

def doc_chi_tiet(html, slug):
    """Trang chi tiết -> mô tả, yêu cầu, quyền lợi, lương, địa điểm (đều nguyên văn)."""
    soup = BeautifulSoup(html, "html.parser")
    phan = soup.select_one("section.job-content")
    dia_diem = soup.select_one('[itemprop="addressLocality"], [data-testid="job-location"], '
                               'div.text-truncate.text-nowrap[title]')
    kq = {"Mo_Ta_Cong_Viec": _van_ban_khoi(phan) if phan else None,
          "Yeu_Cau_Chi_Tiet": None, "Quyen_Loi": None,
          "Luong": luong_goc(html),
          "Dia_Diem": _attr(dia_diem, "title") or _text(dia_diem)}
    for khoi in phan.select("div.paragraph") if phan else []:
        tieu_de = re.sub(r"\s+'", "'", (_text(khoi.select_one("h2")) or "").casefold().replace("’", "'"))
        if tieu_de == "your skills and experience":
            kq["Yeu_Cau_Chi_Tiet"] = _van_ban_khoi(khoi)
        elif tieu_de == "why you'll love working here":
            kq["Quyen_Loi"] = _van_ban_khoi(khoi)
    return kq

# ---------- Tải trang ----------

def _la_thu_thach_cloudflare(headers):
    """Dùng header phản hồi của Cloudflare để nhận diện trang xác minh."""
    return headers.get("cf-mitigated") == "challenge"


def _bi_thu_thach(noi_dung):
    dau = noi_dung[:20000]
    title = re.search(r"<title\b[^>]*>(.*?)</title>", dau, re.I | re.S)
    return "cf-challenge" in dau.casefold() or bool(title and any(
        marker in title.group(1).casefold()
        for marker in ("just a moment", "attention required", "access denied", "captcha", "cloudflare")
    ))

def tai_trang(url):
    """Một lần tải HTTP; trả (nội dung, mã) theo quy ước của base.tai_thu_lai."""
    headers = {"User-Agent": TEN_BOT, "Accept": "text/html"}
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
    except (requests.Timeout, requests.ConnectionError):
        return None, "loi_tam_thoi"
    ma = r.status_code
    if ma in (401, 403, 429) or _la_thu_thach_cloudflare(r.headers):
        return None, "bi_chan"
    vi_tri = r.headers.get("Location")
    if ma == 404:
        print(f"  {url}: HTTP {ma}, Location={vi_tri!r}")
        return None, "khong_ton_tai"
    if ma >= 500:
        return None, "loi_tam_thoi"
    if 300 <= ma < 400:
        if "sign_in" in (vi_tri or "").casefold():
            return None, "bi_chan"
        print(f"  {url}: HTTP {ma}, Location={vi_tri!r}")
        return None, "khong_ton_tai"
    if ma != 200:
        return None, "bi_cam"
    if _bi_thu_thach(r.text):
        return None, "bi_chan"
    if "text/html" not in r.headers.get("Content-Type", "").casefold():
        return None, "bi_cam"
    return r.text, "ok"

def tai_phien(trang, url):
    """Tải trang chi tiết bằng profile đã xác minh, trả mã lỗi như base."""
    try:
        phan_hoi = trang.goto(url, wait_until="load", timeout=15000)
    except HetGio:
        return None, "loi_tam_thoi"
    if phan_hoi is None:
        return None, "loi_tam_thoi"
    ma = phan_hoi.status
    if ma in (401, 403, 429) or _la_thu_thach_cloudflare(phan_hoi.headers):
        return None, "bi_chan"
    if ma == 404:
        return None, "khong_ton_tai"
    if ma >= 500:
        return None, "loi_tam_thoi"
    url_hien_tai = _tach_url(trang.url)
    if url_hien_tai.hostname != "itviec.com" or url_hien_tai.path.rstrip("/") == "/sign_in":
        return None, "bi_chan"
    if khoa_url(trang.url) != khoa_url(url):
        return None, "khong_ton_tai"
    if ma != 200:
        return None, "bi_cam"
    html = trang.content()
    if _bi_thu_thach(html):
        return None, "bi_chan"
    return html, "ok"

def tai_danh_sach(trang, url, rp, buoc, cac_the=(), so_the=0):
    """Tải danh sách bằng phiên đã đăng nhập, cho phép chuyển hướng nội bộ."""
    co_che = buoc.co_che
    phan_hoi = []

    def theo_doi(r):
        if (_tach_url(r.url).hostname == "itviec.com"
                and r.request.resource_type in {"document", "xhr", "fetch"}):
            phan_hoi.append(r)

    trang.on("response", theo_doi)
    try:
        try:
            if co_che in {"mở URL", "href"}:
                r = trang.goto(url, wait_until="load", timeout=15000)
                if r is None:
                    return None, "loi_tam_thoi"
            else:
                if co_che == "cuộn":
                    trang.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                else:
                    trang.locator(buoc.selector).nth(buoc.vi_tri).click(timeout=5000)
                trang.wait_for_function("""({cu, soThe, them}) => {
                    const cards = [...document.querySelectorAll('.job-card')];
                    if (/captcha|just a moment|access denied/i.test(document.title)) return true;
                    if (them && cards.length <= soThe) return false;
                    return cards.some(card => {
                        const link = card.querySelector('h3 a[href]');
                        if (!link) return false;
                        const url = new URL(link.href);
                        return url.host === location.host && url.pathname.startsWith('/it-jobs/') &&
                               !cu.includes(url.pathname.replace(/\\/$/, ''));
                    });
                }""", arg={"cu": [_tach_url(t["URL_Goc"]).path for t in cac_the], "soThe": so_the,
                             "them": co_che in {"xem thêm", "cuộn"}}, timeout=10000)
        except HetGio:
            if co_che in {"mở URL", "href"} and not phan_hoi:
                return None, "loi_tam_thoi"
            # Không bấm lại sau timeout: HTML hiện tại sẽ được kiểm tra xem còn thẻ mới không.

        if any(r.status in (401, 403, 429) or _la_thu_thach_cloudflare(r.headers) for r in phan_hoi):
            return None, "bi_chan"
        html = trang.content()
        url_cuoi = _tach_url(trang.url)
        if (url_cuoi.scheme != "https" or url_cuoi.hostname != "itviec.com"
                or url_cuoi.path.rstrip("/") in {"/sign_in", "/users/sign_in", "/dang-nhap"}
                or _bi_thu_thach(html)):
            return None, "bi_chan"
        if not duoc_phep(rp, TRANG_CHU, trang.url, TEN_BOT):
            print(f"  robots.txt không cho phép URL đích: {trang.url}")
            return None, "bi_cam"
        # Ưu tiên phản hồi của chính nút AJAX hoặc document cuối, bỏ qua tải nội dung bên cạnh.
        r = next((r for r in reversed(phan_hoi) if r.url == url or
                  (r.request.resource_type == "document" and r.request.frame == trang.main_frame)), None)
        if r is not None:
            if r.status == 404:
                print(f"  {r.url}: HTTP 404, Location={r.headers.get('location')!r}")
                return None, "khong_ton_tai"
            if r.request.resource_type in {"xhr", "fetch"} and "text/html" in r.headers.get("content-type", ""):
                if _bi_thu_thach(r.text()):
                    return None, "bi_chan"
            if r.status >= 500:
                return None, "loi_tam_thoi" if co_che in {"mở URL", "href"} else "bi_cam"
            if r.status >= 400:
                return None, "bi_cam"
        return html, "ok"
    finally:
        trang.remove_listener("response", theo_doi)

def tai(url, rp, thong_ke, ham_tai=None):
    """Kiểm tra robots rồi tải có thử lại; mọi lần tải đều đi qua đây."""
    if not duoc_phep(rp, TRANG_CHU, url, TEN_BOT):
        print(f"robots.txt không cho phép: {url}")
        thong_ke["bi_cam"] += 1
        return None, "bi_cam"
    return tai_thu_lai(ham_tai or tai_trang, url, thong_ke, khoang_nghi=KHOANG_NGHI)


def tao_dong(the, chi_tiet, url_tim_kiem, tu_khoa, timestamp):
    """Gộp thẻ danh sách + chi tiết. Cột không có (Kinh_Nghiem, Loai_Hop_Dong) để trống; xuat_csv ghi null."""
    dong = dict(the, Web="itviec", URL_Tim_Kiem=url_tim_kiem, Tu_Khoa_Tim_Kiem=tu_khoa,
                Timestamp=timestamp, Kinh_Nghiem=None, Loai_Hop_Dong=None)
    dong["Luong"] = chi_tiet["Luong"] or the["Luong"]
    dong["Dia_Diem"] = the["Dia_Diem"] or chi_tiet["Dia_Diem"]
    for cot in ("Mo_Ta_Cong_Viec", "Yeu_Cau_Chi_Tiet", "Quyen_Loi"):
        dong[cot] = chi_tiet[cot]
    return dong

def thieu_cot_bat_buoc(dong):
    """Tên cột bắt buộc (không cho null) còn trống; dùng để bỏ tin lỗi thay vì làm hỏng cả lần xuất CSV."""
    schema = doc_schema()
    return [c for c in schema["required"]
            if "null" not in schema["properties"][c]["type"] and not str(dong.get(c) or "").strip()]

def ghi_csv_mot_dong(cac_dong):
    """Mã hóa xuống dòng trong ô thành chữ \\n để mỗi tin chiếm một dòng vật lý."""
    dong_da_doi = [
        {cot: value.replace("\r\n", r"\n").replace("\r", r"\n").replace("\n", r"\n")
         if isinstance(value, str) else value for cot, value in dong.items()}
        for dong in cac_dong
    ]
    xuat_csv(DUONG_DAN_CSV, dong_da_doi)

# ---------- Cào theo từ khóa ----------

class BuocDanhSach(NamedTuple):
    co_che: str
    url: str
    selector: str = ""
    vi_tri: int = 0


def cac_truy_van(nhom_chon, ky_nang, chi_danh_muc):
    """Sinh (từ khóa, URL, nhóm cần lọc) theo URL do ô tìm kiếm ITviec tạo."""
    for nhom in nhom_chon:
        yield nhom, f"{TRANG_CHU}/it-jobs/{DUONG_DAN_NHOM[nhom]}", None
    if chi_danh_muc:
        return
    for nhom in nhom_chon:
        for kn in ky_nang:
            tu_khoa = f"{nhom} {kn}"
            # Ô tìm kiếm sinh /it-jobs/data-engineer-sql và /it-jobs/data-engineer-pl-sql.
            slug = re.sub(r"[^\w]+", "-", tu_khoa.casefold()).strip("-")
            yield tu_khoa, f"{TRANG_CHU}/it-jobs/{slug}", nhom

def dung_nhom(tieu_de, nhom):
    """So khớp từ theo tiêu đề, kể cả khi có dấu gạch giữa các từ."""
    tieu_de = " " + " ".join(re.findall(r"\w+", tieu_de.casefold())) + " "
    return any(f" {ten.casefold()} " in tieu_de for ten in (nhom, *BIEN_THE_NHOM[nhom]))


def tim_trang_sau(soup, url, so_trang) -> BuocDanhSach | None:
    """Tìm nút tiến trong HTML; ưu tiên nút phân trang trước tải thêm hoặc cuộn."""
    selector = ('a[rel~="next"], button[rel~="next"], nav.ipagination a, nav.ipagination button, '
                '.pagination a, .pagination button, [data-load-more], button, [role="button"]')
    nut_them = None
    for i, nut in enumerate(soup.select(selector)):
        if (nut.has_attr("disabled") or nut.has_attr("hidden") or nut.get("aria-disabled") == "true"
                or "disabled" in nut.get("class", []) or nut.find_parent(class_="disabled")):
            continue
        href = _attr(nut, "href") or ""
        dich = urljoin(url, href)
        if href and (_tach_url(dich).scheme != "https" or _tach_url(dich).hostname != "itviec.com"):
            continue
        ten = (_attr(nut, "aria-label") or _text(nut) or "").casefold()
        ke = ("next" in nut.get("rel", []) or ten in {"next", "next page", "trang sau", "trang tiếp"}
              or href and nut.find_parent(class_=re.compile(r"(?:^|\s)i?pagination(?:\s|$)")) is not None
              and parse_qs(_tach_url(dich).query).get("page") == [str(so_trang + 1)])
        if ke:
            # ITviec thực tế gắn data-remote và search--pagination để bấm AJAX.
            ajax = nut.get("data-remote") == "true" or "ajax" in (_attr(nut, "data-action") or "")
            if href and not href.startswith("#") and not ajax:
                return BuocDanhSach("href", dich)
            return BuocDanhSach("bấm nút/AJAX", dich if href and not href.startswith("#") else url, selector, i)
        if nut_them is None and (nut.has_attr("data-load-more") or ten in {
                "load more", "load more jobs", "show more jobs", "xem thêm", "xem thêm việc làm"}):
            nut_them = BuocDanhSach("xem thêm", dich if href and not href.startswith("#") else url, selector, i)
    if nut_them is not None:
        return nut_them
    if soup.select_one('[data-infinite-scroll], [data-controller*="infinite-scroll"]'):
        return BuocDanhSach("cuộn", url)
    return None


def cao_truy_van(tu_khoa, url_goc, nhom_loc, *, rp, cac_dong, da_luu, thong_ke,
                 so_cu, max_pages, gioi_han, trang_chi_tiet=None, dong_theo_url=None,
                 trang_danh_sach=None, tom_tat=None, da_tai_chi_tiet=None):
    """Đọc nút trang kế ngay từ trang 1: theo href, bấm rồi chờ đổi thẻ, hoặc tải thêm.

    Dừng khi hết nút, danh sách không có URL mới, tới max-pages hoặc gặp lỗi/giới hạn tải.
    """
    if tom_tat is None:
        tom_tat = Counter()
    if da_tai_chi_tiet is None:
        da_tai_chi_tiet = set()
    moi = da_xu_ly = 0
    da_thay = set()  # URL đã gặp trong từ khóa này, để nhận ra server trả lại trang cũ
    buoc = BuocDanhSach("mở URL", url_goc)
    cac_the, so_the_tho = [], 0
    for trang in range(1, max_pages + 1):
        url = buoc.url
        if trang_danh_sach is None:
            noi_dung, ma = tai(url, rp, thong_ke)
        else:
            noi_dung, ma = tai(url, rp, thong_ke,
                               lambda dich: tai_danh_sach(trang_danh_sach, dich, rp, buoc, cac_the, so_the_tho))
        if ma != "ok" or noi_dung is None:
            print(f"  [{tu_khoa}] trang {trang} | {buoc.co_che} | {url} | thẻ thô: -, thẻ mới: - | dừng: {ma}")
            return moi, ma if ma in DUNG else None
        url_hien_tai = trang_danh_sach.url if trang_danh_sach is not None else url
        soup = BeautifulSoup(noi_dung, "html.parser")
        so_the_tho = len(soup.select(".job-card"))
        cac_the = doc_danh_sach(noi_dung)
        the_chua_thay = [t for t in cac_the if t["URL_Goc"] not in da_thay]
        da_thay.update(t["URL_Goc"] for t in the_chua_thay)
        tom_tat["trang"] += 1
        the_dung_nhom = [t for t in the_chua_thay if not nhom_loc or dung_nhom(t["Tieu_De"], nhom_loc)]
        bi_loc = len(the_chua_thay) - len(the_dung_nhom)
        tom_tat["the_phu_hop"] += len(the_dung_nhom)
        tom_tat["ngoai_nhom"] += bi_loc
        moi_trang = cap_nhat_trang = 0
        ma_dung = None
        for the in the_dung_nhom:
            khoa = khoa_url(the["URL_Goc"])
            if khoa in da_tai_chi_tiet:
                continue
            dong_cu = dong_theo_url.get(khoa) if dong_theo_url is not None else None
            if khoa in da_luu and (dong_cu is None or not can_bo_sung_luong(dong_cu.get("Luong"))):
                continue
            if gioi_han and da_xu_ly >= gioi_han:
                break
            da_xu_ly += 1
            thong_ke["da_xu_ly"] += 1
            timestamp = danh_dau_bat_dau() if dong_cu is None else None
            if trang_chi_tiet is None:
                html, ma = tai(the["URL_Goc"], rp, thong_ke)
            else:
                html, ma = tai(the["URL_Goc"], rp, thong_ke,
                               lambda url: tai_phien(trang_chi_tiet, url))
            if ma in DUNG:
                ma_dung = ma
                break
            if ma != "ok" or html is None:
                continue
            da_tai_chi_tiet.add(khoa)
            if trang_chi_tiet is not None:
                thong_ke["luong_khoa_lien_tiep"] = (
                    thong_ke["luong_khoa_lien_tiep"] + 1 if bi_khoa_luong(html) else 0
                )
                if thong_ke["luong_khoa_lien_tiep"] >= NGUONG_KHOA_LUONG:
                    print("Dừng: nhiều trang liên tiếp vẫn khóa lương; phiên có thể đã hết hạn.")
                    ma_dung = "bi_chan"
                    break
            chi_tiet = doc_chi_tiet(html, the["URL_Goc"].rsplit("/", 1)[-1])
            if dong_cu is not None:
                if chi_tiet["Luong"] is not None:
                    dong_cu["Luong"] = chi_tiet["Luong"]
                    thong_ke["cap_nhat_luong"] += 1
                    cap_nhat_trang += 1
                    if (len(cac_dong) - so_cu + thong_ke["cap_nhat_luong"]) % CHECKPOINT == 0:
                        ghi_csv_mot_dong(cac_dong)
                else:
                    print(f"  Chưa có lương hiển thị: {the['URL_Goc']}")
                continue
            dong = tao_dong(the, chi_tiet, url_goc, tu_khoa, timestamp)
            thieu = thieu_cot_bat_buoc(dong)
            if thieu:
                print(f"Bỏ tin {the['URL_Goc']} vì thiếu: {', '.join(thieu)}")
                continue
            cac_dong.append(dong)
            da_luu.add(khoa)
            moi += 1
            moi_trang += 1
            if (len(cac_dong) - so_cu) % CHECKPOINT == 0:
                ghi_csv_mot_dong(cac_dong)
        if trang >= 2:
            tom_tat["moi_tu_trang_2"] += moi_trang
        ly_do = ma_dung
        buoc_sau = None
        if not ly_do:
            if gioi_han and da_xu_ly >= gioi_han:
                ly_do = "chạm --limit"
            elif not the_chua_thay:
                ly_do = "không thẻ mới"
            elif trang >= max_pages:
                ly_do = "chạm max-pages"
            else:
                buoc_sau = tim_trang_sau(soup, url_hien_tai, trang)
                if buoc_sau is None:
                    ly_do = "hết nút"
        trang_thai = f"dừng: {ly_do}" if buoc_sau is None else f"tiếp: {buoc_sau.co_che}"
        print(f"  [{tu_khoa}] trang {trang} | {buoc.co_che} | {url_hien_tai} | "
              f"thẻ thô: {so_the_tho}, thẻ mới: {len(the_chua_thay)}, tin mới: {moi_trang}, "
              f"ngoài nhóm: {bi_loc}, lương bổ sung: {cap_nhat_trang} | {trang_thai}")
        if buoc_sau is None:
            return moi, ma_dung
        buoc = buoc_sau
    return moi, None

def main(argv=None):
    cli = argparse.ArgumentParser(description="ITviec crawler ITEC3417")
    cli.add_argument("--nhom", choices=list(DUONG_DAN_NHOM), help="Chỉ cào một nhóm ngành")
    cli.add_argument("--chi-danh-muc", action="store_true", help="Chỉ cào trang danh mục nhóm, bỏ tìm theo kỹ năng")
    cli.add_argument("--max-pages", type=int, default=MAX_PAGES)
    cli.add_argument("--limit", type=int, default=0,
                     help="Giới hạn số trang chi tiết xử lý, gồm tin mới và bổ sung lương (0 = không giới hạn)")
    args = cli.parse_args(argv)
    if args.max_pages < 1 or args.limit < 0:
        cli.error("--max-pages phải >= 1 và --limit phải >= 0")

    cau_hinh = json.loads(TU_KHOA.read_text(encoding="utf-8"))
    nhom_ds, ky_nang = cau_hinh["Nhom_Nghanh"], cau_hinh["Ki_Nang"]
    for ten, values in (("Nhom_Nghanh", nhom_ds), ("Ki_Nang", ky_nang)):
        if not isinstance(values, list) or not all(isinstance(x, str) and x.strip() for x in values):
            cli.error(f"keyword.json: {ten} không hợp lệ")
    chua_co = [n for n in nhom_ds if n not in DUONG_DAN_NHOM]
    if chua_co:
        cli.error(f"keyword.json có nhóm chưa có đường dẫn ITviec: {chua_co}")
    if args.nhom and args.nhom not in nhom_ds:
        cli.error("--nhom phải thuộc keyword.json/Nhom_Nghanh")
    nhom_chon = [args.nhom] if args.nhom else nhom_ds
    truy_van = list(cac_truy_van(nhom_chon, ky_nang, args.chi_danh_muc))

    muc_tieu = [TRANG_DANG_NHAP] + [url for _, url, _ in truy_van]
    rp, ly_do = kiem_thu_robot(TRANG_CHU, muc_tieu, TEN_BOT)
    if rp is None:
        print(f"Dừng: {ly_do}")
        return 2
    try:
        with sync_playwright() as playwright:
            phien = mo_phien(playwright)
            try:
                trang = phien.pages[0] if phien.pages else phien.new_page()
                if not kiem_tra_phien(trang):
                    if not dang_nhap_tay(trang) or not kiem_tra_phien(trang):
                        print("Dừng: phiên đăng nhập chưa hợp lệ; chưa cào dữ liệu.")
                        return 2
                try:
                    cac_dong = doc_csv(DUONG_DAN_CSV)
                except ValueError as loi:
                    print(f"Dừng: {loi}")
                    return 2
                for dong in cac_dong:
                    if can_bo_sung_luong(dong.get("Luong")):
                        dong["Luong"] = None
                if any("Khop_Ky_Nang:" in str(d.get("Tu_Khoa_Tim_Kiem") or "")
                       or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("Ngay_Dang") or ""))
                       or d.get("Kinh_Nghiem") for d in cac_dong):
                    print("Cảnh báo: CSV cũ có dữ liệu đã chuẩn hóa; nên sao lưu rồi cào lại để dữ liệu thô đồng nhất.")
                da_luu = {khoa_url(d["URL_Goc"]) for d in cac_dong if d.get("URL_Goc")}
                dong_theo_url = {khoa_url(d["URL_Goc"]): d for d in cac_dong if d.get("URL_Goc")}
                so_cu, thong_ke, dung = len(cac_dong), Counter(), None
                trang_danh_sach = phien.new_page()
                tong_hop = []
                da_tai_chi_tiet = set()
                try:
                    for tu_khoa, url, nhom_loc in truy_van:
                        con_lai = args.limit - thong_ke["da_xu_ly"] if args.limit else 0
                        if args.limit and con_lai <= 0:
                            break
                        ket_qua = Counter()
                        tong_hop.append((tu_khoa, nhom_loc, ket_qua))
                        moi, dung = cao_truy_van(
                            tu_khoa, url, nhom_loc, rp=rp, cac_dong=cac_dong,
                            da_luu=da_luu, thong_ke=thong_ke, so_cu=so_cu,
                            max_pages=args.max_pages, gioi_han=con_lai, trang_chi_tiet=trang,
                            dong_theo_url=dong_theo_url, trang_danh_sach=trang_danh_sach, tom_tat=ket_qua,
                            da_tai_chi_tiet=da_tai_chi_tiet,
                        )
                        ket_qua["moi"] = moi
                        print(f"[{tu_khoa}] +{moi} tin mới; tổng lương bổ sung: {thong_ke['cap_nhat_luong']}", flush=True)
                        if dung in DUNG:
                            print(f"Dừng toàn bộ: {dung}")
                            break
                except KeyboardInterrupt:
                    dung = "Ctrl+C"
                    print("Đã dừng bằng Ctrl+C; đang lưu CSV.")
                finally:
                    ghi_csv_mot_dong(cac_dong)
            finally:
                phien.close()
    except (LoiPlaywright, HetGio, RuntimeError) as loi:
        print(f"Dừng: không mở hoặc xác minh được phiên ITviec: {loi}")
        return 2
    print("Tóm tắt theo truy vấn")
    for tu_khoa, _, kq in tong_hop:
        print(f"  [{tu_khoa}] {kq['trang']} trang, {kq['moi']} tin mới, {kq['moi_tu_trang_2']} từ trang >= 2, "
              f"{kq['the_phu_hop']} thẻ phù hợp, {kq['ngoai_nhom']} thẻ ngoài nhóm")
    print(f"Tổng {sum(kq['trang'] for _, _, kq in tong_hop)} trang danh sách, "
          f"{sum(kq['moi_tu_trang_2'] for _, _, kq in tong_hop)} tin mới từ trang >= 2, "
          f"{sum(bool(nhom and kq['the_phu_hop']) for _, nhom, kq in tong_hop)} truy vấn kỹ năng có kết quả, "
          f"{sum(kq['ngoai_nhom'] for _, _, kq in tong_hop)} thẻ ngoài nhóm bị lọc")
    thieu_luong = sum(not d.get("Luong") for d in cac_dong)
    print(f"Tin mới: {len(cac_dong) - so_cu}; tổng: {len(cac_dong)}; lương trống: {thieu_luong}; "
          f"thống kê tải: {dict(thong_ke)}\nCSV: {DUONG_DAN_CSV}")
    return 130 if dung == "Ctrl+C" else 2 if dung in DUNG else 0

if __name__ == "__main__":
    raise SystemExit(main())
