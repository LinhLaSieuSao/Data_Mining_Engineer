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
__all__ = [
    "DUNG", "doc_schema", "kiem_thu_robot", "duoc_phep", "doc_csv",
    "khoa_url", "danh_dau_bat_dau", "nghi_ngau_nhien", "tai_thu_lai",
    "xuat_csv",
]
