"""Đọc, kiểm tra và gộp CSV thô theo schema chung."""

import csv
import json
import re
import tempfile
from datetime import datetime
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.json"


@cache
def load_schema() -> dict:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Không tìm thấy schema: {SCHEMA_PATH}") from exc


def coerce(value) -> str | None:
    if value is None or value == "" or value == [] or value == {} or value == ():
        return None
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    return text if text.strip() else None


def load_raw(path: str | Path) -> list[dict[str, str | None]]:
    columns = load_schema()["required"]
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if header != columns:
            raise ValueError(
                f"{path}: cột thiếu={sorted(set(columns) - set(header))}, "
                f"cột thừa={sorted(set(header) - set(columns))}, thứ tự khớp={header == columns}"
            )
        return [{key: value if value != "" else None for key, value in row.items()}
                for row in reader]


def check_row(row: dict) -> list[str]:
    schema = load_schema()
    errors = []
    if row.get("Nguon") not in schema["properties"]["Nguon"]["enum"]:
        errors.append("Nguon không hợp lệ")
    url = row.get("URL_Goc")
    if not isinstance(url, str) or not re.match(schema["properties"]["URL_Goc"]["pattern"], url):
        errors.append("URL_Goc không hợp lệ")
    try:
        stamp = datetime.fromisoformat((row.get("Timestamp") or "").replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            errors.append("Timestamp thiếu múi giờ")
    except (TypeError, ValueError, AttributeError):
        errors.append("Timestamp không hợp lệ")
    if set(row) - set(schema["required"]):
        errors.append("Có khóa ngoài schema")
    return errors


def merge_raw(paths, out_path: str | Path) -> None:
    columns = load_schema()["required"]
    rows, seen = [], set()
    total = duplicates = invalid = 0
    for path in paths:
        for row in load_raw(path):
            total += 1
            if check_row(row):
                invalid += 1
                continue
            url = urlsplit(row["URL_Goc"])
            key = ((row["Nguon"], row["Ma_Tin_Nguon"])
                   if row["Ma_Tin_Nguon"] else (url.netloc.lower(), url.path.rstrip("/")))
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            rows.append(row)
    if not rows:
        print(f"Không có dòng hợp lệ: đọc={total}, lỗi={invalid}, trùng={duplicates}".encode("ascii", "backslashreplace").decode("ascii"))
        return
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp = handle.name
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        Path(temp).replace(target)
    finally:
        if temp and Path(temp).exists():
            Path(temp).unlink()
    print(f"Đã gộp {len(rows)} tin: đọc={total}, trùng={duplicates}, lỗi={invalid}; {target}".encode("ascii", "backslashreplace").decode("ascii"))
