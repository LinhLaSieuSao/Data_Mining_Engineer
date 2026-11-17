"""Kiểm thử bộ công cụ crawler bằng dữ liệu giả, không truy cập mạng."""

import csv
import json
import unittest
import urllib.error
from collections import Counter
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.robotparser import RobotFileParser

import crawlers
from crawlers import loc_keyword


class PhanHoiGia:
    def __init__(self, noi_dung, status=200):
        self.noi_dung = noi_dung.encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.noi_dung


class KiemThuKeyword(unittest.TestCase):
    def test_khop_tieu_de(self):
        cac_truong_hop = [
            ("Senior Data Analyst (SQL/Power BI)", ["DA"]),
            ("Chuyên viên Phân tích dữ liệu", ["DA"]),
            ("Junior DA", ["DA"]),
            ("Kỹ sư Dữ liệu", ["DE"]),
            ("AI Engineer", ["AI"]),
            ("AI Engineering", ["AI"]),
            ("Artificial Intelligence Engineer", ["AI"]),
            ("Kỹ sư Trí tuệ nhân tạo", ["AI"]),
            ("Analytics Engineer", []),
            ("AI Product Manager", []),
            ("AI", []),
            ("Senior Backend Developer (Java)", ["BE"]),
            ("Back-end Engineer", ["BE"]),
            ("BE Developer", ["BE"]),
            ("Senior AE", []),
            ("AE Account Executive", []),
            ("Data Analyst / Data Engineer", ["DA", "DE"]),
            ("Nhân viên đa năng", []),
            ("Database Administrator", []),
            ("Data Entry Operator", []),
            ("Frontend Developer", []),
            ("Nhân viên kinh doanh", []),
            ("", []), (None, []), (123, []),
        ]
        for tieu_de, mong_doi in cac_truong_hop:
            with self.subTest(tieu_de=tieu_de):
                self.assertEqual(crawlers.khop_nhom(tieu_de), mong_doi)
                self.assertIs(crawlers.la_tin_muc_tieu(tieu_de), bool(mong_doi))
        self.assertEqual(crawlers.chuan_van_ban("Kỹ sư Dữ liệu"), "ky su du lieu")
        self.assertEqual(list(crawlers.doc_keyword()["nhom"]), ["DA", "DS", "DE", "AI", "BE"])

    def test_file_keyword_khong_doc_duoc(self):
        loc_keyword.doc_keyword.cache_clear()
        self.addCleanup(loc_keyword.doc_keyword.cache_clear)
        with TemporaryDirectory() as thu_muc, patch.object(loc_keyword, "THU_MUC_GOC", Path(thu_muc)):
            with self.assertRaisesRegex(ValueError, "keyword.json"):
                loc_keyword.doc_keyword()
            (Path(thu_muc) / "keyword.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "keyword.json"):
                loc_keyword.doc_keyword()


class KiemThuBase(unittest.TestCase):
    def setUp(self):
        self.thu_muc = TemporaryDirectory()
        self.addCleanup(self.thu_muc.cleanup)
        self.duong_dan = Path(self.thu_muc.name) / "raw.csv"
        self.schema = crawlers.doc_schema()
        self.dong = {
            "Nguon": "topcv", "URL_Goc": "https://example.com/job/1?ref=abc",
            "Timestamp": crawlers.danh_dau_bat_dau(), "Tieu_De": "Data Analyst",
            "Cong_Ty": "Công ty", "Dia_Diem_Goc": "Hà Nội",
            "Mo_Ta_Cong_Viec_Goc": '  Mô tả, "Python"\nDòng mới  ',
        }

    def test_robots_va_host(self):
        noi_dung = "User-agent: *\nDisallow: /private\nUser-agent: FakeBot\nDisallow: /fake\n"
        with patch("crawlers.base_crawler.urllib.request.urlopen", return_value=PhanHoiGia(noi_dung)) as tai:
            rp, loi = crawlers.kiem_thu_robot("https://example.com/", ["https://example.com/job"], "Other")
            self.assertIsInstance(rp, RobotFileParser)
            self.assertEqual(loi, "")
            self.assertEqual(tai.call_args.args[0].full_url, "https://example.com/robots.txt")
            self.assertEqual(tai.call_args.args[0].get_header("User-agent"), "Other")
            self.assertFalse(crawlers.duoc_phep(rp, "https://example.com", "https://www.example.com/private", "Other"))
            self.assertTrue(crawlers.duoc_phep(rp, "https://example.com", "https://www.example.com/fake", "Other"))
            self.assertFalse(crawlers.duoc_phep(rp, "https://example.com", "https://khac.com/job", "Other"))
            rp_cam, ly_do = crawlers.kiem_thu_robot("https://example.com", ["https://example.com/fake"], "FakeBot")
            self.assertIsNone(rp_cam)
            self.assertIn("không cho phép", ly_do)
        for ma in (403, 404, 429, 500):
            with self.subTest(ma=ma):
                loi = urllib.error.HTTPError("https://example.com", ma, "error", Message(), None)
                with patch("crawlers.base_crawler.urllib.request.urlopen", side_effect=loi):
                    rp_loi, ly_do = crawlers.kiem_thu_robot("https://example.com", [], "bot")
                    self.assertIsNone(rp_loi)
                    self.assertIn(str(ma), ly_do)
                    if ma == 404:
                        self.assertIn("không tìm thấy", ly_do)
        with patch("crawlers.base_crawler.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            rp_loi, ly_do = crawlers.kiem_thu_robot("https://example.com", [], "bot")
            self.assertIsNone(rp_loi)
            self.assertIn("lỗi mạng", ly_do)
        self.assertIsNone(crawlers.kiem_thu_robot("invalid", [], "bot")[0])

    def test_retry_va_ngat_mach(self):
        thong_ke = Counter()
        tai = Mock(return_value=(None, "loi_tam_thoi"))
        nghi = Mock()
        with patch("crawlers.base_crawler.random.uniform", side_effect=[3, 0.5, 0.5, 0.5] * 2):
            for trang_thai in ("that_bai", "ngat_mach"):
                self.assertEqual(crawlers.tai_thu_lai(tai, "url", thong_ke, so_lan_thu=3,
                                                      tran_cho=3, nguong_ngat=2, ham_nghi=nghi), (None, trang_thai))
        self.assertEqual(tai.call_count, 8)
        self.assertEqual([cuoc_goi.args[0] for cuoc_goi in nghi.call_args_list[:4]], [3, 2.5, 3.5, 3.5])
        self.assertEqual(thong_ke["loi_lien_tiep"], 2)

    def test_trang_thai_khong_retry(self):
        for ma in ("ok", "khong_ton_tai", "bi_cam", "bi_chan", "ma_la", "exception"):
            with self.subTest(ma=ma):
                thong_ke = Counter(loi_lien_tiep=1)
                tai = Mock(side_effect=RuntimeError("lỗi giả")) if ma == "exception" else Mock(return_value=("html", ma))
                with patch("builtins.print") as in_loi:
                    ket_qua = crawlers.tai_thu_lai(tai, "url", thong_ke, ham_nghi=Mock())
                if ma == "exception":
                    in_loi.assert_called_once_with("Lỗi khi tải trang: RuntimeError: lỗi giả")
                else:
                    in_loi.assert_not_called()
                mong_doi = "that_bai" if ma in ("ma_la", "exception") else ma
                self.assertEqual(ket_qua, ("html" if ma == "ok" else None, mong_doi))
                self.assertEqual(tai.call_count, 1)
                self.assertEqual(sum(v for k, v in thong_ke.items() if k != "loi_lien_tiep"), 1)
                self.assertEqual(thong_ke["loi_lien_tiep"], 0 if ma in ("ok", "khong_ton_tai") else 2 if ma in ("ma_la", "exception") else 1)

    def test_csv_giu_du_lieu_va_kiem_tra(self):
        crawlers.xuat_csv(self.duong_dan, [])
        self.assertFalse(self.duong_dan.exists())
        with patch("builtins.print") as in_canh_bao:
            crawlers.xuat_csv(self.duong_dan, [dict(self.dong, thua=1, Ky_Nang_Goc=["Python", "SQL"])])
            in_canh_bao.assert_called_once()
        with self.duong_dan.open(encoding="utf-8-sig", newline="") as tep:
            self.assertEqual(csv.DictReader(tep).fieldnames, self.schema["required"])
        dong = crawlers.doc_csv(self.duong_dan)[0]
        self.assertEqual(dong["Mo_Ta_Cong_Viec_Goc"], self.dong["Mo_Ta_Cong_Viec_Goc"])
        self.assertEqual(dong["URL_Goc"], self.dong["URL_Goc"])
        self.assertEqual(json.loads(dong["Ky_Nang_Goc"]), ["Python", "SQL"])
        self.assertIsNone(dong["Luong_Goc"])
        with patch("builtins.print") as in_canh_bao:
            crawlers.xuat_csv(self.duong_dan, [self.dong])
            in_canh_bao.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Dòng 1.*Tieu_De"):
            crawlers.xuat_csv(self.duong_dan, [dict(self.dong, Tieu_De="  ")])

    def test_csv_an_toan_khi_loi(self):
        self.duong_dan.write_bytes(b"wrong,header\n1,2\n")
        truoc = self.duong_dan.read_bytes()
        with self.assertRaises(ValueError):
            crawlers.doc_csv(self.duong_dan)
        self.assertEqual(self.duong_dan.read_bytes(), truoc)
        with patch("crawlers.base_crawler.os.replace", side_effect=OSError("cannot replace")):
            with self.assertRaises(OSError):
                crawlers.xuat_csv(self.duong_dan, [self.dong])
        self.assertEqual(self.duong_dan.read_bytes(), truoc)
        self.assertEqual(list(self.duong_dan.parent.glob("*.tmp")), [])
        with patch("crawlers.base_crawler.tempfile.mkstemp") as tao:
            with self.assertRaises(ValueError):
                crawlers.xuat_csv(self.duong_dan, [{}])
            tao.assert_not_called()

    def test_url_thoi_gian_va_nghi(self):
        self.assertEqual(crawlers.khoa_url("https://WWW.Example.com/job/1/?id=5"), ("example.com", "/job/1"))
        self.assertEqual(crawlers.khoa_url("https://example.com"), ("example.com", "/"))
        self.assertRegex(crawlers.danh_dau_bat_dau(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
        nghi = Mock()
        with patch("crawlers.base_crawler.random.uniform", return_value=3):
            crawlers.nghi_ngau_nhien(ham_nghi=nghi)
        nghi.assert_called_once_with(3)

    def test_phoi_hop_va_tiep_tuc_sau_gian_doan(self):
        danh_sach = [
            ("https://example.com/job/1?ref=one", "Data Analyst"),
            ("https://www.example.com/job/1?ref=two", "DA"),
            ("https://example.com/job/2", "Frontend Developer"),
            ("https://example.com/private", "Data Engineer"),
            ("https://example.com/job/3", "Data Engineer"),
        ]
        with patch("crawlers.base_crawler.urllib.request.urlopen",
                   return_value=PhanHoiGia("User-agent: *\nDisallow: /private\n")):
            rp, loi = crawlers.kiem_thu_robot("https://example.com", [], "bot")
        self.assertEqual(loi, "")
        thong_ke = Counter()
        for lan in range(2):
            cac_dong = crawlers.doc_csv(self.duong_dan)
            da_luu = {crawlers.khoa_url(dong["URL_Goc"]) for dong in cac_dong}
            try:
                for url, tieu_de in danh_sach:
                    khoa = crawlers.khoa_url(url)
                    if khoa in da_luu or not crawlers.duoc_phep(rp, "https://example.com", url, "bot"):
                        continue
                    if not crawlers.la_tin_muc_tieu(tieu_de):
                        continue
                    thoi_gian = crawlers.danh_dau_bat_dau()
                    noi_dung, trang_thai = crawlers.tai_thu_lai(
                        Mock(return_value=(tieu_de, "ok")), url, thong_ke, ham_nghi=Mock()
                    )
                    self.assertEqual(trang_thai, "ok")
                    cac_dong.append(dict(self.dong, URL_Goc=url, Tieu_De=noi_dung, Timestamp=thoi_gian))
                    da_luu.add(khoa)
                    if lan == 0:
                        raise KeyboardInterrupt
            except KeyboardInterrupt:
                pass
            finally:
                crawlers.xuat_csv(self.duong_dan, cac_dong)
        cac_dong = crawlers.doc_csv(self.duong_dan)
        self.assertEqual([dong["URL_Goc"] for dong in cac_dong],
                         [danh_sach[0][0], danh_sach[4][0]])
        self.assertEqual(thong_ke["ok"], 2)


if __name__ == "__main__":
    unittest.main()
