# Thu thập và khai phá dữ liệu tuyển dụng CNTT tại Việt Nam

Đồ án môn Khai phá dữ liệu (ITEC3417) · Nhóm 9 · Lớp DH24DS01

## Chạy lại công cụ

### 1. Cài đặt

Dùng Python 3.13 trở lên. Mở terminal trong thư mục chứa `README.md`. Trên Windows PowerShell, chạy các lệnh sau.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Trên macOS/Linux, lệnh kích hoạt môi trường là `source .venv/bin/activate`.

### 2. Thu thập dữ liệu

Chọn lệnh tương ứng với nguồn cần chạy. Các ví dụ giới hạn số trang hoặc số tin để tiện kiểm tra.

```bash
python crawlers/carrerviet.py --max-pages 1
python crawlers/saramin.py --max-pages 1
python crawlers/topdev.py --max-pages 1
python crawlers/itviec.py --nhom "Data Analyst" --chi-danh-muc --limit 20
python crawlers/topcv.py --keyword "Data Analyst" --max-pages 2 --limit 5
python crawlers/vietnamworks.py --tu-khoa "Data Analyst" --so-trang 1 --gioi-han 20
```

Có thể bổ sung lương còn thiếu cho ITviec bằng lệnh dưới đây. Khi cửa sổ trình duyệt mở, đăng nhập thủ công để công cụ đọc mức lương hiển thị.

```bash
python crawlers/browser.py --limit 20
```

Thêm `--help` sau tên script để xem các tùy chọn của crawler.

### 3. Kiểm tra kết quả

Các crawler tiếp tục từ dữ liệu đã lưu và cập nhật CSV tương ứng trong `data/raw/`. Bộ CSV nộp kèm có 1.089 bản ghi. Mỗi tệp có 18 cột theo `schema.json`. Dùng `URL_Goc` để đối chiếu với tin tuyển dụng gốc.

## Cấu trúc thư mục

```text
.
├── .gitignore
├── README.md
├── requirements.txt
├── keyword.json
├── schema.json
├── crawlers/
│   ├── __init__.py
│   ├── base_crawler.py
│   ├── browser.py
│   ├── carrerviet.py
│   ├── itviec.py
│   ├── saramin.py
│   ├── topcv.py
│   ├── topdev.py
│   └── vietnamworks.py
└── data/
    └── raw/
        ├── raw_careerviet.csv
        ├── raw_itviec.csv
        ├── raw_saramin.csv
        ├── raw_topcv.csv
        ├── raw_topdev.csv
        └── raw_vietnamworks.csv
```

## Phân công công việc

| Thành viên | Nguồn phụ trách | Công việc khác |
| --- | --- | --- |
| Trần Đăng Khoa | CareerViet, Saramin, TopDev | Quản lý thư viện, kiểm tra và gộp dữ liệu, chuẩn hóa lương, địa điểm và kinh nghiệm, viết báo cáo |
| Lưu Đức Linh | ITviec, TopCV | README, schema và khung crawler, phân tích khám phá dữ liệu (EDA), phân lớp, làm slide cùng Hiếu |
| Trần Minh Hiếu | VietnamWorks | Làm sạch văn bản, trích xuất kỹ năng, gom cụm và khai phá luật kết hợp, làm slide cùng Linh |
