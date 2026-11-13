import csv
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from crawlers import BaseCrawler, load_raw, merge_raw
from crawlers.schema_utils import load_schema


class FakeCrawler(BaseCrawler):
    SOURCE = "topcv"

    def __init__(self, jobs, fail=False):
        super().__init__(); self.jobs, self.fail = jobs, fail

    def iter_jobs(self, *, max_pages=None):
        yield from self.jobs
        if self.fail:
            raise RuntimeError("nguồn dừng")


class BaseCrawlerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "raw_topcv.csv"
        self.job = {"URL_Goc": "https://example.com/job/1?a=1", "Tieu_De": "  ",
                    "Ky_Nang_Goc": ["Python", datetime(2026, 11, 13)], "Luong_Goc": 30}

    def test_raw_fields_and_duplicates(self):
        jobs = [self.job, {**self.job, "URL_Goc": "https://example.com/job/1?a=2"},
                {"URL_Goc": "bad"}, None, {**self.job, "URL_Goc": "https://example.com/job/2",
                                           "Luong_goc": "khóa lạ"}]
        result = FakeCrawler(jobs).crawl(output_path=self.path)
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, load_schema()["required"])
            rows = list(reader)
        self.assertEqual((result.saved, result.duplicates, result.skipped), (2, 1, 2))
        self.assertTrue(all(row["URL_Goc"] for row in rows))
        self.assertEqual((rows[0]["Ky_Nang_Goc"], rows[0]["Luong_Goc"], rows[0]["Tieu_De"]),
                         ('["Python", "2026-11-13 00:00:00"]', "30", ""))
        self.assertFalse(Path(str(self.path) + ".partial.jsonl").exists())

    def test_partial_keeps_good_csv(self):
        self.path.write_text("old", encoding="utf-8")
        result = FakeCrawler([self.job], fail=True).crawl(output_path=self.path)
        self.assertEqual((result.status, result.saved), ("partial", 1))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old")
        self.assertTrue(result.output_path.exists() and Path(str(self.path) + ".partial.jsonl").exists())

    def test_excel_lock_saves_fallback(self):
        self.path.write_text("old", encoding="utf-8")
        with patch("os.replace", side_effect=PermissionError("Excel")):
            result = FakeCrawler([self.job]).crawl(output_path=self.path)
        self.assertEqual((result.status, result.saved), ("partial", 1))
        self.assertTrue(self.path.read_text(encoding="utf-8") == "old" and result.output_path.exists())

    def test_bad_tracked_column(self):
        schema = {**load_schema(), "x-tracked-fields": ["Khong_Co"]}
        with patch("crawlers.base_crawler.load_schema", return_value=schema), self.assertRaises(ValueError):
            FakeCrawler([])

    def test_load_raw_and_merge(self):
        columns = load_schema()["required"]
        a, b = Path(self.temp.name) / "a.csv", Path(self.temp.name) / "b.csv"
        row = dict.fromkeys(columns, "")
        row.update(Nguon="topcv", URL_Goc="https://example.com/job/1",
                   Timestamp="2026-11-13T10:00:00+07:00", Ma_Tin_Nguon="1")
        for path, rows in ((a, [row]), (b, [row, {**row, "Ma_Tin_Nguon": "2",
                                                "URL_Goc": "https://example.com/job/2"}])):
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
        bad = Path(self.temp.name) / "bad.csv"
        bad.write_text("wrong\nvalue\n", encoding="utf-8")
        with self.assertRaises(ValueError): load_raw(bad)
        out = Path(self.temp.name) / "merged.csv"
        merge_raw([a, b], out)
        self.assertEqual(len(load_raw(out)), 2)
