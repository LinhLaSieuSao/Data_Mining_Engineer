"""Lọc nhóm vị trí theo tiêu đề tuyển dụng."""

import json
import re
import unicodedata
from functools import cache
from pathlib import Path

THU_MUC_GOC = Path(__file__).resolve().parent.parent


@cache
def doc_keyword() -> dict:
    """Đọc cấu hình từ khóa."""
    try:
        with (THU_MUC_GOC / "keyword.json").open(encoding="utf-8") as tep:
            return json.load(tep)
    except (OSError, json.JSONDecodeError) as loi:
        raise ValueError("Không đọc được keyword.json") from loi


def chuan_van_ban(chuoi) -> str:
    """Chuẩn hóa văn bản để so khớp."""
    chuoi = unicodedata.normalize("NFD", chuoi)
    chuoi = "".join(ky_tu for ky_tu in chuoi if unicodedata.category(ky_tu) != "Mn")
    chuoi = chuoi.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9]+", " ", chuoi).strip()


def khop_nhom(tieu_de) -> list[str]:
    """Trả các nhóm khớp theo thứ tự cấu hình."""
    if not isinstance(tieu_de, str) or not tieu_de.strip():
        return []
    cau_hinh = doc_keyword()
    tieu_de_chuan = f" {chuan_van_ban(tieu_de)} "
    ket_qua = []
    # Nhóm AI chỉ khớp cụm chức danh, tránh nhận mọi tiêu đề có từ AI.
    for ma, nhom in cau_hinh["nhom"].items():
        if (any(f" {chuan_van_ban(cum)} " in tieu_de_chuan for cum in nhom["cum_tu"])
                or any(re.search(r"(?<!\w)" + re.escape(vt) + r"(?!\w)", tieu_de)
                       for vt in nhom["viet_tat"])):
            ket_qua.append(ma)
    return ket_qua


def la_tin_muc_tieu(tieu_de) -> bool:
    """Kiểm tra tiêu đề có thuộc nhóm mục tiêu."""
    return len(khop_nhom(tieu_de)) > 0
