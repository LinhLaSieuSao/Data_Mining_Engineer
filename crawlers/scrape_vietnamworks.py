"""Crawler VietnamWorks, ánh xạ nội dung trang chi tiết vào schema dùng chung.

Tìm theo tên vị trí để tin sát phân khúc Data/AI; kỹ năng phổ biến như Excel,
AWS hay Replication dễ kéo về nhiều tin ngoài ngành nên dành cho bước làm sạch.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from crawlers import (
    DUNG,
    danh_dau_bat_dau,
    doc_csv,
    doc_schema,
    khoa_url,
    tai_thu_lai,
    xuat_csv,
)

GOC = Path(__file__).resolve().parent.parent
HOST = "https://www.vietnamworks.com"
API = "https://ms.vietnamworks.com/job-search/v1.0/search"
CSV = GOC / "data" / "raw" / "raw_vietnamworks.csv"
JSON = GOC / "data" / "raw" / "raw_vietnamworks.json"
COT = doc_schema()["required"]
CHECKPOINT = 10

# Selector dựa trên heading, thuộc tính name và văn bản đã quan sát trên trang.
SELECTOR_TIEU_DE = 'h1[name="title"]'  # Tiêu đề tin đang xem.
SELECTOR_CONG_TY = 'a[name="label"][href*="/nha-tuyen-dung/"]'  # Công ty trong thẻ hồ sơ tin.
SELECTOR_NHAN_LUONG = 'span[name="label"]'  # Nhãn lương trong khối tiêu đề.
SELECTOR_NHAN_THONG_TIN = 'label[name="label"]'  # Nhãn của từng dòng thông tin việc làm.
SELECTOR_GIA_TRI_THONG_TIN = "xpath=following-sibling::p[@name='paragraph'][1]"  # Giá trị cùng dòng thông tin.
SELECTOR_THE_KY_NANG = 'button.btn-default.btn-sm.clickable[aria-label]'  # Từng thẻ kỹ năng.
SELECTOR_BANNER_GOI_Y = '.title-banner-c'  # Banner gợi ý ứng viên, không thuộc nội dung JD.
SELECTOR_KHUNG_TIN = "xpath=ancestor::div[.//h2[normalize-space()='Địa điểm làm việc']][1]"  # Nội dung tin, neo từ heading mô tả.
SELECTOR_H2 = "h2"  # Heading các mục của tin.
SELECTOR_PARENT = "xpath=.."  # Container trực tiếp của heading.
SELECTOR_KHOI_TIEU_DE = "xpath=ancestor::div[.//span[@name='label']][1]"  # Card chứa tiêu đề và lương.
SELECTOR_CAPTCHA = (
    'iframe[src*="captcha" i], iframe[title*="captcha" i], '
    '.g-recaptcha, #captcha, [data-sitekey]'
)  # Tín hiệu captcha cụ thể.
TEN_NUT_XEM_THEM = "Xem thêm"  # Tên nút mở rộng mục.
SELECTOR_NUT_VA_ROLE = 'button,[role="button"]'  # Nút không thuộc văn bản trích xuất.
TEN_HEADING = (
    "Mô tả công việc", "Yêu cầu công việc", "Các phúc lợi dành cho bạn",
    "Thông tin việc làm", "Địa điểm làm việc",
)
NHAN_THONG_TIN_BIET = frozenset({
    "ngày đăng", "cấp bậc", "ngành nghề", "kỹ năng", "lĩnh vực",
    "ngôn ngữ trình bày hồ sơ", "số năm kinh nghiệm tối thiểu", "quốc tịch",
    "trình độ học vấn tối thiểu", "giới tính", "độ tuổi mong muốn",
    "tình trạng hôn nhân", "số lượng tuyển dụng", "ngày làm việc",
    "giờ làm việc", "loại hình làm việc", "hình thức làm việc",
    "loại hợp đồng", "loại hình công việc",
})


def log(thong_diep: str) -> None:
    """Ghi tiến độ UTF-8 vào stderr."""
    print(thong_diep, file=sys.stderr, flush=True)


def doc_tu_khoa() -> list[str]:
    """Chỉ đọc nhóm ngành để tìm kiếm; nhóm kỹ năng dùng ở bước làm sạch."""
    with (GOC / "keyword.json").open(encoding="utf-8") as tep:
        cau_hinh = json.load(tep)
    danh_sach = cau_hinh["Nhom_Nghanh"]
    return list(dict.fromkeys(
        muc.strip() for muc in danh_sach
        if isinstance(muc, str) and muc.strip()
    ))


def url_tim_kiem(tu_khoa: str) -> str:
    """Tạo URL tìm kiếm từ khóa theo slug của website."""
    slug = re.sub(r"\s+", "-", tu_khoa.strip().lower())
    return f"{HOST}/jobs?q={quote(slug, safe='-')}"


def phan_loai_http(ma: int) -> str:
    """Đổi mã HTTP sang trạng thái mà base crawler hiểu."""
    if ma in (403, 429):
        return "bi_chan"
    if ma == 404:
        return "khong_ton_tai"
    if ma == 408 or ma == 425 or ma >= 500:
        return "loi_tam_thoi"
    return "ok" if 200 <= ma < 400 else "that_bai"


def co_captcha(page) -> bool:
    """Chỉ nhận diện tín hiệu captcha cụ thể, không quét nội dung tin."""
    if page.locator(SELECTOR_CAPTCHA).count():
        return True
    tieu_de = page.title().casefold()
    return any(cum in tieu_de for cum in (
        "verify you are human", "access denied", "security check",
    ))


def tai_danh_sach(page, url: str):
    """Mở tìm kiếm động và lấy đúng request/response API đầu tiên."""
    try:
        with page.expect_response(
            lambda r: r.url.split("?", 1)[0] == API and r.request.method == "POST",
            timeout=45_000,
        ) as cho_api:
            trang = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            if trang is None:
                return None, "loi_tam_thoi"
            trang_thai = phan_loai_http(trang.status)
            if trang_thai != "ok":
                return None, trang_thai
            if co_captcha(page):
                return None, "bi_chan"
        phan_hoi = cho_api.value
        trang_thai = phan_loai_http(phan_hoi.status)
        if trang_thai != "ok":
            return None, trang_thai
        return {
            "payload": phan_hoi.request.post_data_json,
            "data": phan_hoi.json(),
            "url": page.url,
        }, "ok"
    except PlaywrightTimeoutError:
        return None, "loi_tam_thoi"
    except (PlaywrightError, ValueError, json.JSONDecodeError):
        return None, "that_bai"


def tai_trang_api(context, payload: dict, referer: str):
    """Tải một trang API kế tiếp; retry điều tiết các lần gọi tải."""
    try:
        response = context.request.post(
            API,
            data=payload,
            headers={"Origin": HOST, "Referer": referer,
                     "Accept-Language": "vi-VN,vi;q=0.9"},
            timeout=45_000,
        )
        trang_thai = phan_loai_http(response.status)
        return (response.json(), "ok") if trang_thai == "ok" else (None, trang_thai)
    except PlaywrightTimeoutError:
        return None, "loi_tam_thoi"
    except (PlaywrightError, ValueError, json.JSONDecodeError):
        return None, "that_bai"


def duyet_tin(page, context, tu_khoa: str, so_trang: int | None, thong_ke):
    """Yield từng trang; dùng nbPages nếu có, nếu thiếu dò đến trang rỗng/lặp."""
    tim_kiem = url_tim_kiem(tu_khoa)
    with redirect_stdout(sys.stderr):
        ket_qua, trang_thai = tai_thu_lai(
            lambda _url: tai_danh_sach(page, tim_kiem), tim_kiem, thong_ke,
        )
    if trang_thai != "ok" or not ket_qua:
        yield tim_kiem, None, 0, trang_thai
        return
    payload = ket_qua["payload"]
    du_lieu = ket_qua["data"]
    tim_kiem = ket_qua["url"]
    da_gap = set()
    so_trang_da_doc = 0
    while True:
        jobs = du_lieu.get("data") or []
        chu_ky = tuple(str(j.get("jobId") or j.get("jobUrl")) for j in jobs)
        if not jobs or chu_ky in da_gap:
            break
        da_gap.add(chu_ky)
        so_trang_da_doc += 1
        yield tim_kiem, jobs, so_trang_da_doc, "ok"
        meta = du_lieu.get("meta") or {}
        tong = meta.get("nbPages")
        try:
            if tong is not None and so_trang_da_doc >= int(tong):
                break
        except (TypeError, ValueError):
            pass
        if so_trang is not None and so_trang_da_doc >= so_trang:
            break
        payload = dict(payload, page=so_trang_da_doc)
        with redirect_stdout(sys.stderr):
            du_lieu, trang_thai = tai_thu_lai(
                lambda _url: tai_trang_api(context, payload, tim_kiem),
                tim_kiem, thong_ke,
            )
        if trang_thai != "ok" or not du_lieu:
            yield tim_kiem, None, so_trang_da_doc + 1, trang_thai
            break


def url_tieng_viet(url: str) -> str:
    """Đổi hậu tố trang chi tiết sang biến thể tiếng Việt -jv."""
    return re.sub(r"-j[dv](?=/?(?:\?|$))", "-jv", url, flags=re.I)


def tai_chi_tiet(page, url: str):
    """Mở trang -jv, chờ heading và chỉ mở rộng đúng nút Xem thêm."""
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        if response is None:
            return None, "loi_tam_thoi"
        trang_thai = phan_loai_http(response.status)
        if trang_thai != "ok":
            return None, trang_thai
        if co_captcha(page):
            return None, "bi_chan"
        page.locator(SELECTOR_TIEU_DE).first.wait_for(state="visible", timeout=20_000)
        try:
            muc_heading(page, "Mô tả công việc").wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeoutError:
            log(f"Không tìm thấy heading 'Mô tả công việc' sau khi chờ: {url}")
            return None, "that_bai"
        for ten_muc in TEN_HEADING:
            heading = muc_heading(page, ten_muc)
            if heading.count():
                nut = heading.locator(SELECTOR_PARENT).get_by_role(
                    "button", name=TEN_NUT_XEM_THEM, exact=True,
                )
                if nut.count() and nut.first.is_visible():
                    nut.first.click(timeout=5_000)
        return True, "ok"
    except PlaywrightTimeoutError as loi:
        log(f"Timeout khi tải hoặc chờ DOM: {type(loi).__name__}: {url}")
        return None, "loi_tam_thoi"
    except PlaywrightError as loi:
        log(f"Lỗi điều hướng/DOM: {type(loi).__name__}: {url}")
        return None, "loi_dieu_huong"


def muc_heading(page, ten_muc: str):
    """Chọn đúng heading tiếng Việt, không phụ thuộc vị trí trong trang."""
    return page.get_by_role("heading", name=ten_muc, exact=True).first


def noi_dung_muc(page, ten_muc: str, bao_gom_heading: bool = True) -> str | None:
    """Lấy nguyên văn mục theo heading; có thể bỏ heading khỏi giá trị."""
    heading = muc_heading(page, ten_muc)
    if not heading.count():
        return None
    try:
        return heading.locator(SELECTOR_PARENT).evaluate("""(e, options) => {
          const copy = e.cloneNode(true);
          copy.querySelectorAll(options.buttonSelector).forEach(n => n.remove());
          if (!options.baoGomHeading) copy.querySelector(options.headingSelector)?.remove();
          return copy.innerText.trim() || null;
        }""", {
            "baoGomHeading": bao_gom_heading,
            "buttonSelector": SELECTOR_NUT_VA_ROLE,
            "headingSelector": SELECTOR_H2,
        })
    except PlaywrightError:
        return None


def toan_van_mo_ta(page) -> str | None:
    """Lấy toàn văn các khối JD, loại tiêu đề tin và nội dung gợi ý."""
    mo_ta_heading = muc_heading(page, "Mô tả công việc")
    if not mo_ta_heading.count():
        return None
    try:
        return mo_ta_heading.evaluate("""(h, options) => {
          const all = [...document.querySelectorAll(options.h2Selector)];
          const targets = all.filter(e => options.names.includes(e.innerText.trim()));
          if (!targets.length) return null;
          let root = h;
          while (root && !targets.every(e => root.contains(e))) root = root.parentElement;
          if (!root) return null;
          const copy = root.cloneNode(true);
          const sections = [...copy.querySelectorAll(options.h2Selector)].filter(e => options.names.includes(e.innerText.trim()));
          const keep = new Set(sections);
          for (const section of sections) {
            for (let parent = section.parentElement; parent && parent !== copy; parent = parent.parentElement) keep.add(parent);
          }
          [...copy.children].forEach(child => { if (![...keep].some(node => child === node || child.contains(node))) child.remove(); });
          copy.querySelectorAll(options.buttonSelector).forEach(n => n.remove());
          copy.querySelectorAll(options.bannerSelector).forEach(n => n.remove());
          return copy.innerText.trim() || null;
        }""", {
            "names": list(TEN_HEADING),
            "h2Selector": SELECTOR_H2,
            "buttonSelector": SELECTOR_NUT_VA_ROLE,
            "bannerSelector": SELECTOR_BANNER_GOI_Y,
        })
    except PlaywrightError:
        return None


def gia_tri_thong_tin(text: str, nhan: tuple[str, ...]) -> str | None:
    """Đọc giá trị sau nhãn, tránh lấy nhãn kế tiếp làm giá trị."""
    dong = [re.sub(r"\s+", " ", m).strip() for m in text.splitlines() if m.strip()]
    nhan_can_tim = {re.sub(r"\s+", " ", m).strip().rstrip(":：").casefold() for m in nhan}
    tat_ca_nhan = NHAN_THONG_TIN_BIET | nhan_can_tim
    for vi_tri, muc in enumerate(dong):
        muc_chuan = muc.casefold()
        ten = next((m for m in sorted(nhan_can_tim, key=len, reverse=True)
                    if muc_chuan == m or muc_chuan.startswith(m + " ")
                    or muc_chuan.startswith(m + ":") or muc_chuan.startswith(m + "：")), None)
        if ten is None:
            continue
        hau_to = muc[len(ten):].strip()
        if hau_to.startswith((":", "：")):
            hau_to = hau_to[1:].strip()
        if hau_to:
            gia_tri = hau_to
        elif vi_tri + 1 < len(dong):
            gia_tri = dong[vi_tri + 1].strip()
        else:
            return None
        if gia_tri.rstrip(":：").casefold() in tat_ca_nhan:
            return None
        return gia_tri
    return None


def tach_ky_nang(cac_muc: list[str]) -> str | None:
    """Tuần tự hóa nguyên văn từng thẻ kỹ năng thành chuỗi JSON."""
    ky_nang = [muc.strip() for muc in cac_muc if muc.strip()]
    return json.dumps(ky_nang, ensure_ascii=False) if ky_nang else None


def lay_thong_tin_dom(page) -> str:
    """Ghép nhãn và giá trị từ từng dòng trong mục thông tin việc làm."""
    heading = muc_heading(page, "Thông tin việc làm")
    if not heading.count():
        return ""
    khoi = heading.locator(SELECTOR_PARENT)
    ket_qua = []
    for nhan in khoi.locator(SELECTOR_NHAN_THONG_TIN).all():
        ten = nhan.inner_text().strip()
        try:
            gia_tri = nhan.locator(SELECTOR_GIA_TRI_THONG_TIN).inner_text().strip()
        except PlaywrightError:
            gia_tri = ""
        ket_qua.append(f"{ten}\n{gia_tri}" if gia_tri else ten)
    return "\n".join(ket_qua)


def lay_the_ky_nang(page) -> list[str]:
    """Lấy từng nút kỹ năng trong vùng của tin hiện tại."""
    mo_ta = muc_heading(page, "Mô tả công việc")
    khoi = mo_ta.locator(SELECTOR_KHUNG_TIN)
    return khoi.locator(SELECTOR_THE_KY_NANG).all_inner_texts()


def lay_luong(page) -> str | None:
    """Đọc nhãn lương gần tiêu đề, không nhầm nhãn badge hoặc thông tin khác."""
    try:
        tieu_de = page.locator(SELECTOR_TIEU_DE).first
        khoi = tieu_de.locator(SELECTOR_KHOI_TIEU_DE)
        nhan = khoi.locator(SELECTOR_NHAN_LUONG)
        mau_luong = re.compile(
            r"(?:\$|€|£|₫|\bđ\b|\bvnd\b|\busd\b|\btriệu\b|\btr\b|/tháng|/năm)",
            re.I,
        )
        nhan_thoa_thuan = {"thương lượng", "thỏa thuận", "negotiable"}
        for i in range(nhan.count()):
            gia_tri = nhan.nth(i).inner_text().strip()
            if mau_luong.search(gia_tri) or gia_tri.casefold() in nhan_thoa_thuan:
                return gia_tri
    except PlaywrightError:
        pass
    return None


def lay_cong_ty(page) -> str | None:
    """Đọc tên công ty từ link nhãn trong hồ sơ của tin hiện tại."""
    try:
        links = page.locator(SELECTOR_CONG_TY)
        for i in range(links.count()):
            if links.nth(i).is_visible():
                text = links.nth(i).inner_text().strip()
                if text:
                    return text
    except PlaywrightError:
        return None
    return None


def tach_ban_ghi(page, job: dict, url_tim_kiem: str,
                  tu_khoa: str, timestamp: str) -> tuple[dict | None, str]:
    """Ánh xạ các trường từ một nguồn DOM cố định theo schema."""
    tieu_de = page.locator(SELECTOR_TIEU_DE).first.inner_text().strip()
    ten_ct = lay_cong_ty(page)
    mo_ta = toan_van_mo_ta(page)
    yeu_cau = noi_dung_muc(page, "Yêu cầu công việc")
    quyen_loi = noi_dung_muc(page, "Các phúc lợi dành cho bạn")
    dia_diem = noi_dung_muc(page, "Địa điểm làm việc", bao_gom_heading=False)
    ky_nang = tach_ky_nang(lay_the_ky_nang(page))
    thong_tin = lay_thong_tin_dom(page)
    if mo_ta and re.search(
        r"(?im)^\s*[^\w\n]*(?:job description|job requirements|what we can offer)\s*:?\s*$",
        mo_ta,
    ):
        log(f"CẢNH BÁO: tin gốc có heading tiếng Anh, giữ nguyên văn: {page.url}")
    mota_chuan = re.sub(r"\s+", " ", mo_ta or "")
    ma_tin = str(job.get("jobId") or "không rõ")
    if yeu_cau and re.sub(r"\s+", " ", yeu_cau) not in mota_chuan:
        log(f"CẢNH BÁO: yêu cầu không nằm trong Mo_Ta_Cong_Viec; mã tin {ma_tin}")
    if quyen_loi and re.sub(r"\s+", " ", quyen_loi) not in mota_chuan:
        log(f"CẢNH BÁO: quyền lợi không nằm trong Mo_Ta_Cong_Viec; mã tin {ma_tin}")
    bat_buoc = (tieu_de, ten_ct, dia_diem, mo_ta, page.url, timestamp)
    if not all(bat_buoc):
        return None, "thiếu trường bắt buộc: " + ", ".join(
            ten for ten, gia_tri in zip(
                ("Tieu_De", "Ten_Cong_Ty", "Dia_Diem", "Mo_Ta_Cong_Viec", "URL_Goc", "Timestamp"),
                bat_buoc,
            ) if not gia_tri
        )
    return {
        "Web": "vietnamworks",
        "Ma_Tin_Nguon": str(job["jobId"]) if job.get("jobId") is not None else None,
        "URL_Goc": page.url,
        "URL_Tim_Kiem": url_tim_kiem,
        "Tu_Khoa_Tim_Kiem": tu_khoa,
        "Timestamp": timestamp,
        "Tieu_De": tieu_de,
        "Ten_Cong_Ty": ten_ct,
        "Dia_Diem": dia_diem,
        "Luong": lay_luong(page),
        "Kinh_Nghiem": gia_tri_thong_tin(thong_tin, ("Số năm kinh nghiệm tối thiểu",)),
        "Hinh_Thuc_Lam_Viec": gia_tri_thong_tin(thong_tin, ("Hình thức làm việc",)),
        "Loai_Hop_Dong": gia_tri_thong_tin(thong_tin, ("Loại hợp đồng", "Loại hình công việc", "Loại hình làm việc")),
        "Ngay_Dang": gia_tri_thong_tin(thong_tin, ("Ngày đăng",)),
        "Mo_Ta_Cong_Viec": mo_ta,
        "Yeu_Cau_Chi_Tiet": yeu_cau,
        "Quyen_Loi": quyen_loi,
        "Ky_Nang": ky_nang,
    }, ""


def in_jsonl(dong: dict) -> None:
    """In một dòng JSONL đúng thứ tự schema, không escape Unicode."""
    print(json.dumps({cot: dong.get(cot) for cot in COT},
                     ensure_ascii=False, separators=(",", ":")), flush=True)


def ghi_json(duong_dan, cac_dong: list[dict]) -> None:
    """Ghi mảng JSON theo schema bằng tệp tạm rồi thay thế nguyên tử."""
    dich = Path(duong_dan)
    dich.parent.mkdir(parents=True, exist_ok=True)
    cot_bat_buoc = doc_schema()["required"]
    ban_ghi = []
    for dong in cac_dong:
        ban_ghi.append({
            cot: (None if isinstance(dong.get(cot), str) and not dong[cot].strip()
                  else str(dong[cot]) if cot == "Ma_Tin_Nguon" and dong.get(cot) is not None
                  else dong.get(cot))
            for cot in cot_bat_buoc
        })
    fd, tep_tam = tempfile.mkstemp(dir=dich.parent, prefix=f".{dich.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tep:
            json.dump(ban_ghi, tep, ensure_ascii=False, indent=2)
            tep.write("\n\n")
            tep.flush()
            os.fsync(tep.fileno())
        os.replace(tep_tam, dich)
    finally:
        if os.path.exists(tep_tam):
            os.unlink(tep_tam)


def doc_tham_so():
    """Đọc ba tham số dòng lệnh của crawler."""
    parser = argparse.ArgumentParser(description="Cào tin tuyển dụng VietnamWorks")
    parser.add_argument("--tu-khoa")
    parser.add_argument("--so-trang", type=int)
    parser.add_argument("--gioi-han", type=int)
    args = parser.parse_args()
    if args.so_trang is not None and args.so_trang < 1:
        parser.error("--so-trang phải >= 1")
    if args.gioi_han is not None and args.gioi_han < 1:
        parser.error("--gioi-han phải >= 1")
    return args


def xu_ly_tin(page, job, search_url, kw, ids, urls, rows, stats, dem_kw):
    """Bỏ tin trùng, tải trang chi tiết và thêm bản ghi hợp lệ."""
    job_id = str(job.get("jobId") or "")
    url = url_tieng_viet(job.get("jobUrl") or "")
    key_url = khoa_url(url) if url else None
    if (job_id and job_id in ids) or (key_url and key_url in urls):
        stats["trung"] += 1
        dem_kw["trung"] += 1
        return "trùng", "đã có trong CSV"
    timestamp = danh_dau_bat_dau()
    with redirect_stdout(sys.stderr):
        tai_xong, status = tai_thu_lai(
            lambda target: tai_chi_tiet(page, target), url, stats,
        )
    if status in DUNG:
        raise RuntimeError(f"Dừng do 403/429/captcha: {url}")
    if status != "ok" or not tai_xong:
        stats["loi"] += 1
        dem_kw["loi"] += 1
        return "lỗi", f"chi tiết {status}"
    try:
        row, reason = tach_ban_ghi(page, job, search_url, kw, timestamp)
    except PlaywrightError as error:
        row, reason = None, f"lỗi DOM {type(error).__name__}"
    if row is None:
        stats["loi"] += 1
        dem_kw["loi"] += 1
        if reason.startswith("thiếu trường bắt buộc:"):
            stats["tin_thieu_bat_buoc"] += 1
            stats["thieu_lien_tiep"] += 1
            truong_thieu = [
                muc.strip() for muc in reason.partition(":")[2].split(",") if muc.strip()
            ]
            stats["truong_thieu_gan_nhat"] = ", ".join(truong_thieu)
            for muc in truong_thieu:
                stats["thieu_theo_truong"][muc] += 1
            return "bỏ thiếu trường", reason
        return "lỗi", reason
    rows.append(row)
    if job_id:
        ids.add(job_id)
    urls.add(khoa_url(row["URL_Goc"]))
    in_jsonl(row)
    stats["moi"] += 1
    dem_kw["moi"] += 1
    stats["thieu_lien_tiep"] = 0
    return "mới", ""


def xu_ly_tu_khoa(page, context, kw, vi_tri, tong_kw, args, rows,
                  ids, urls, stats, dem_kw, moi):
    """Duyệt từng trang tìm kiếm và ghi tiến độ một lần cho mỗi tin."""
    for search_url, jobs, page_no, status in duyet_tin(
        page, context, kw, args.so_trang, stats,
    ):
        if status in DUNG:
            raise RuntimeError(f"Truy cập bị chặn ở {search_url}")
        if status != "ok" or jobs is None:
            stats["loi"] += 1
            dem_kw["loi"] += 1
            log(f"Lỗi danh sách trang {page_no}: {status} {search_url}")
            break
        log(f"Từ khóa {vi_tri}/{tong_kw}; trang {page_no}; {len(jobs)} tin")
        for stt, job in enumerate(jobs, 1):
            if args.gioi_han is not None and moi >= args.gioi_han:
                return moi
            status, reason = xu_ly_tin(
                page, job, search_url, kw, ids, urls, rows, stats, dem_kw,
            )
            stats["da_xu_ly_tin"] += 1
            if status == "mới":
                moi += 1
                if moi % CHECKPOINT == 0:
                    xuat_csv(CSV, rows)
                    ghi_json(JSON, rows)
            log(f"Tin {stt}/{len(jobs)}; {status} {reason}; {job.get('jobUrl')}; tổng {len(rows)}")
            if stats["thieu_lien_tiep"] >= 5:
                xuat_csv(CSV, rows)
                ghi_json(JSON, rows)
                stats["dung_do_dom"] = True
                log(
                    "Dừng crawler: 5 tin liên tiếp thiếu trường bắt buộc; "
                    f"đã xử lý={stats['da_xu_ly_tin']}, "
                    f"bị bỏ vì thiếu trường={stats['tin_thieu_bat_buoc']}, "
                    f"các trường hay thiếu={stats['thieu_theo_truong'].most_common()}"
                )
                return moi
    return moi


def chay() -> None:
    """Khởi chạy crawler, checkpoint CSV và in thống kê."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = doc_tham_so()
    day_du = doc_tu_khoa()
    if args.tu_khoa:
        kw_chuan = next(
            (muc for muc in day_du if muc.casefold() == args.tu_khoa.strip().casefold()),
            None,
        )
        if kw_chuan is None:
            raise ValueError("--tu-khoa phải khớp một mục trong keyword.json")
        keywords = [kw_chuan]
    else:
        keywords = day_du
    rows = doc_csv(CSV)
    ids = {str(r["Ma_Tin_Nguon"]) for r in rows if r.get("Ma_Tin_Nguon")}
    urls = {khoa_url(r["URL_Goc"]) for r in rows if r.get("URL_Goc")}
    stats = Counter()
    stats["thieu_lien_tiep"] = 0
    stats["tin_thieu_bat_buoc"] = 0
    stats["dung_do_dom"] = False
    stats["truong_thieu_gan_nhat"] = ""
    stats["thieu_theo_truong"] = Counter()
    stats["da_xu_ly_tin"] = 0
    by_keyword = {kw: Counter() for kw in keywords}
    start = time.monotonic()
    moi = 0
    browser = context = None
    log(f"Bắt đầu: {len(keywords)} từ khóa; checkpoint có {len(rows)} tin")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(
                locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
                extra_http_headers={"Accept-Language": "vi-VN,vi;q=0.9"},
            )
            page = context.new_page()
            for pos, kw in enumerate(keywords, 1):
                log(f"Từ khóa {pos}/{len(keywords)}: {kw}")
                moi = xu_ly_tu_khoa(
                    page, context, kw, pos, len(keywords), args, rows,
                    ids, urls, stats, by_keyword[kw], moi,
                )
                if stats["dung_do_dom"] or (args.gioi_han is not None and moi >= args.gioi_han):
                    break
    finally:
        xuat_csv(CSV, rows)
        ghi_json(JSON, rows)
        log(f"Kết thúc: mới={stats['moi']}, trùng={stats['trung']}, lỗi={stats['loi']}, tổng={len(rows)}, thời gian={time.monotonic()-start:.1f}s")
        for kw, counts in by_keyword.items():
            log(f"  {kw}: mới={counts['moi']}, trùng={counts['trung']}, lỗi={counts['loi']}")
    if len(rows) < 800:
        log(f"CẢNH BÁO: hiện có {len(rows)} tin, thấp hơn mục tiêu tối thiểu 800.")


if __name__ == "__main__":
    try:
        chay()
    except KeyboardInterrupt:
        log("Đã dừng bởi Ctrl+C; checkpoint CSV và JSON đã được lưu.")
    except (ValueError, RuntimeError, OSError, PlaywrightError) as loi:
        log(f"Dừng crawler: {loi}")
