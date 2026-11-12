# Crawler tuyển dụng CNTT – phiên bản chỉnh sửa

## Cấu trúc
Đặt thư mục `crawlers/` này vào project, giữ nguyên tên thư mục để các import `from crawlers...` hoạt động.

## Cài đặt
```powershell
python -m pip install requests beautifulsoup4 lxml playwright
python -m playwright install
```
Các crawler dùng Chrome cài trên máy (`channel="chrome"`). Cần cài Google Chrome.

## Chạy thử từng nguồn
Chạy từ thư mục gốc project (thư mục cha của `crawlers/`):
```powershell
python -m crawlers.itviec --pages 5 --limit 100
python -m crawlers.topcv --pages 5 --limit 100
python -m crawlers.topdev --pages 5 --limit 100
python -m crawlers.vietnamworks --pages 5 --limit 100
python -m crawlers.linkedin --scrolls 10
```

Lấy mô tả công việc ITviec/TopCV/TopDev (best-effort; selector trang chi tiết có thể cần cập nhật):
```powershell
python -m crawlers.itviec --pages 5 --limit 100 --details --detail-limit 20
python -m crawlers.topcv --pages 5 --limit 100 --details --detail-limit 20
python -m crawlers.topdev --pages 5 --limit 100 --details --detail-limit 20
```

Mỗi nguồn xuất:
- `data/raw/<source>.jsonl`: dữ liệu thô dạng JSON Lines.
- `data/raw/<source>.csv`: CSV UTF-8-SIG, thuận tiện mở bằng Excel.

## Schema chung
`site`, `job_url`, `title`, `company`, `location`, `salary` (giữ nguyên chuỗi gốc),
`experience_level`, `description`, `requirements`, `benefits`, `skills`,
`posted_at`, `work_model`, `job_type`, `timestamp`, `raw_fields`.

`timestamp` là thời điểm crawler ghi nhận tin (UTC ISO-8601), không phải ngày đăng tuyển.
`posted_at` là thông tin ngày đăng do nền tảng cung cấp nếu có.
`detail_fetch_timestamp` và `detail_fetch_status` được thêm khi bật `--details`.

## Lưu ý học thuật và vận hành
- Không đảm bảo một số lượng tin cố định: số tin phụ thuộc dữ liệu đang hiển thị, phân trang, bộ lọc và giới hạn của nền tảng.
- Không giả định API/HTML selector luôn ổn định. Kiểm tra thủ công một số `job_url` và nội dung trước khi phân tích.
- `--details` là trích xuất best-effort; cần kiểm tra chất lượng JD, requirements, benefits trước khi dùng.
- Không né CAPTCHA, đăng nhập trái phép, proxy rotation hoặc biện pháp chống truy cập. Nếu bị chặn, dừng và chuyển nguồn/phương thức được nền tảng cho phép.
- Crawler không tự chuẩn hóa lương, địa điểm, kinh nghiệm hoặc kỹ năng. Giữ nguyên dữ liệu nguồn để bước Data Cleaning xử lý riêng.
- Kiểm tra điều khoản sử dụng, robots.txt và giới hạn truy cập của từng nền tảng trước khi chạy ở quy mô lớn.
