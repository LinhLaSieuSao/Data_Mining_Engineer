"""Cào ITviec theo keyword.json và ghi CSV một dòng vật lý cho mỗi tin.

Các bước chuẩn hóa lương, ngày đăng, kinh nghiệm và kỹ năng thuộc giai đoạn làm sạch.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlunsplit, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

if __package__ in (None, ""):
    # Cho phép chạy trực tiếp bằng python crawlers/itviec.py.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers.base_crawler import (
    DUNG, THU_MUC_GOC, danh_dau_bat_dau, doc_csv, doc_schema,
    duoc_phep, khoa_url, kiem_thu_robot, nghi_ngau_nhien, tai_thu_lai, xuat_csv,
)
TEN_BOT = "ITEC3417-ITviecResearchBot/1.0 (academic project)"
TRANG_CHU = "https://itviec.com"


def _tach_url(url):
    return urlsplit(url)


def la_thu_thach_cloudflare(headers):
    return headers.get("cf-mitigated", "").casefold() == "challenge"


def bi_thu_thach(noi_dung):
    dau = noi_dung[:20000]
    title = re.search(r"<title\b[^>]*>(.*?)</title>", dau, re.I | re.S)
    return any(marker in dau.casefold() for marker in (
        "cf-challenge", "g-recaptcha", "h-captcha", "cf-turnstile",
    )) or bool(title and any(marker in title.group(1).casefold() for marker in (
        "just a moment", "attention required", "access denied", "captcha", "cloudflare",
    )))


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
DUONG_DAN_CSV = THU_MUC_GOC / "data" / "raw" / "raw_itviec.csv"
TU_KHOA = THU_MUC_GOC / "keyword.json"

# ---------- Bóc tách HTML ----------

def _text(tag):
    return (" ".join(tag.get_text(" ", strip=True).split()) or None) if tag else None

def _attr(tag, ten):
    gia_tri = tag.get(ten) if tag else None
    return gia_tri if isinstance(gia_tri, str) else None

def luong_goc(html):
    """Lấy nguyên văn .salary; câu khóa/không công bố/lỗi trả null."""
    soup = html if isinstance(html, Tag) else BeautifulSoup(html, "html.parser")
    van_ban = _text(soup.select_one(".salary"))
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
    soup = html if isinstance(html, Tag) else BeautifulSoup(html, "html.parser")
    van_ban = (_text(soup.select_one(".salary")) or "").casefold()
    return any(dau in van_ban for dau in ("sign in to view", "đăng nhập để xem"))

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
        "Luong": luong_goc(card),
        "Hinh_Thuc_Lam_Viec": next((h for h in hinh_thuc if h), None),
        "Ngay_Dang": _text(card.select_one("span.small-text.text-dark-grey")),
        "Ky_Nang": [t for t in (_text(x) for x in card.select('[data-responsive-tag-list-target="tag"]')) if t],
    }

def doc_danh_sach(html):
    """HTML danh sách -> list thẻ tin, không trùng URL."""
    ket_qua, da_thay = [], set()
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "html.parser")
    for card in soup.select(".job-card"):
        the = doc_the_tin(card)
        if the and the["URL_Goc"] not in da_thay:
            da_thay.add(the["URL_Goc"])
            ket_qua.append(the)
    return ket_qua

def doc_kinh_nghiem(khoi):
    """Giữ nội dung dưới nhãn Experience/Kinh nghiệm trong khối yêu cầu."""
    for nhan in khoi.find_all(["h3", "h4", "h5", "p", "li", "strong", "b", "span"]):
        van_ban = _text(nhan) or ""
        khop = re.fullmatch(r"(?:Experience|Kinh nghiệm)\s*[:：]?", van_ban, re.I)
        cung_dong = re.match(r"^(?:Experience|Kinh nghiệm)\s*[:：]\s*(.+)$", van_ban, re.I)
        if cung_dong:
            vb = _van_ban_khoi(nhan) or ""
            res = re.sub(r"^(?:Experience|Kinh nghiệm)\s*[:：]\s*", "", vb, count=1, flags=re.I)
            return res.strip() or None
        if not khop:
            continue
        # Nhãn in đậm có thể nằm trong một đoạn chỉ chứa nhãn.
        while nhan.parent is not khoi and _text(nhan.parent) == van_ban:
            nhan = nhan.parent
        noi_dung = []
        for muc in nhan.next_siblings:
            if not isinstance(muc, Tag):
                if str(muc).strip():
                    noi_dung.append(str(muc).strip())
                continue
            if muc.name in {"h2", "h3", "h4", "h5"}:
                break
            nhan_tiep = muc.find(["strong", "b"])
            if muc.name == "p" and ((_text(muc) or "").endswith(":")
                                    or nhan_tiep and _text(nhan_tiep) == _text(muc)):
                break
            if muc.name not in {"ul", "ol", "li", "p", "div"}:
                break
            text = _van_ban_khoi(muc)
            if text:
                noi_dung.append(text)
        return "\n".join(noi_dung) or None
    return None


def doc_chi_tiet(html, slug):
    """Trang chi tiết -> mô tả, yêu cầu, quyền lợi, lương, địa điểm (đều nguyên văn)."""
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "html.parser")
    phan = soup.select_one("section.job-content")
    dia_diem = soup.select_one('[itemprop="addressLocality"], [data-testid="job-location"], '
                               'div.text-truncate.text-nowrap[title]')
    kq = {"Mo_Ta_Cong_Viec": _van_ban_khoi(phan) if phan else None,
          "Yeu_Cau_Chi_Tiet": None, "Quyen_Loi": None, "Kinh_Nghiem": None,
          "Luong": luong_goc(soup),
          "Dia_Diem": _attr(dia_diem, "title") or _text(dia_diem)}
    for khoi in phan.select("div.paragraph") if phan else []:
        tieu_de = re.sub(r"\s+'", "'", (_text(khoi.select_one("h2")) or "").casefold().replace("’", "'"))
        if tieu_de in {"your skills and experience", "yêu cầu công việc", "yêu cầu ứng viên"}:
            kq["Yeu_Cau_Chi_Tiet"] = _van_ban_khoi(khoi)
            kq["Kinh_Nghiem"] = doc_kinh_nghiem(khoi)
        elif tieu_de in {"why you'll love working here", "quyền lợi"}:
            kq["Quyen_Loi"] = _van_ban_khoi(khoi)
    return kq

# ---------- Tải trang ----------

def tai_trang(url, *, ajax=False):
    """Một lần tải HTTP; trả (nội dung, mã) theo quy ước của base.tai_thu_lai."""
    headers = {"User-Agent": TEN_BOT, "Accept": "text/html"}
    if ajax:
        headers.update({"Accept": "application/json, text/html", "X-Requested-With": "XMLHttpRequest"})
    nghi_ngau_nhien(KHOANG_NGHI)
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
    except (requests.Timeout, requests.ConnectionError):
        return None, "loi_tam_thoi"
    ma = r.status_code
    if ma in (401, 403, 429) or la_thu_thach_cloudflare(r.headers):
        return None, "bi_chan"
    vi_tri = r.headers.get("Location")
    if ma == 404:
        print(f"  {url}: HTTP {ma}, Location={vi_tri!r}")
        return None, "khong_ton_tai"
    if ma >= 500:
        return None, "loi_tam_thoi"
    if 300 <= ma < 400:
        if _tach_url(urljoin(url, vi_tri or "")).path.rstrip("/") in {"/sign_in", "/users/sign_in", "/dang-nhap"}:
            return None, "bi_chan"
        print(f"  {url}: HTTP {ma}, Location={vi_tri!r}")
        return None, "khong_ton_tai"
    if ma != 200:
        return None, "bi_cam"
    if bi_thu_thach(r.text):
        return None, "bi_chan"
    if ajax:
        try:
            data = json.loads(r.text)
        except ValueError:
            print(f"Lỗi AJAX: JSON không hợp lệ tại {url}")
            return None, "bi_cam"
        if not isinstance(data, dict) or not isinstance(data.get("jobs_html"), str):
            print(f"Lỗi AJAX: thiếu hoặc sai kiểu jobs_html tại {url}")
            return None, "bi_cam"
        if not isinstance(data.get("pagination_html", ""), str) or not isinstance(data.get("headline_result_html", ""), str):
            print(f"Lỗi AJAX: pagination_html/headline_result_html sai kiểu tại {url}")
            return None, "bi_cam"
        if bi_thu_thach(data["jobs_html"]):
            return None, "bi_chan"
        return data, "ok"
    if r.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold() == "text/html":
        return r.text, "ok"
    return None, "bi_cam"


def tai(url, rp, thong_ke, ham_tai=None):
    """Kiểm tra robots rồi tải có thử lại; mọi lần tải đều đi qua đây."""
    if not duoc_phep(rp, TRANG_CHU, url, TEN_BOT):
        print(f"robots.txt không cho phép: {url}")
        thong_ke["bi_cam"] += 1
        return None, "bi_cam"
    return tai_thu_lai(ham_tai or tai_trang, url, thong_ke, khoang_nghi=(0, 0))


def tao_dong(the, chi_tiet, url_tim_kiem, tu_khoa, timestamp):
    """Gộp thẻ tin với chi tiết nguyên văn; loại hợp đồng chưa có trường riêng."""
    dong = dict(the, Web="itviec", URL_Tim_Kiem=url_tim_kiem, Tu_Khoa_Tim_Kiem=tu_khoa,
                Timestamp=timestamp, Kinh_Nghiem=chi_tiet.get("Kinh_Nghiem"), Loai_Hop_Dong=None)
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


def tim_trang_sau(soup, url, so_trang):
    """Chỉ lấy tín hiệu còn trang; URL được dựng lại từ đường dẫn gốc."""
    for nut in soup.select('[rel~="next"], .pagination a, .pagination button, .ipagination a, .ipagination button'):
        if (nut.has_attr("disabled") or nut.has_attr("hidden") or nut.get("aria-disabled") == "true"
                or "disabled" in nut.get_attribute_list("class") or nut.find_parent(class_="disabled")):
            continue
        trang_tiep = str(so_trang + 1)
        href = _attr(nut, "href") or ""
        if ("next" in nut.get_attribute_list("rel") or _text(nut) == trang_tiep
                or parse_qs(_tach_url(href).query).get("page") == [trang_tiep]):
            phan = _tach_url(url)
            dich = urlunsplit((phan.scheme, phan.netloc, phan.path, f"page={trang_tiep}&source=search_job", ""))
            return "AJAX", dich, True
    return None


def cao_truy_van(tu_khoa, url_goc, nhom_loc, *, rp, cac_dong, da_luu, thong_ke,
                 so_cu, max_pages, gioi_han, dong_theo_url=None,
                 tom_tat=None, da_tai_chi_tiet=None):
    """Tải danh sách và chi tiết công khai theo từng truy vấn."""
    if tom_tat is None:
        tom_tat = Counter()
    if da_tai_chi_tiet is None:
        da_tai_chi_tiet = set()
    moi = da_xu_ly = 0
    da_thay = set()  # URL đã gặp trong từ khóa này, để nhận ra server trả lại trang cũ
    trang_da_tai = set()
    buoc = ("mở URL", url_goc, False)
    for trang in range(1, max_pages + 1):
        url = buoc[1]
        if url is None:
            break
        trang_da_tai.add(url)
        if buoc[2]:
            noi_dung, ma = tai(url, rp, thong_ke, lambda dich: tai_trang(dich, ajax=True))
        else:
            noi_dung, ma = tai(url, rp, thong_ke)
        if ma != "ok" or noi_dung is None:
            print(f"  [{tu_khoa}] trang {trang} | {buoc[0]} | {url} | thẻ thô: -, thẻ mới: - | dừng: {ma}")
            return moi, ma
        if isinstance(noi_dung, dict):
            headline = _text(BeautifulSoup(noi_dung.get("headline_result_html", ""), "html.parser"))
            if headline:
                hl = tom_tat.get("headlines")
                if isinstance(hl, list):
                    hl.append(headline)
                else:
                    tom_tat["headlines"] = [headline]  # pyright: ignore[reportArgumentType]
            html_tin = noi_dung["jobs_html"]
            phan_trang = BeautifulSoup(noi_dung.get("pagination_html", ""), "html.parser")
        else:
            html_tin = noi_dung
            phan_trang = BeautifulSoup(noi_dung, "html.parser")
        soup = BeautifulSoup(html_tin, "html.parser")
        so_the_tho = len(soup.select(".job-card"))
        cac_the = doc_danh_sach(soup)
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
            html, ma = tai(the["URL_Goc"], rp, thong_ke)
            if ma in (*DUNG, "bi_cam"):
                ma_dung = ma
                break
            if ma != "ok" or html is None:
                continue
            da_tai_chi_tiet.add(khoa)
            chi_tiet = doc_chi_tiet(html, the["URL_Goc"].rsplit("/", 1)[-1])
            if dong_cu is not None:
                luong = chi_tiet["Luong"] or the["Luong"]
                if luong is not None:
                    dong_cu["Luong"] = luong
                    thong_ke["cap_nhat_luong"] += 1
                    cap_nhat_trang += 1
                    if (len(cac_dong) - so_cu + thong_ke["cap_nhat_luong"]) % CHECKPOINT == 0:
                        ghi_csv_mot_dong(cac_dong)
                else:
                    print(f"  Chưa có lương hiển thị: {the['URL_Goc']}")
            else:
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
                buoc_sau = tim_trang_sau(phan_trang, url_goc, trang)
                if buoc_sau is None:
                    ly_do = "hết nút"
                elif buoc_sau[1] is None:
                    ly_do = f"{buoc_sau[0]} không có URL để tải bằng requests"
                    buoc_sau = None
                elif buoc_sau[1] in trang_da_tai:
                    ly_do = "URL trang kế đã tải"
                    buoc_sau = None
        trang_thai = f"dừng: {ly_do}" if buoc_sau is None else f"tiếp: {buoc_sau[0]}"
        print(f"  [{tu_khoa}] trang {trang} | {buoc[0]} | {url} | "
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
                     help="Giới hạn số tin xử lý, gồm tin mới và tin cần bổ sung lương (0 = không giới hạn)")
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

    muc_tieu = [url for _, url, _ in truy_van]
    nghi_ngau_nhien(KHOANG_NGHI)
    rp, ly_do = kiem_thu_robot(TRANG_CHU, muc_tieu, TEN_BOT)
    if rp is None:
        print(f"Dừng: {ly_do}")
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
           or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("Ngay_Dang") or "")) for d in cac_dong):
        print("Cảnh báo: CSV cũ có dữ liệu đã chuẩn hóa; nên sao lưu rồi cào lại để dữ liệu thô đồng nhất.")
    dong_theo_url = {khoa_url(d["URL_Goc"]): d for d in cac_dong if d.get("URL_Goc")}
    da_luu = set(dong_theo_url)
    so_cu, thong_ke, dung = len(cac_dong), Counter(), None
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
                max_pages=args.max_pages, gioi_han=con_lai, dong_theo_url=dong_theo_url,
                tom_tat=ket_qua, da_tai_chi_tiet=da_tai_chi_tiet,
            )
            ket_qua["moi"] = moi
            print(f"[{tu_khoa}] +{moi} tin mới; tổng lương bổ sung: {thong_ke['cap_nhat_luong']}", flush=True)
            if dung:
                print(f"Dừng toàn bộ: {dung}")
                break
    except KeyboardInterrupt:
        dung = "Ctrl+C"
        print("Đã dừng bằng Ctrl+C; đang lưu CSV.")
    finally:
        ghi_csv_mot_dong(cac_dong)
    print("Tóm tắt theo truy vấn")
    for tu_khoa, _, kq in tong_hop:
        print(f"  [{tu_khoa}] {kq['trang']} trang, {kq['moi']} tin mới, {kq['moi_tu_trang_2']} từ trang >= 2, "
              f"{kq['the_phu_hop']} thẻ phù hợp, {kq['ngoai_nhom']} thẻ ngoài nhóm")
    print(f"Tổng {sum(kq['trang'] for _, _, kq in tong_hop)} trang danh sách, "
          f"{sum(kq['moi_tu_trang_2'] for _, _, kq in tong_hop)} tin mới từ trang >= 2, "
          f"{sum(bool(nhom and kq['the_phu_hop']) for _, nhom, kq in tong_hop)} truy vấn kỹ năng có kết quả, "
          f"{sum(kq['ngoai_nhom'] for _, _, kq in tong_hop)} thẻ ngoài nhóm bị lọc")
    for _, _, kq in tong_hop:
        for headline in kq.get("headlines", []):
            print(f"Kết quả tìm kiếm: {headline}")
    for cot in doc_schema()["required"]:
        print(f"Ô trống {cot}: {sum(not d.get(cot) for d in cac_dong)}")
    print(f"Số lần DUNG: {sum(thong_ke[ma] for ma in DUNG)}")
    thieu_luong = sum(not d.get("Luong") for d in cac_dong)
    print(f"Tin mới: {len(cac_dong) - so_cu}; tổng: {len(cac_dong)}; lương trống: {thieu_luong}; "
          f"thống kê tải: {dict(thong_ke)}\nCSV: {DUONG_DAN_CSV}")
    return 130 if dung == "Ctrl+C" else 2 if dung else 0

if __name__ == "__main__":
    raise SystemExit(main())
