"""Crawler VietnamWorks cho 5 chuyên ngành Data/AI trong keyword.json.

Theo quyết định của nhóm, crawler bỏ qua bước kiểm tra robots.txt.
Trang tìm kiếm dùng API JSON; trang chi tiết vẫn được mở để xác minh nội dung.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from crawlers import DUNG, danh_dau_bat_dau, doc_csv, doc_schema, khoa_url, tai_thu_lai, xuat_csv

GOC_DU_AN = Path(__file__).resolve().parent.parent
URL_GOC = "https://www.vietnamworks.com"
URL_TIM_KIEM = f"{URL_GOC}/jobs"
API_TIM_KIEM = "https://ms.vietnamworks.com/job-search/v1.0/search"
DUONG_DAN_CSV = GOC_DU_AN / "data" / "raw" / "raw_vietnamworks.csv"
DUONG_DAN_JSONL = GOC_DU_AN / "data" / "raw" / "raw_vietnamworks.jsonl"
DUONG_DAN_LOG = GOC_DU_AN / "data" / "raw" / "vietnamworks.log"
CAC_COT = doc_schema()["required"]
CHECKPOINT = 10
SO_TRANG_TOI_DA = 100
logger = logging.getLogger("vietnamworks")


class TrangBiChan(Exception):
    """Dùng để thoát ngay khi trang trả 403/429 hoặc hiện captcha."""


class JsonLogFormatter(logging.Formatter):
    """Ghi log tiến độ theo JSONL ra stderr và file log."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "type": "progress",
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }, ensure_ascii=False)


def doc_tu_khoa() -> list[str]:
    """Chỉ đọc 5 tên chuyên ngành; kỹ năng được lấy từ từng tin tuyển dụng."""
    with (GOC_DU_AN / "keyword.json").open(encoding="utf-8") as tep:
        cau_hinh = json.load(tep)
    return list(dict.fromkeys(
        tu_khoa.strip()
        for tu_khoa in cau_hinh["Nhom_Nghanh"]
        if isinstance(tu_khoa, str) and tu_khoa.strip()
    ))


def tao_url_tim_kiem(tu_khoa: str) -> str:
    """Tạo URL tìm kiếm theo dạng slug mà trang công khai đang dùng."""
    slug = re.sub(r"\s+", "-", tu_khoa.strip().lower())
    return f"{URL_TIM_KIEM}?q={quote_plus(slug)}"


def phan_loai_http(ma_http: int) -> str:
    """Phân loại phản hồi HTTP cho hàm retry của base crawler."""
    if ma_http in (401, 403, 429):
        return "bi_chan"
    if ma_http == 404:
        return "khong_ton_tai"
    if ma_http in (408, 425) or ma_http >= 500:
        return "loi_tam_thoi"
    if 200 <= ma_http < 400:
        return "ok"
    return "that_bai"


def phan_loai_loi(loi: Exception) -> str:
    """Chỉ xem timeout/lỗi kết nối là tạm thời; lỗi khác không retry."""
    if isinstance(loi, (PlaywrightTimeoutError, PlaywrightError, OSError)):
        return "loi_tam_thoi"
    return "that_bai"


def co_captcha(page) -> bool:
    """Nhận diện trang captcha để dừng, không tìm cách vượt qua."""
    try:
        noi_dung = page.locator("body").inner_text(timeout=3000).casefold()
    except PlaywrightError:
        return False
    return any(cum in noi_dung for cum in (
        "captcha", "verify you are human", "are you a robot", "xác minh bạn không phải robot",
    ))


def tai_trang_tim_kiem(page, url: str):
    """Mở trang tìm kiếm và bắt response POST JSON đã quan sát từ trình duyệt."""
    try:
        with page.expect_response(
            lambda phan_hoi: phan_hoi.url.split("?", 1)[0] == API_TIM_KIEM
            and phan_hoi.request.method == "POST",
            timeout=45_000,
        ) as response_info:
            phan_hoi_trang = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            if phan_hoi_trang is None:
                raise PlaywrightTimeoutError("Trang không trả response chính")
            if phan_hoi_trang.status in (401, 403, 429):
                raise TrangBiChan(f"HTTP {phan_hoi_trang.status}")
            if phan_hoi_trang.status >= 500:
                raise PlaywrightError(f"HTTP {phan_hoi_trang.status}")
        if co_captcha(page):
            return None, "bi_chan"
        response = response_info.value
        trang_thai = phan_loai_http(response.status)
        if trang_thai != "ok":
            return None, trang_thai
        payload = response.request.post_data_json
        du_lieu = response.json()
        return {"payload": payload, "du_lieu": du_lieu, "url": page.url}, "ok"
    except TrangBiChan:
        return None, "bi_chan"
    except PlaywrightTimeoutError as loi:
        logger.warning("Chờ API tìm kiếm quá hạn tại %s", url)
        return None, phan_loai_loi(loi)
    except PlaywrightError as loi:
        logger.warning("Lỗi trình duyệt khi mở tìm kiếm %s: %s", url, type(loi).__name__)
        return None, phan_loai_loi(loi)
    except (ValueError, json.JSONDecodeError) as loi:
        logger.warning("API tìm kiếm trả JSON không hợp lệ tại %s: %s", url, type(loi).__name__)
        return None, "that_bai"
    except Exception as loi:
        logger.warning("Lỗi không dự kiến ở trang tìm kiếm %s: %s", url, type(loi).__name__)
        return None, "that_bai"


def tai_trang_api(context, payload: dict, url_tham_chieu: str):
    """Tải trang API kế tiếp bằng payload gốc đã bắt từ trang thật."""
    try:
        response = context.request.post(
            API_TIM_KIEM,
            data=payload,
            headers={"Origin": URL_GOC, "Referer": url_tham_chieu},
            timeout=45_000,
        )
        trang_thai = phan_loai_http(response.status)
        if trang_thai != "ok":
            return None, trang_thai
        return response.json(), "ok"
    except PlaywrightTimeoutError as loi:
        logger.warning("Timeout khi tải trang API tiếp theo")
        return None, phan_loai_loi(loi)
    except (PlaywrightError, ValueError, json.JSONDecodeError) as loi:
        logger.warning("Lỗi API tìm kiếm tiếp theo: %s", type(loi).__name__)
        return None, phan_loai_loi(loi)
    except Exception as loi:
        logger.warning("Lỗi không dự kiến ở API tìm kiếm: %s", type(loi).__name__)
        return None, "that_bai"


def tai_trang_chi_tiet(page, url: str):
    """Mở chi tiết, chờ tiêu đề và mở các mục đang thu gọn."""
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        if response is None:
            return None, "loi_tam_thoi"
        trang_thai = phan_loai_http(response.status)
        if trang_thai != "ok":
            return None, trang_thai
        if co_captcha(page):
            return None, "bi_chan"
        page.locator("h1").first.wait_for(state="visible", timeout=15_000)
        # Mở phần mô tả và Job Information để đọc đủ nội dung/nhãn hiển thị.
        for _ in range(5):
            nut_xem_them = page.get_by_role("button", name="View more", exact=True)
            if not nut_xem_them.count():
                break
            nut_xem_them.first.click(timeout=10_000)
        return page.content(), "ok"
    except PlaywrightTimeoutError as loi:
        logger.warning("Không thấy tiêu đề chi tiết hoặc hết thời gian: %s", url)
        return None, phan_loai_loi(loi)
    except PlaywrightError as loi:
        logger.warning("Lỗi trình duyệt ở trang chi tiết %s: %s", url, type(loi).__name__)
        return None, phan_loai_loi(loi)
    except Exception as loi:
        logger.warning("Lỗi không dự kiến ở trang chi tiết %s: %s", url, type(loi).__name__)
        return None, "that_bai"


def lay_noi_dung_muc(soup: BeautifulSoup, ten_muc: str) -> str | None:
    """Lấy nội dung các mục theo heading thật trên trang chi tiết."""
    heading = next((
        muc for muc in soup.find_all("h2")
        if muc.get_text(" ", strip=True).casefold() == ten_muc.casefold()
    ), None)
    if heading is None or heading.parent is None:
        return None
    cac_doan = []
    for phan_tu in heading.next_siblings:
        if getattr(phan_tu, "name", None) in ("h1", "h2", "h3"):
            break
        # Bỏ banner gợi ý phụ nằm xen giữa heading và nội dung mô tả.
        if getattr(phan_tu, "select_one", None) and phan_tu.select_one(".title-banner-c"):
            continue
        text = phan_tu.get_text("\n", strip=True) if getattr(phan_tu, "get_text", None) else ""
        if text and text not in cac_doan:
            cac_doan.append(text)
    return "\n".join(cac_doan) or None


def lay_thong_tin_cong_viec(soup: BeautifulSoup) -> dict[str, str]:
    """Đọc cặp nhãn/giá trị trong mục Job Information đã mở."""
    heading = next((
        muc for muc in soup.find_all("h2")
        if muc.get_text(" ", strip=True).casefold() == "job information"
    ), None)
    if heading is None or heading.parent is None:
        return {}
    thong_tin = {}
    for nhan in heading.parent.find_all("label"):
        gia_tri = nhan.find_next_sibling("p")
        ten = nhan.get_text(" ", strip=True).upper()
        text = gia_tri.get_text(" ", strip=True) if gia_tri else ""
        if ten and text:
            thong_tin[ten] = text
    return thong_tin


def lay_dia_diem(job: dict) -> str | None:
    """Lấy tên địa điểm theo thứ tự hiển thị trong kết quả VietnamWorks."""
    dia_diem = []
    for muc in job.get("workingLocations") or []:
        ten = muc.get("cityName") or muc.get("cityNameVI")
        if isinstance(ten, str) and ten.strip() and ten.strip() not in dia_diem:
            dia_diem.append(ten.strip())
    return ", ".join(dia_diem) if dia_diem else None


def tach_chi_tiet(job: dict, html_chi_tiet: str, url_tim_kiem: str,
                   tu_khoa: str, timestamp: str) -> dict | None:
    """Ánh xạ nội dung chi tiết theo schema, giữ cả mô tả tổng và mục tách riêng."""
    soup = BeautifulSoup(html_chi_tiet, "lxml")
    the_tieu_de = soup.find("h1")
    tieu_de = the_tieu_de.get_text(" ", strip=True) if the_tieu_de else None
    thong_tin = lay_thong_tin_cong_viec(soup)
    dia_diem = lay_dia_diem(job)
    mo_ta_nguon = lay_noi_dung_muc(soup, "Job description")
    yeu_cau_nguon = lay_noi_dung_muc(soup, "Job requirements")
    quyen_loi_nguon = lay_noi_dung_muc(soup, "What We Can Offer")
    cac_muc = []
    for ten_muc, noi_dung in (
        ("Job description", mo_ta_nguon),
        ("Job requirements", yeu_cau_nguon),
        ("What We Can Offer", quyen_loi_nguon),
    ):
        if noi_dung:
            cac_muc.append(f"{ten_muc}\n{noi_dung}")
    mo_ta = "\n\n".join(cac_muc) or None
    ten_cong_ty = job.get("companyName")
    if not all((tieu_de, ten_cong_ty, dia_diem, mo_ta, job.get("jobUrl"), timestamp)):
        return None

    cac_ky_nang = [
        muc["skillName"] for muc in job.get("skills") or []
        if isinstance(muc, dict) and isinstance(muc.get("skillName"), str) and muc["skillName"].strip()
    ]
    url_goc = job["jobUrl"]
    if urlsplit(url_goc).hostname not in ("www.vietnamworks.com", "vietnamworks.com"):
        return None
    ma_tin = job.get("jobId")
    return {
        "Web": "vietnamworks",
        "Ma_Tin_Nguon": str(ma_tin) if ma_tin is not None else None,
        "URL_Goc": url_goc,
        "URL_Tim_Kiem": url_tim_kiem,
        "Tu_Khoa_Tim_Kiem": tu_khoa,
        "Timestamp": timestamp,
        "Tieu_De": tieu_de,
        "Ten_Cong_Ty": ten_cong_ty,
        "Dia_Diem": dia_diem,
        "Luong": job.get("prettySalary") or None,
        "Kinh_Nghiem": thong_tin.get("YEAR OF EXPERIENCE"),
        "Hinh_Thuc_Lam_Viec": None,
        "Loai_Hop_Dong": thong_tin.get("WORKING TYPE"),
        "Ngay_Dang": thong_tin.get("POSTED DATE") or job.get("onlineOnText") or None,
        "Mo_Ta_Cong_Viec": mo_ta,
        "Yeu_Cau_Chi_Tiet": f"Job requirements\n{yeu_cau_nguon}" if yeu_cau_nguon else None,
        "Quyen_Loi": f"What We Can Offer\n{quyen_loi_nguon}" if quyen_loi_nguon else None,
        "Ky_Nang": json.dumps(cac_ky_nang, ensure_ascii=False) if cac_ky_nang else None,
    }


def ma_hoa_ban_ghi(ban_ghi: dict) -> str:
    """Mã hóa đúng thứ tự trường hiện tại của schema thành JSONL."""
    dong_theo_schema = {cot: ban_ghi.get(cot) for cot in CAC_COT}
    return json.dumps(dong_theo_schema, ensure_ascii=False, separators=(",", ":"))


def khoa_ban_ghi(ban_ghi: dict) -> tuple:
    """Tạo khóa chống trùng theo cả ID nguồn và URL đã chuẩn hóa."""
    return (str(ban_ghi.get("Ma_Tin_Nguon") or ""), khoa_url(ban_ghi["URL_Goc"]))


def doc_jsonl(duong_dan: Path) -> list[dict]:
    """Nạp JSONL cũ để khôi phục checkpoint và chống trùng sau khi ngắt."""
    if not duong_dan.exists():
        return []
    cac_dong = []
    with duong_dan.open(encoding="utf-8") as tep:
        for so_dong, dong in enumerate(tep, 1):
            try:
                ban_ghi = json.loads(dong)
                if isinstance(ban_ghi, dict) and ban_ghi.get("URL_Goc"):
                    if list(ban_ghi) != CAC_COT:
                        raise ValueError(
                            f"JSONL {duong_dan} dùng schema khác. Hãy sao lưu/đổi tên file cũ "
                            "trước khi chạy với schema.json hiện tại."
                        )
                    cac_dong.append(ban_ghi)
            except json.JSONDecodeError:
                logger.warning("Bỏ qua dòng JSONL lỗi số %s", so_dong)
    return cac_dong


def ghi_jsonl_moi(tep, ban_ghi: dict) -> None:
    """Append một bản ghi JSONL và flush ngay để giữ checkpoint khi bị ngắt."""
    tep.write(ma_hoa_ban_ghi(ban_ghi) + "\n")
    tep.flush()


def ghi_ban_ghi_stdout(ban_ghi: dict) -> None:
    """In đúng JSONL của tin mới ra stdout, không in log xen vào."""
    print(ma_hoa_ban_ghi(ban_ghi), flush=True)


def cau_hinh_log() -> None:
    """Đưa log JSON tiến độ ra stderr và file log, giữ stdout thuần JSONL."""
    DUONG_DAN_LOG.parent.mkdir(parents=True, exist_ok=True)
    formatter = JsonLogFormatter()
    logger.handlers.clear()
    for handler in (logging.StreamHandler(), logging.FileHandler(DUONG_DAN_LOG, encoding="utf-8")):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def ghep_checkpoint(cac_dong_csv: list[dict], cac_dong_jsonl: list[dict]) -> list[dict]:
    """Gộp checkpoint CSV/JSONL, ưu tiên bản ghi đầu tiên theo URL và ID."""
    ket_qua = []
    id_da_co = set()
    url_da_co = set()
    for ban_ghi in cac_dong_csv + cac_dong_jsonl:
        url = ban_ghi.get("URL_Goc")
        if not url:
            continue
        id_tin = str(ban_ghi.get("Ma_Tin_Nguon") or "")
        khoa_url_tin = khoa_url(url)
        if (id_tin and id_tin in id_da_co) or khoa_url_tin in url_da_co:
            continue
        ket_qua.append(ban_ghi)
        if id_tin:
            id_da_co.add(id_tin)
        url_da_co.add(khoa_url_tin)
    return ket_qua


def chay(tu_khoa_chi_dinh: str | None = None, so_trang: int | None = None,
         gioi_han: int | None = None) -> None:
    """Cào tuần tự, in JSONL trực tiếp và lưu CSV/JSONL theo checkpoint."""
    cau_hinh_log()
    tu_khoa_day_du = doc_tu_khoa()
    tu_khoa_list = [tu_khoa_chi_dinh] if tu_khoa_chi_dinh else tu_khoa_day_du
    if so_trang is not None and so_trang < 1:
        raise ValueError("--so-trang phải lớn hơn hoặc bằng 1")
    if gioi_han is not None and gioi_han < 1:
        raise ValueError("--gioi-han phải lớn hơn hoặc bằng 1")

    try:
        cac_dong_csv = doc_csv(DUONG_DAN_CSV)
    except ValueError as loi:
        raise ValueError(
            f"CSV checkpoint {DUONG_DAN_CSV} không khớp schema.json hiện tại. "
            "Hãy sao lưu/đổi tên CSV cũ trước khi chạy để tránh mất dữ liệu."
        ) from loi
    cac_dong_jsonl = doc_jsonl(DUONG_DAN_JSONL)
    cac_dong = ghep_checkpoint(cac_dong_csv, cac_dong_jsonl)
    da_luu_id = {str(dong.get("Ma_Tin_Nguon")) for dong in cac_dong if dong.get("Ma_Tin_Nguon")}
    da_luu_url = {khoa_url(dong["URL_Goc"]) for dong in cac_dong if dong.get("URL_Goc")}
    jsonl_da_co = {khoa_ban_ghi(dong) for dong in cac_dong_jsonl}

    # Nếu JSONL chưa tồn tại, nối các dòng CSV cũ để hai đầu ra cùng checkpoint.
    DUONG_DAN_JSONL.parent.mkdir(parents=True, exist_ok=True)
    tep_jsonl = DUONG_DAN_JSONL.open("a", encoding="utf-8", newline="\n")
    for dong in cac_dong:
        if khoa_ban_ghi(dong) not in jsonl_da_co:
            ghi_jsonl_moi(tep_jsonl, dong)
            jsonl_da_co.add(khoa_ban_ghi(dong))

    thong_ke = Counter()
    theo_tu_khoa = {tu_khoa: Counter() for tu_khoa in tu_khoa_list}
    so_moi = 0
    thoi_diem_bat_dau = time.monotonic()
    dung_crawler = False
    logger.info("Bắt đầu cào %s từ khóa; đã có %s tin trong checkpoint", len(tu_khoa_list), len(cac_dong))

    browser = None
    context = None
    with sync_playwright() as playwright:
        try:
            # Headed + User-Agent mặc định là cấu hình đã truy cập được khi khảo sát.
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
            page = context.new_page()
            for vi_tri_tu_khoa, tu_khoa in enumerate(tu_khoa_list, 1):
                url_tim_kiem = tao_url_tim_kiem(tu_khoa)
                payload_mau = None
                du_lieu_trang = None
                trang_hien_tai = 0
                trang_da_gap = set()
                while True:
                    if trang_hien_tai == 0:
                        ket_qua, trang_thai = tai_thu_lai(
                            lambda url: tai_trang_tim_kiem(page, url),
                            url_tim_kiem,
                            thong_ke,
                            khoang_nghi=(3.0, 6.0),
                        )
                        if trang_thai in DUNG:
                            logger.error("Dừng khi mở danh sách: từ khóa %s, status %s", tu_khoa, trang_thai)
                            dung_crawler = True
                            break
                        if trang_thai != "ok" or not ket_qua:
                            thong_ke["loi"] += 1
                            theo_tu_khoa[tu_khoa]["loi"] += 1
                            logger.warning("Từ khóa %s lỗi ở trang 1: %s", tu_khoa, trang_thai)
                            break
                        payload_mau = ket_qua["payload"]
                        du_lieu_trang = ket_qua["du_lieu"]
                        url_tim_kiem = ket_qua["url"]
                    else:
                        payload = dict(payload_mau)
                        payload["page"] = trang_hien_tai
                        ket_qua, trang_thai = tai_thu_lai(
                            lambda _url: tai_trang_api(context, payload, url_tim_kiem),
                            url_tim_kiem,
                            thong_ke,
                            khoang_nghi=(3.0, 6.0),
                        )
                        if trang_thai in DUNG:
                            logger.error("Dừng khi tải API danh sách trang %s: %s", trang_hien_tai + 1, trang_thai)
                            dung_crawler = True
                            break
                        if trang_thai != "ok" or not ket_qua:
                            thong_ke["loi"] += 1
                            theo_tu_khoa[tu_khoa]["loi"] += 1
                            logger.warning("Từ khóa %s lỗi ở trang %s: %s", tu_khoa, trang_hien_tai + 1, trang_thai)
                            break
                        du_lieu_trang = ket_qua

                    metadata = du_lieu_trang.get("meta") or {}
                    danh_sach_job = du_lieu_trang.get("data") or []
                    ids_trang = tuple(str(job.get("jobId") or job.get("jobUrl")) for job in danh_sach_job)
                    if not danh_sach_job or ids_trang in trang_da_gap:
                        logger.info("Hết dữ liệu/lặp trang: từ khóa %s trang %s", tu_khoa, trang_hien_tai + 1)
                        break
                    trang_da_gap.add(ids_trang)
                    tong_trang = min(int(metadata.get("nbPages") or 0), SO_TRANG_TOI_DA)
                    if so_trang is not None:
                        tong_trang = min(tong_trang, so_trang)
                    logger.info(
                        "Từ khóa %s/%s; trang %s/%s; %s tin; tổng đã lưu %s",
                        vi_tri_tu_khoa, len(tu_khoa_list), trang_hien_tai + 1,
                        tong_trang, len(danh_sach_job), len(cac_dong),
                    )

                    for vi_tri_job, job in enumerate(danh_sach_job, 1):
                        url_chi_tiet = job.get("jobUrl") or ""
                        ma_tin = str(job.get("jobId") or "")
                        khoa_url_tin = khoa_url(url_chi_tiet) if url_chi_tiet else None
                        if (ma_tin and ma_tin in da_luu_id) or (khoa_url_tin and khoa_url_tin in da_luu_url):
                            thong_ke["trung"] += 1
                            theo_tu_khoa[tu_khoa]["trung"] += 1
                            logger.info(
                                "Từ khóa %s/%s; trang %s; tin %s/%s; trạng thái trùng; URL %s; tổng %s",
                                vi_tri_tu_khoa, len(tu_khoa_list), trang_hien_tai + 1,
                                vi_tri_job, len(danh_sach_job), url_chi_tiet, len(cac_dong),
                            )
                            continue
                        if gioi_han is not None and so_moi >= gioi_han:
                            dung_crawler = True
                            break
                        timestamp = danh_dau_bat_dau()
                        html_chi_tiet, trang_thai = tai_thu_lai(
                            lambda url: tai_trang_chi_tiet(page, url),
                            url_chi_tiet,
                            thong_ke,
                            khoang_nghi=(2.0, 5.0),
                        )
                        if trang_thai in DUNG:
                            logger.error("Dừng do 403/429/captcha ở %s", url_chi_tiet)
                            dung_crawler = True
                            break
                        if trang_thai != "ok" or not html_chi_tiet:
                            thong_ke["loi"] += 1
                            theo_tu_khoa[tu_khoa]["loi"] += 1
                            logger.warning(
                                "Từ khóa %s/%s; trang %s; tin %s/%s; trạng thái lỗi %s; URL %s; tổng %s",
                                vi_tri_tu_khoa, len(tu_khoa_list), trang_hien_tai + 1,
                                vi_tri_job, len(danh_sach_job), trang_thai, url_chi_tiet, len(cac_dong),
                            )
                            continue
                        try:
                            ban_ghi = tach_chi_tiet(job, html_chi_tiet, url_tim_kiem, tu_khoa, timestamp)
                            if ban_ghi is None:
                                thong_ke["loi"] += 1
                                theo_tu_khoa[tu_khoa]["loi"] += 1
                                logger.warning("Bỏ tin thiếu trường bắt buộc: %s", url_chi_tiet)
                                continue
                            cac_dong.append(ban_ghi)
                            if ma_tin:
                                da_luu_id.add(ma_tin)
                            da_luu_url.add(khoa_url(ban_ghi["URL_Goc"]))
                            ghi_jsonl_moi(tep_jsonl, ban_ghi)
                            ghi_ban_ghi_stdout(ban_ghi)
                            so_moi += 1
                            thong_ke["moi"] += 1
                            theo_tu_khoa[tu_khoa]["moi"] += 1
                            logger.info(
                                "Từ khóa %s/%s; trang %s; tin %s/%s; trạng thái mới; URL %s; tổng %s",
                                vi_tri_tu_khoa, len(tu_khoa_list), trang_hien_tai + 1,
                                vi_tri_job, len(danh_sach_job), url_chi_tiet, len(cac_dong),
                            )
                            if so_moi % CHECKPOINT == 0:
                                xuat_csv(DUONG_DAN_CSV, cac_dong)
                        except Exception:
                            thong_ke["loi"] += 1
                            theo_tu_khoa[tu_khoa]["loi"] += 1
                            logger.exception("Lỗi xử lý tin; tiếp tục: %s", url_chi_tiet)
                    if dung_crawler:
                        break
                    if trang_hien_tai + 1 >= tong_trang:
                        break
                    trang_hien_tai += 1
                if dung_crawler:
                    break
        except KeyboardInterrupt:
            logger.warning("Nhận Ctrl+C; lưu checkpoint hiện có rồi dừng")
        finally:
            try:
                xuat_csv(DUONG_DAN_CSV, cac_dong)
            finally:
                tep_jsonl.close()
                if context:
                    context.close()
                if browser:
                    browser.close()

    tong_giay = time.monotonic() - thoi_diem_bat_dau
    logger.info(
        "Kết thúc: mới=%s trùng=%s lỗi=%s tổng_lưu=%s thời_gian_giây=%.1f theo_từ_khóa=%s",
        thong_ke["moi"], thong_ke["trung"], thong_ke["loi"], len(cac_dong), tong_giay,
        {tu_khoa: dict(so_lieu) for tu_khoa, so_lieu in theo_tu_khoa.items()},
    )
    if len(cac_dong) < 800:
        logger.warning("Tổng số tin đang có là %s, dưới mục tiêu tối thiểu 800 tin thô", len(cac_dong))


def tao_bo_tham_so() -> argparse.ArgumentParser:
    """Định nghĩa tham số demo, không tham số thì chạy đủ từ khóa."""
    parser = argparse.ArgumentParser(description="Cào tin tuyển dụng VietnamWorks theo keyword.json")
    parser.add_argument("--tu-khoa", help="Chỉ cào một từ khóa có trong keyword.json")
    parser.add_argument("--so-trang", type=int, help="Giới hạn số trang cho mỗi từ khóa")
    parser.add_argument("--gioi-han", type=int, help="Giới hạn số tin mới trong lần chạy")
    return parser


def main() -> None:
    """Kiểm tra tham số rồi chạy crawler."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = tao_bo_tham_so()
    args = parser.parse_args()
    if args.tu_khoa:
        danh_sach = doc_tu_khoa()
        tu_khoa_chuan = next((muc for muc in danh_sach if muc.casefold() == args.tu_khoa.casefold()), None)
        if tu_khoa_chuan is None:
            parser.error("--tu-khoa phải trùng một mục trong keyword.json")
        args.tu_khoa = tu_khoa_chuan
    try:
        chay(args.tu_khoa, args.so_trang, args.gioi_han)
    except ValueError as loi:
        parser.error(str(loi))


if __name__ == "__main__":
    main()
