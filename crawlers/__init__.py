"""Các hàm dùng chung cho crawler tuyển dụng."""

from .base_crawler import (
    DUNG,
    danh_dau_bat_dau,
    doc_csv,
    doc_schema,
    duoc_phep,
    khoa_url,
    kiem_thu_robot,
    nghi_ngau_nhien,
    tai_thu_lai,
    xuat_csv,
)
from .loc_keyword import chuan_van_ban, doc_keyword, khop_nhom, la_tin_muc_tieu

__all__ = [
    "DUNG", "doc_schema", "kiem_thu_robot", "duoc_phep", "doc_csv",
    "khoa_url", "danh_dau_bat_dau", "nghi_ngau_nhien", "tai_thu_lai",
    "xuat_csv", "doc_keyword", "chuan_van_ban", "khop_nhom", "la_tin_muc_tieu",
]
