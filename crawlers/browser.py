"""Duyệt trang TopCV bằng HTTP và quản lý phiên xem lương ITviec."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections import Counter
from html import escape
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawlers import itviec_crawler as itviec
from crawlers.base_crawler import (
    DUNG, doc_csv, duoc_phep, khoa_url, kiem_thu_robot, nghi_ngau_nhien, xuat_csv,
)
from crawlers.itviec_crawler import (
    TEN_BOT as ITVIEC_USER_AGENT, TRANG_CHU as TRANG_CHU_ITVIEC,
    KHOANG_NGHI, bi_thu_thach, la_thu_thach_cloudflare, _tach_url as tach_url,
)

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Playwright


TRANG_DANG_NHAP = f"{TRANG_CHU_ITVIEC}/sign_in"
DUONG_DAN_DANG_NHAP = {"/sign_in", "/users/sign_in", "/dang-nhap"}
THOI_GIAN_DANG_NHAP = 300
THU_MUC_PHIEN = Path.home() / ".itec3417_itviec_profile"
NGUONG_KHOA_LUONG = 3


def duyet_trang_topcv(url, tai, max_pages):
    """Nối các lô tin theo nút trang sau TopCV công bố trong HTML."""
    da_duyet = set()
    while url and url not in da_duyet:
        da_duyet.add(url)
        html, ma = tai(url)
        soup = BeautifulSoup(html, "html.parser") if html is not None else None
        yield url, soup, ma
        if soup is None or max_pages and len(da_duyet) >= max_pages:
            return
        nut = soup.select_one('.box-pagination a[rel~="next"]')
        if nut is None:
            return
        href = nut.get("data-href")
        if not isinstance(href, str) or not href.strip():
            href = nut.get("href")
        if not isinstance(href, str) or not href.strip():
            return
        try:
            url = urldefrag(urljoin(url, href)).url
        except ValueError:
            yield url, None, "loi_lien_ket"
            return


def mo_chrome(playwright: Playwright, thu_muc_phien: Path) -> BrowserContext:
    """Mở cửa sổ Chrome với profile riêng, dùng Chromium nếu thiếu Chrome."""
    from playwright.sync_api import Error

    chromium = playwright.chromium
    user_data_dir = str(thu_muc_phien)
    try:
        return chromium.launch_persistent_context(
            user_data_dir=user_data_dir, channel="chrome", headless=False, user_agent=ITVIEC_USER_AGENT,
        )
    except Error as loi:
        if not any(dau in str(loi).casefold() for dau in ("not found", "doesn't exist", "executable doesn't exist")):
            raise
        return chromium.launch_persistent_context(user_data_dir=user_data_dir, headless=False, user_agent=ITVIEC_USER_AGENT)


def kiem_tra_phien(trang: Page, rp, *, cho_xac_minh: bool = False) -> bool:
    """Kiểm tra phiên, giữ nguyên màn hình xác minh nếu đang chờ đăng nhập tay."""
    from playwright.sync_api import Error

    if not duoc_phep(rp, TRANG_CHU_ITVIEC, TRANG_DANG_NHAP, ITVIEC_USER_AGENT):
        raise RuntimeError("robots.txt không cho phép mở trang đăng nhập")
    nghi_ngau_nhien(KHOANG_NGHI)
    try:
        phan_hoi = trang.goto(TRANG_DANG_NHAP, wait_until="domcontentloaded", timeout=15000)
    except Error as loi:
        raise RuntimeError(f"Không thể mở trang đăng nhập: {loi}") from loi
    if phan_hoi is None:
        raise RuntimeError("Trang xác minh phiên không có phản hồi HTTP")
    url = tach_url(trang.url)
    ma = phan_hoi.status
    duong_dan = url.path or "/"
    if url.scheme != "https" or url.hostname != "itviec.com":
        raise RuntimeError("Trang xác minh phiên chuyển ra ngoài ITviec")
    if la_thu_thach_cloudflare(phan_hoi.headers):
        if cho_xac_minh and ma in (200, 403, 503):
            return False
        ray_id = phan_hoi.headers.get("cf-ray")
        tham_chieu = f", Ray ID {ray_id}" if ray_id else ""
        raise RuntimeError(f"Cloudflare yêu cầu xác minh tại {duong_dan} (HTTP {ma}{tham_chieu})")
    if ma in (401, 403, 429):
        raise RuntimeError(f"Trang xác minh phiên bị từ chối tại {duong_dan} (HTTP {ma})")
    try:
        html = trang.content()
    except Error:
        html = ""
    if bi_thu_thach(html):
        if cho_xac_minh and ma == 200:
            return False
        raise RuntimeError(f"Phát hiện trang xác minh hoặc CAPTCHA tại {duong_dan} (HTTP {ma})")
    if ma != 200:
        raise RuntimeError(f"Trang xác minh phiên trả HTTP {ma} tại {duong_dan}")
    try:
        khong_con_form = trang.locator('input[type="password"]').count() == 0
    except Error:
        khong_con_form = False
    return url.path.rstrip("/") not in DUONG_DAN_DANG_NHAP and khong_con_form


def dang_nhap_tay(trang: Page) -> bool:
    """Chờ người dùng đăng nhập trong cửa sổ đã mở."""
    from playwright.sync_api import Error

    print("Đăng nhập thủ công trên ITviec bằng Email + Mật khẩu trong cửa sổ Chrome.", flush=True)
    print(
        "Nếu Chrome hiện CAPTCHA, hãy xác minh trong cửa sổ đó. "
        f"Chờ tối đa {THOI_GIAN_DANG_NHAP} giây.",
        flush=True,
    )
    han = time.monotonic() + THOI_GIAN_DANG_NHAP
    while time.monotonic() < han:
        for cua_so in trang.context.pages:
            try:
                if (tach_url(cua_so.url).hostname == "accounts.google.com"
                        and "this browser or app may not be secure" in cua_so.content().casefold()):
                    print("Google từ chối trình duyệt automation; dừng. Hãy dùng đăng nhập Email của ITviec.")
                    return False
            except Error:
                pass

        try:
            dia_chi = trang.url
            url = tach_url(dia_chi)
            if (url.scheme == "https" and url.hostname == "itviec.com"
                    and url.path.rstrip("/") not in DUONG_DAN_DANG_NHAP
                    and not bi_thu_thach(trang.content())
                    and trang.locator('input[type="password"]').count() == 0
                    and trang.url == dia_chi):
                return True
        except Error:
            pass

        trang.wait_for_timeout(1000)
    print("Hết thời gian chờ đăng nhập; phần lương cần đăng nhập sẽ để trống.")
    return False


@contextmanager
def phien_luong(thu_muc_phien: Path, rp, cdp_url: str | None = None) -> Iterator[Page]:
    """Mở một phiên đăng nhập riêng để xem lương và đóng khi dùng xong."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as loi:
        raise RuntimeError("Cần cài Playwright để bổ sung lương yêu cầu đăng nhập.") from loi

    if cdp_url:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(cdp_url)
                try:
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                    trang = context.pages[0] if context.pages else context.new_page()
                    yield trang
                finally:
                    pass
        except Error as loi:
            raise RuntimeError(f"Lỗi khi kết nối Chrome qua CDP ({cdp_url}): {loi}") from loi
        return

    shutil.rmtree(thu_muc_phien, ignore_errors=True)
    try:
        with sync_playwright() as playwright:
            phien = mo_chrome(playwright, thu_muc_phien)
            try:
                trang = phien.pages[0] if phien.pages else phien.new_page()
                if not kiem_tra_phien(trang, rp, cho_xac_minh=True):
                    if not dang_nhap_tay(trang) or not kiem_tra_phien(trang, rp):
                        raise RuntimeError("Phiên đăng nhập ITviec chưa hợp lệ.")
                yield trang
            finally:
                phien.close()
                shutil.rmtree(thu_muc_phien, ignore_errors=True)
    except Error as loi:
        raise RuntimeError(f"Lỗi trình duyệt khi bổ sung lương: {loi}") from loi


def tai_trang_luong(trang: Page, url: str) -> tuple[str | None, str]:
    """Lấy HTML của tin trong phiên đã đăng nhập để đọc lương hiển thị."""
    from playwright.sync_api import Error, TimeoutError

    nghi_ngau_nhien(KHOANG_NGHI)
    try:
        phan_hoi = trang.goto(url, wait_until="load", timeout=15000)
    except (TimeoutError, Error):
        return None, "loi_tam_thoi"
    if phan_hoi is None:
        return None, "loi_tam_thoi"
    ma = phan_hoi.status
    if ma in (401, 403, 429) or la_thu_thach_cloudflare(phan_hoi.headers):
        return None, "bi_chan"
    if ma == 404:
        return None, "khong_ton_tai"
    if ma >= 500:
        return None, "loi_tam_thoi"
    try:
        url_hien_tai = tach_url(trang.url)
    except Error:
        return None, "loi_tam_thoi"
    if (url_hien_tai.scheme != "https" or url_hien_tai.hostname != "itviec.com"
            or url_hien_tai.path.rstrip("/") in DUONG_DAN_DANG_NHAP):
        return None, "bi_chan"
    if khoa_url(trang.url) != khoa_url(url):
        return None, "khong_ton_tai"
    if ma != 200:
        return None, "bi_cam"
    try:
        html = trang.content()
    except Error:
        return None, "loi_tam_thoi"
    if bi_thu_thach(html):
        return None, "bi_chan"
    try:
        salary = trang.locator(".salary").first
        if not salary.count():
            return "", "ok"
        return f'<div class="salary">{escape(salary.inner_text())}</div>', "ok"
    except Error:
        return None, "loi_tam_thoi"


def bo_sung_luong(can_xem_luong, rp, cac_dong, thong_ke, cdp_url: str | None = None):
    print(f"Bổ sung lương qua Chrome cho tối đa {len(can_xem_luong)} tin.", flush=True)
    khoa_lien_tiep = 0
    try:
        with phien_luong(THU_MUC_PHIEN, rp, cdp_url=cdp_url) as trang:
            for dong in can_xem_luong:
                if not itviec.can_bo_sung_luong(dong.get("Luong")):
                    continue
                url = dong["URL_Goc"]
                html, ma = itviec.tai(url, rp, thong_ke, lambda dich: tai_trang_luong(trang, dich))
                if ma in (*DUNG, "bi_cam"):
                    print(f"Dừng bổ sung lương: {ma} tại {url}")
                    return ma
                if ma != "ok" or html is None:
                    khoa_lien_tiep = 0
                    continue
                khoa_lien_tiep = khoa_lien_tiep + 1 if itviec.bi_khoa_luong(html) else 0
                if khoa_lien_tiep >= NGUONG_KHOA_LUONG:
                    print("Dừng bổ sung lương: nhiều trang liên tiếp yêu cầu đăng nhập.")
                    thong_ke["bi_chan"] += 1
                    return "bi_chan"
                luong = itviec.luong_goc(html)
                if luong is not None:
                    dong["Luong"] = luong
                    thong_ke["cap_nhat_luong"] += 1
                    if thong_ke["cap_nhat_luong"] % itviec.CHECKPOINT == 0:
                        xuat_csv(itviec.DUONG_DAN_CSV, cac_dong)
    except RuntimeError as loi:
        print(f"Dừng bổ sung lương: {loi}")
        return "loi_phien"
    return None


def main(argv=None):
    cli = argparse.ArgumentParser(description="Bổ sung lương vào CSV ITviec bằng phiên Chrome đã đăng nhập")
    cli.add_argument("--limit", type=int, default=20, help="Số tin thiếu lương tối đa (mặc định: 20, 0: không giới hạn)")
    cli.add_argument("--cdp", action="store_true", help="Kết nối tới Chrome thật đang mở qua cổng Remote Debugging (port 9222)")
    cli.add_argument("--cdp-url", type=str, default="http://localhost:9222", help="URL CDP (mặc định: http://localhost:9222)")
    args = cli.parse_args(argv)
    if args.limit < 0:
        cli.error("--limit phải >= 0")

    cdp_endpoint = args.cdp_url if args.cdp else None

    try:
        cac_dong = doc_csv(itviec.DUONG_DAN_CSV)
    except ValueError as loi:
        print(f"Dừng: {loi}")
        return 2
    can_xem_luong = [
        dong for dong in cac_dong
        if itviec.can_bo_sung_luong(dong.get("Luong")) and itviec._url_tin(dong.get("URL_Goc"))
    ]
    if args.limit:
        can_xem_luong = can_xem_luong[:args.limit]
    if not can_xem_luong:
        print("CSV không có tin cần bổ sung lương.")
        return 0

    muc_tieu = [TRANG_DANG_NHAP, *(dong["URL_Goc"] for dong in can_xem_luong)]
    nghi_ngau_nhien(KHOANG_NGHI)
    rp, ly_do = kiem_thu_robot(itviec.TRANG_CHU, muc_tieu, ITVIEC_USER_AGENT)
    if rp is None:
        print(f"Dừng bổ sung lương: {ly_do}")
        return 2

    thong_ke = Counter()
    try:
        dung = bo_sung_luong(can_xem_luong, rp, cac_dong, thong_ke, cdp_url=cdp_endpoint)
    except KeyboardInterrupt:
        dung = "Ctrl+C"
    finally:
        if thong_ke["cap_nhat_luong"]:
            xuat_csv(itviec.DUONG_DAN_CSV, cac_dong)
    print(f"Đã bổ sung lương cho {thong_ke['cap_nhat_luong']} tin.")
    return 130 if dung == "Ctrl+C" else 2 if dung else 0


if __name__ == "__main__":
    raise SystemExit(main())
