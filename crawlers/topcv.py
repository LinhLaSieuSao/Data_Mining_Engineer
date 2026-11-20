"""Cào HTML công khai của TopCV và xuất CSV theo schema của dự án."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers.base_crawler import (
    DUNG, THU_MUC_GOC, danh_dau_bat_dau, doc_csv, doc_schema, duoc_phep, kiem_thu_robot, tai_thu_lai, xuat_csv,
)
from crawlers.browser import duyet_trang_topcv


TRANG_CHU = "https://www.topcv.vn"
TEN_BOT = "ITEC3417-TopCVResearchBot/1.0 (academic project)"
DUONG_DAN_CSV = THU_MUC_GOC / "data" / "raw" / "raw_topcv.csv"
MA_TIN = re.compile(r"(?:/viec-lam/[^/]+/|/brand/[^/]+/tuyen-dung/[^/]+-j)(\d+)\.html")
NHAN_MO_TA = {
    "mô tả công việc", "mô tả", "chi tiết công việc",
    "job description", "job descriptions", "job details", "description",
}
NHAN_YEU_CAU = {
    "yêu cầu ứng viên", "yêu cầu công việc", "yêu cầu",
    "candidate requirements", "job requirements", "requirements",
}
NHAN_QUYEN_LOI = {
    "quyền lợi ứng viên", "quyền lợi", "phúc lợi",
    "benefits", "remuneration and benefits", "compensation & benefits",
}
NHAN_KY_NANG = {
    "kỹ năng cần có", "kỹ năng nên có", "kỹ năng",
    "required skills", "skills",
}
NHAN_DIA_DIEM = {
    "địa điểm làm việc", "địa điểm", "nơi làm việc",
    "address and time work", "location", "working location", "address",
}
CHECKPOINT = 10
GiaTriCot = str | list[str] | None


def la_url_topcv(url):
    try:
        phan = urlsplit(url)
    except ValueError:
        return False
    return phan.scheme == "https" and phan.netloc.casefold() in {"www.topcv.vn", "topcv.vn"}


def url_tin(href: object):
    if not isinstance(href, str) or not href.strip():
        return None, None
    try:
        phan = urlsplit(urljoin(TRANG_CHU, href))
    except ValueError:
        return None, None
    ma = MA_TIN.fullmatch(phan.path)
    if ma and la_url_topcv(phan.geturl()):
        return f"{TRANG_CHU}{phan.path}", ma[1]
    return None, None


def van_ban(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    return " ".join(tag.get_text(" ", strip=True).split()) or None


def nhan(tag: Tag | None) -> str:
    return (van_ban(tag) or "").casefold().rstrip(" :：")


def van_ban_khoi(tag: Tag) -> str:
    """Giữ dòng, mục và thứ tự của HTML, kể cả phần được thu gọn trên giao diện."""
    ban_sao = BeautifulSoup(str(tag), "html.parser")
    for nut in ban_sao.select("script, style, button, .box-group-button-apply"):
        nut.extract()
    for chuoi in ban_sao.find_all(string=True):
        if type(chuoi) is NavigableString:
            chuoi.replace_with(re.sub(r"\s+", " ", str(chuoi)))
    for br in ban_sao.select("br"):
        br.replace_with("\n")
    for khoi in ban_sao.select("div, p, li, h2, h3, h4, h5, h6"):
        khoi.insert_before("\n• " if khoi.name == "li" else "\n")
        khoi.insert_after("\n")
    dong = "\n".join(dong.strip() for dong in ban_sao.get_text().splitlines() if dong.strip())
    return re.sub(r"(?m)^•\n", "• ", dong)


def doc_danh_sach(soup: BeautifulSoup) -> dict[str, dict[str, str | None]]:
    """Đọc thẻ thuộc danh sách kết quả, gồm cả URL tin trên trang thương hiệu."""
    ket_qua: dict[str, dict[str, str | None]] = {}
    for the in soup.select(".job-list-search-result .job-item-search-result"):
        lien_ket = the.select_one("h3.title a[href]")
        if lien_ket is None:
            continue
        url, ma = url_tin(lien_ket.get("href"))
        if url is None or ma is None or ma in ket_qua:
            continue
        ngay = van_ban(the.select_one(".label-update"))
        ket_qua[ma] = {
            "URL_Goc": url,
            "Ma_Tin_Nguon": ma,
            "Tieu_De": van_ban(lien_ket.select_one("span[title]")) or van_ban(lien_ket),
            "Ten_Cong_Ty": van_ban(the.select_one(".company-name")) or van_ban(the.select_one("a.company")),
            "Dia_Diem": van_ban(the.select_one(".address:not(.label-update)")),
            "Luong": van_ban(the.select_one(".salary, .title-salary")),
            "Kinh_Nghiem": van_ban(the.select_one(".exp")),
            "Ngay_Dang": ngay if ngay and ngay.casefold().startswith("đăng ") else None,
        }
    return ket_qua


def ngay_dang_json_ld(soup: BeautifulSoup) -> str | None:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            du_lieu = json.loads(script.string or "")
        except ValueError:
            continue
        if isinstance(du_lieu, dict) and du_lieu.get("@type") == "JobPosting":
            ngay = du_lieu.get("datePosted")
            return ngay if isinstance(ngay, str) else None
    return None


def doc_chi_tiet(html: str | bytes) -> dict[str, GiaTriCot]:
    soup = BeautifulSoup(html, "html.parser")
    thong_tin: dict[str, str | None] = {}
    for hang in soup.select(".box-header-job .list-info__content, .box-job-information-general-info-list__item--content"):
        tieu_de = hang.select_one(".list-info__content__title, .box-job-information-general-info-list__item--content-title")
        gia_tri = hang.select_one(".list-info__content__desc, .box-job-information-general-info-list__item--content-desc")
        thong_tin[nhan(tieu_de)] = van_ban(gia_tri)

    cac_muc, yeu_cau, quyen_loi = [], [], []
    ky_nang: list[str] = []
    dia_diem: list[str | None] = []
    co_mo_ta = False
    cac_khoi = soup.select("#box-job-information-detail .box-job-information-detail-item")
    for khoi in cac_khoi:
        tieu_de = khoi.select_one(".box-job-information-detail-item__title--title")
        ten_muc = nhan(tieu_de)
        noi_dung = khoi.select(
            ":scope > .box-job-information-detail-item__text, :scope > .required-tags, "
            ":scope > .job-tags, :scope > .box-job-information-address-and-time-list"
        )
        cac_doan = [van_ban_khoi(doan) for doan in noi_dung]
        if not ten_muc or not any(cac_doan):
            continue
        muc = "\n".join(doan for doan in (van_ban(tieu_de), *cac_doan) if doan)
        cac_muc.append(muc)
        if ten_muc in NHAN_MO_TA:
            co_mo_ta = True
        if ten_muc in NHAN_YEU_CAU:
            yeu_cau.append(muc)
        if ten_muc in NHAN_QUYEN_LOI:
            quyen_loi.append(muc)

    for the in soup.select("#box-job-information-detail .required-tag__content"):
        if nhan(the.select_one(".required-tag__content--title")) in NHAN_KY_NANG:
            gia_tri = van_ban(the.select_one(".required-tag__content--desc")) or ""
            ky_nang.extend(ky.strip() for ky in gia_tri.split(",") if ky.strip())
    for the in soup.select("#box-job-information-detail .box-job-information-address-and-time-list__item"):
        if nhan(the.select_one("h3")) in NHAN_DIA_DIEM:
            gia_tri = the.select_one(".box-job-information-address-and-time-list__item--content")
            if gia_tri:
                dia_diem.extend(van_ban(khoi) for khoi in gia_tri.select("li") or [gia_tri])

    cong_ty = soup.select_one(".box-company-info-detail__header .name") or soup.select_one(".box-company-info__detail .name")
    return {
        "Tieu_De": van_ban(soup.select_one("h1.box-header-job__title")),
        "Ten_Cong_Ty": van_ban(cong_ty),
        "Dia_Diem": "\n".join(dict.fromkeys(dia for dia in dia_diem if dia)) or thong_tin.get("địa điểm") or thong_tin.get("location") or thong_tin.get("address"),
        "Luong": van_ban(soup.select_one(".box-header-job__salary--title")) or thong_tin.get("mức lương") or thong_tin.get("salary"),
        "Kinh_Nghiem": thong_tin.get("kinh nghiệm") or thong_tin.get("experience"),
        "Hinh_Thuc_Lam_Viec": thong_tin.get("hình thức làm việc") or thong_tin.get("working method") or thong_tin.get("work mode"),
        "Loai_Hop_Dong": thong_tin.get("loại hình làm việc") or thong_tin.get("loại hợp đồng") or thong_tin.get("employment type") or thong_tin.get("job type"),
        "Ngay_Dang": ngay_dang_json_ld(soup),
        "Mo_Ta_Cong_Viec": "\n\n".join(cac_muc) if co_mo_ta else None,
        "Yeu_Cau_Chi_Tiet": "\n\n".join(yeu_cau) or None,
        "Quyen_Loi": "\n\n".join(quyen_loi) or None,
        "Ky_Nang": list(dict.fromkeys(ky_nang)) or None,
    }


def tai_trang(session, url, rp=None):
    ma_tin = url_tin(url)[1]
    for _ in range(4):
        if not la_url_topcv(url) or rp is not None and not duoc_phep(rp, TRANG_CHU, url, TEN_BOT):
            print(f"URL ngoài phạm vi tải hoặc robots.txt không cho phép tại {url}")
            return None, "bi_cam"
        la_robots = urlsplit(url).path == "/robots.txt"
        try:
            r = session.get(url, timeout=15, allow_redirects=False)
        except (requests.Timeout, requests.ConnectionError):
            return None, "loi_tam_thoi"
        ma = r.status_code
        if ma in (401, 403, 429) or r.headers.get("cf-mitigated", "").casefold() == "challenge":
            print(f"TopCV từ chối hoặc yêu cầu xác minh tại {url} (HTTP {ma})")
            return None, "bi_chan"
        if r.is_redirect:
            try:
                dich = urljoin(url, r.headers["Location"])
            except ValueError:
                print(f"Địa chỉ chuyển hướng không hợp lệ tại {url}")
                return None, "bi_cam"
            if not la_url_topcv(dich):
                print(f"TopCV chuyển ra ngoài website tại {url}")
                return None, "bi_cam"
            duong_dan = urlsplit(dich).path
            if duong_dan.rstrip("/") in {"/dang-nhap", "/login", "/sign-in"}:
                print(f"TopCV yêu cầu đăng nhập tại {url}")
                return None, "bi_chan"
            if ma_tin and url_tin(dich)[1] != ma_tin:
                return None, "khong_ton_tai"
            if la_robots and duong_dan != "/robots.txt":
                return None, "bi_cam"
            if not (la_robots or ma_tin or duong_dan.startswith("/tim-viec-lam")):
                return None, "bi_cam"
            url = dich
            continue
        if ma == 200:
            dau_html = r.content[:20000].lower()
            if re.search(rb"<title[^>]*>\s*(?:just a moment|access denied|attention required|captcha)", dau_html):
                print(f"TopCV yêu cầu xác minh tại {url}")
                return None, "bi_chan"
            if la_robots:
                kieu = r.headers.get("Content-Type", "").partition(";")[0].strip().casefold()
                dau = dau_html.removeprefix(b"\xef\xbb\xbf").lstrip()
                if kieu in {"text/html", "application/xhtml+xml"} or dau.startswith(b"<"):
                    print(f"TopCV trả HTML khi tải robots.txt tại {url}")
                    return None, "bi_cam"
            return r.content, "ok"
        if ma in (404, 410):
            return None, "khong_ton_tai"
        if ma >= 500:
            return None, "loi_tam_thoi"
        print(f"TopCV trả HTTP {ma} tại {url}")
        return None, "bi_cam"
    return None, "bi_cam"


def tao_dong(
    the: Mapping[str, str | None],
    chi_tiet: Mapping[str, GiaTriCot],
    url_tim_kiem: str,
    tu_khoa: str | None,
    timestamp: str,
) -> dict[str, GiaTriCot]:
    dong: dict[str, GiaTriCot] = {
        **the,
        "Web": "topcv",
        "URL_Tim_Kiem": url_tim_kiem,
        "Tu_Khoa_Tim_Kiem": tu_khoa,
        "Timestamp": timestamp,
    }
    for cot, gia_tri in chi_tiet.items():
        if cot == "Ngay_Dang" and dong.get(cot):
            continue
        dong[cot] = gia_tri or dong.get(cot)
    return dong


def ghi_csv(duong_dan, cac_dong):
    """Dùng cùng định dạng ITviec, mỗi tin chiếm một dòng CSV vật lý."""
    xuat_csv(duong_dan, [
        {cot: gia_tri.replace("\r\n", r"\n").replace("\r", r"\n").replace("\n", r"\n")
         if isinstance(gia_tri, str) else gia_tri
         for cot, gia_tri in dong.items()}
        for dong in cac_dong
    ])


def url_tim_kiem(tu_khoa):
    tu_khoa = unicodedata.normalize("NFKD", tu_khoa.casefold().replace("đ", "d"))
    tu_khoa = "".join(ky_tu for ky_tu in tu_khoa if not unicodedata.combining(ky_tu))
    slug = re.sub(r"[^a-z0-9]+", "-", tu_khoa).strip("-")
    if not slug:
        raise ValueError("Từ khóa cần chứa ít nhất một chữ cái hoặc chữ số")
    return f"{TRANG_CHU}/tim-viec-lam-{slug}"


def cao_truy_van(url, tu_khoa, tai, args, cac_dong, da_luu, bat_buoc, thong_ke):
    for trang, soup, ma in duyet_trang_topcv(url, tai, args.max_pages):
        if ma != "ok" or soup is None:
            print(f"Lỗi tải danh sách ({ma}) tại {trang}")
            return ma
        truong_tu_khoa = soup.select_one("input#keyword[value]")
        gia_tri_tu_khoa = truong_tu_khoa.get("value") if truong_tu_khoa else None
        tu_khoa_trang = tu_khoa
        if not tu_khoa_trang and isinstance(gia_tri_tu_khoa, str):
            tu_khoa_trang = gia_tri_tu_khoa.strip() or None
        cac_the = doc_danh_sach(soup)
        print(f"{trang} — {len(cac_the)} tin", flush=True)
        if not cac_the:
            danh_sach = soup.select_one(".job-list-search-result")
            if danh_sach is None or danh_sach.select_one(".job-item-search-result") is not None:
                print("Không đọc được các thẻ việc làm từ HTML danh sách")
                return "loi_html"
        for ma_tin, the in cac_the.items():
            if ma_tin in da_luu:
                continue
            timestamp = danh_dau_bat_dau()
            html, ma = tai(the["URL_Goc"])
            if ma in (*DUNG, "bi_cam"):
                return ma
            if html is None:
                print(f"Bỏ qua tin {ma_tin} ({ma})")
                if ma != "khong_ton_tai":
                    thong_ke["loi_tai_chi_tiet"] += 1
                continue
            dong = tao_dong(the, doc_chi_tiet(html), trang, tu_khoa_trang, timestamp)
            thieu = [cot for cot in bat_buoc if not dong.get(cot)]
            if thieu:
                thong_ke["thieu_cot"] += 1
                print(f"Bỏ qua tin {ma_tin} vì thiếu {', '.join(thieu)}")
                continue
            cac_dong.append(dong)
            da_luu.add(ma_tin)
            thong_ke["tin_moi"] += 1
            if thong_ke["tin_moi"] % CHECKPOINT == 0:
                ghi_csv(args.output, cac_dong)
            if args.limit and thong_ke["tin_moi"] >= args.limit:
                return "dat_gioi_han"
    return "ok"


def main(argv=None):
    cli = argparse.ArgumentParser(description="Cào tin công khai trên TopCV vào CSV")
    nhom = cli.add_mutually_exclusive_group()
    nhom.add_argument("--keyword", action="append", help="Từ khóa tìm kiếm, có thể lặp. Mặc định lấy nhóm ngành trong keyword.json.")
    nhom.add_argument("--url", help="URL trang tìm việc TopCV đã có bộ lọc")
    cli.add_argument("--max-pages", type=int, default=2, help="Số trang tối đa mỗi truy vấn (mặc định 2, 0 là đến trang cuối)")
    cli.add_argument("--limit", type=int, default=0, help="Số tin mới tối đa trong một lần chạy (0 là không giới hạn)")
    cli.add_argument("--delay-min", type=float, default=2.0, help="Thời gian nghỉ tối thiểu giữa các request (giây, mặc định 2.0)")
    cli.add_argument("--delay-max", type=float, default=5.0, help="Thời gian nghỉ tối đa giữa các request (giây, mặc định 5.0)")
    cli.add_argument("--output", type=Path, default=DUONG_DAN_CSV, help="Đường dẫn CSV đầu ra")
    args = cli.parse_args(argv)
    if args.limit < 0 or args.max_pages < 0 or args.delay_min < 0 or args.delay_max < args.delay_min:
        cli.error("--limit, --max-pages, --delay-min phải >= 0 và --delay-max >= --delay-min")
    if args.url and (not la_url_topcv(args.url) or not urlsplit(args.url).path.startswith("/tim-viec-lam")):
        cli.error("--url phải là URL HTTPS của trang tìm việc TopCV")

    thong_ke = Counter()
    try:
        if args.url:
            truy_van = [(None, urldefrag(args.url).url)]
        else:
            tu_khoa = args.keyword or json.loads((THU_MUC_GOC / "keyword.json").read_text(encoding="utf-8"))["Nhom_Nghanh"]
            truy_van = [(tu.strip(), url_tim_kiem(tu)) for tu in tu_khoa]
        cac_dong = doc_csv(args.output)
        if any(dong["Web"] != "topcv" for dong in cac_dong):
            raise ValueError("CSV đầu ra đang chứa dữ liệu từ nguồn khác")
        schema = doc_schema()
        bat_buoc = [cot for cot in schema["required"] if "null" not in schema["properties"][cot]["type"]]
    except (OSError, ValueError) as loi:
        print(f"Dừng vì {loi}")
        return 2

    da_luu = {dong["Ma_Tin_Nguon"] or url_tin(dong["URL_Goc"])[1] for dong in cac_dong}
    ma_thoat = 0
    try:
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": TEN_BOT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            })

            def tai_robots(url):
                return tai_thu_lai(lambda dia_chi: tai_trang(session, dia_chi), url, thong_ke, khoang_nghi=(args.delay_min, args.delay_max))

            rp, ly_do = kiem_thu_robot(TRANG_CHU, [url for _, url in truy_van], TEN_BOT, tai_robots=tai_robots)
            if rp is None:
                print(f"Dừng vì {ly_do}")
                return 2

            def tai(url):
                return tai_thu_lai(lambda dia_chi: tai_trang(session, dia_chi, rp), url, thong_ke, khoang_nghi=(args.delay_min, args.delay_max))

            for tu_khoa, url in truy_van:
                ma = cao_truy_van(url, tu_khoa, tai, args, cac_dong, da_luu, bat_buoc, thong_ke)
                if ma == "dat_gioi_han":
                    break
                if ma != "ok":
                    ma_thoat = 2
                if ma in (*DUNG, "bi_cam"):
                    print(f"Dừng cào TopCV ({ma})")
                    break
    except KeyboardInterrupt:
        ma_thoat = 130
    finally:
        if thong_ke["tin_moi"]:
            ghi_csv(args.output, cac_dong)

    if ma_thoat == 0 and (thong_ke["thieu_cot"] or thong_ke["loi_tai_chi_tiet"]):
        ma_thoat = 2
    print(f"Đã lưu {thong_ke['tin_moi']} tin mới, bỏ qua {thong_ke['thieu_cot']} tin thiếu cột bắt buộc "
          f"và {thong_ke['loi_tai_chi_tiet']} tin lỗi tải chi tiết.")
    if thong_ke["tin_moi"]:
        print(f"CSV {args.output}")
    return ma_thoat


if __name__ == "__main__":
    raise SystemExit(main())
