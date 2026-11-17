"""
BẮT ĐẦU -> kiem_thu_robot() -- không được phép/lỗi --> DỪNG
-> doc_csv() -> tạo da_luu từ khoa_url() -> duyệt URL/phân trang
-> khoa_url(): đã lưu -> BỎ QUA -> duoc_phep(): không được -> BỎ QUA
-> danh_dau_bat_dau() -> tai_thu_lai(): bi_chan/ngat_mach -> DỪNG;
   lỗi khác -> BỎ QUA -> bóc thông tin -> loc_keyword.la_tin_muc_tieu():
   không thuộc nhóm -> BỎ QUA -> thêm dòng thô và cập nhật da_luu ngay
-> xuat_csv() theo checkpoint, ví dụ mỗi 10 tin mới -> URL tiếp -> KẾT THÚC.
"""

import csv
import json
import os
import random
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

THU_MUC_GOC = Path(__file__).resolve().parent.parent
TIMEOUT_ROBOTS = 15
DUNG = ("bi_chan", "ngat_mach")


@cache
def doc_schema() -> dict:
    """Đọc schema dùng chung."""
    try:
        with (THU_MUC_GOC / "schema.json").open(encoding="utf-8") as tep:
            return json.load(tep)
    except (OSError, json.JSONDecodeError) as loi:
        raise ValueError("Không đọc được schema.json") from loi


def kiem_thu_robot(trang_chu, url_muc_tieu, ten_bot) -> tuple:
    """Trả (robots, "") nếu được phép; ngược lại trả (None, lý do)."""
    thanh_phan = urlsplit(trang_chu)
    if not thanh_phan.scheme or not thanh_phan.netloc:
        return None, "trang_chu không hợp lệ"
    goc = f"{thanh_phan.scheme}://{thanh_phan.netloc}"
    yeu_cau = urllib.request.Request(f"{goc}/robots.txt", headers={"User-Agent": ten_bot})
    try:
        with urllib.request.urlopen(yeu_cau, timeout=TIMEOUT_ROBOTS) as phan_hoi:
            ma = phan_hoi.status
            noi_dung = phan_hoi.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as loi:
        ma = loi.code
    except (urllib.error.URLError, OSError) as loi:
        return None, f"lỗi mạng khi tải robots.txt: {loi}"
    if ma == 404:
        # Nhóm chủ động dừng khi robots.txt trả 404; RFC 9309 cho phép crawler tiếp tục trong trường hợp này.
        return None, "không tìm thấy robots.txt (HTTP 404)"
    if ma != 200:
        return None, f"không tải được robots.txt (HTTP {ma})"
    rp = RobotFileParser()
    rp.parse(noi_dung.splitlines())
    for url in url_muc_tieu or [f"{goc}/"]:
        if not rp.can_fetch(ten_bot, url):
            return None, f"robots.txt không cho phép: {url}"
    return rp, ""


def duoc_phep(rp, trang_chu, url, ten_bot) -> bool:
    """Kiểm tra host và quyền truy cập URL."""
    host_goc = (urlsplit(trang_chu).hostname or "").lower().removeprefix("www.")
    host_url = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host_goc == host_url and rp.can_fetch(ten_bot, url)


def doc_csv(duong_dan) -> list[dict]:
    """Đọc CSV cũ và kiểm tra thứ tự cột."""
    try:
        tep = open(duong_dan, encoding="utf-8-sig", newline="")
    except FileNotFoundError:
        return []
    with tep:
        doc = csv.DictReader(tep)
        mong_doi = doc_schema()["required"]
        if doc.fieldnames != mong_doi:
            raise ValueError(f"Header CSV khác schema: nhận {doc.fieldnames}, cần {mong_doi}")
        return [{cot: None if gia_tri == "" else gia_tri for cot, gia_tri in dong.items()}
                for dong in doc]


def khoa_url(url) -> tuple:
    """Tạo khóa đối chiếu URL."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    # Chỉ đối chiếu; CSV giữ URL gốc. Nếu query chứa mã tin, crawler phải tự xử lý trước.
    return host, path


def danh_dau_bat_dau() -> str:
    """Ghi nhận thời điểm bắt đầu tải tin."""
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def nghi_ngau_nhien(khoang_nghi=(2.0, 5.0), ham_nghi=time.sleep):
    """Giãn tần suất truy cập."""
    giay = random.uniform(khoang_nghi[0], khoang_nghi[1])
    ham_nghi(giay)


def tai_thu_lai(ham_tai, url, thong_ke, *, khoang_nghi=(2.0, 5.0), so_lan_thu=3, co_so_cho=2.0, tran_cho=60.0, nguong_ngat=3, ham_nghi=time.sleep):
    """Thử lại lỗi tạm thời và ngắt khi lỗi liên tiếp."""
    nghi_ngau_nhien(khoang_nghi, ham_nghi)
    for lan in range(so_lan_thu + 1):
        try:
            noi_dung, ma = ham_tai(url)
        except Exception as loi:
            # Hiển thị nguyên nhân khi hàm tải gặp lỗi để hỗ trợ kiểm tra lúc chạy.
            print(f"Lỗi khi tải trang: {type(loi).__name__}: {loi}")
            break
        if ma == "ok":
            thong_ke["loi_lien_tiep"] = 0
            thong_ke["ok"] += 1
            return noi_dung, "ok"
        if ma == "khong_ton_tai":
            thong_ke["loi_lien_tiep"] = 0
            thong_ke[ma] += 1
            return None, ma
        if ma in ("bi_cam", "bi_chan"):
            thong_ke[ma] += 1
            return None, ma
        if ma != "loi_tam_thoi":
            break
        if lan < so_lan_thu:
            # Chờ tăng theo hàm mũ và thêm độ lệch ngẫu nhiên giữa các lần thử.
            ham_nghi(min(tran_cho, co_so_cho * 2**lan) + random.uniform(0, 1))
    thong_ke["loi_lien_tiep"] += 1
    if thong_ke["loi_lien_tiep"] >= nguong_ngat:
        thong_ke["ngat_mach"] += 1
        return None, "ngat_mach"
    thong_ke["that_bai"] += 1
    return None, "that_bai"


def xuat_csv(duong_dan, cac_dong):
    """Kiểm tra dữ liệu rồi ghi CSV nguyên tử."""
    if not cac_dong:
        return
    schema = doc_schema()
    cac_cot = schema["required"]
    bat_buoc = {cot for cot in cac_cot if "null" not in schema["properties"][cot]["type"]}
    dong_da_doi = []
    khoa_thua = set()
    for so_dong, dong in enumerate(cac_dong, 1):
        if not isinstance(dong, dict):
            raise ValueError(f"Dòng {so_dong}: dữ liệu không phải dict")
        khoa_thua.update(set(dong) - set(cac_cot))
        dong_moi = {}
        for cot in cac_cot:
            gia_tri = dong.get(cot)
            if gia_tri is None or isinstance(gia_tri, str) and not gia_tri.strip():
                gia_tri = ""
            elif isinstance(gia_tri, (list, dict, tuple)):
                gia_tri = json.dumps(gia_tri, ensure_ascii=False, default=str) if gia_tri else ""
            elif not isinstance(gia_tri, str):
                gia_tri = str(gia_tri)
            if cot in bat_buoc and gia_tri == "":
                raise ValueError(f"Dòng {so_dong}: cột bắt buộc '{cot}' thiếu giá trị")
            dong_moi[cot] = gia_tri
        dong_da_doi.append(dong_moi)
    if khoa_thua:
        print(f"Bỏ khóa ngoài schema: {', '.join(str(khoa) for khoa in khoa_thua)}")
    dich = Path(duong_dan)
    dich.parent.mkdir(parents=True, exist_ok=True)
    # Ghi và đồng bộ file tạm trước khi thay thế CSV đích.
    fd, file_tam = tempfile.mkstemp(dir=dich.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as tep:
            ghi = csv.DictWriter(tep, fieldnames=cac_cot)
            ghi.writeheader()
            ghi.writerows(dong_da_doi)
            tep.flush()
            os.fsync(tep.fileno())
        os.replace(file_tam, dich)
    finally:
        if os.path.exists(file_tam):
            os.unlink(file_tam)
