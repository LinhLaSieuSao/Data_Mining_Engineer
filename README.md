# Thu thập và khai phá dữ liệu tuyển dụng CNTT tại Việt Nam

Đồ án môn Khai phá dữ liệu (ITEC3417) · Nhóm 9 · Lớp DH24DS01

## Hướng dẫn Giảng viên Nghiệm thu & Chạy lại Toàn bộ Công cụ (Reproduction Guide)

Phần này được biên soạn dành cho Giảng viên và Người thẩm định để kiểm tra tính trung thực, phương pháp thu thập có trách nhiệm (`robots.txt`, `crawl-delay`) và tái lập kết quả cào dữ liệu của từng nền tảng tuyển dụng.

---

### 1. Chuẩn bị môi trường

Yêu cầu môi trường **Python 3.13+** (hoặc 3.11–3.15). Mở terminal tại thư mục gốc dự án `Data_Mining_Engineer`:

```powershell
# 1. Khởi tạo và kích hoạt môi trường ảo
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Cài đặt các thư viện phụ thuộc
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Cài đặt trình duyệt cho Playwright
python -m playwright install chromium
```
*(Trên macOS/Linux: kích hoạt bằng `source .venv/bin/activate`).*

---

### 2. Cơ chế Chrome Remote Debugging (CDP) & Lấy ID/Trạng thái Chrome trước khi cào lương

> [!IMPORTANT]
> **Tại sao cần cơ chế này?**
> Hai nền tảng **ITviec** và **Saramin** ẩn mức lương đằng sau yêu cầu đăng nhập và được bảo vệ bởi **Cloudflare Turnstile**. Nếu dùng script tự động bật trình duyệt, Cloudflare sẽ phát hiện cờ bot (`navigator.webdriver = true`) và chặn lại ngay lập tức (HTTP 403).
> 
> **Giải pháp kỹ thuật của nhóm:** Áp dụng mô hình **Human-in-the-Loop** thông qua giao thức **Chrome DevTools Protocol (CDP)**:
> 1. Người dùng/Giảng viên tự mở một tiến trình Google Chrome thật độc lập với cổng gỡ lỗi (`port 9222`).
> 2. Người dùng tự đăng nhập và vượt Cloudflare hợp pháp trên trình duyệt thật 100%.
> 3. Crawler kết nối vào cổng gỡ lỗi này (`--cdp`) để đọc DOM mức lương thực tế mà không vi phạm bot-protection.

#### Bước 2.1: Lệnh khởi chạy Google Chrome gỡ lỗi

Tắt các cửa sổ Chrome đang chạy, sau đó chạy lệnh mở Chrome thật với profile riêng biệt tại thư mục an toàn:

* **Trên Windows PowerShell:**
  ```powershell
  & "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome_dev_profile"
  ```
* **Trên Command Prompt (CMD) hoặc hộp thoại Run (`Win + R`):**
  ```cmd
  chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome_dev_profile"
  ```
* **Trên Git Bash / Linux / macOS:**
  ```bash
  google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome_dev_profile"
  # (hoặc trên macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome_dev_profile")
  ```

#### Bước 2.2: Rà soát & Lấy ID Chrome trước khi cào (Kiểm tra cổng 9222)

Trước khi chạy script, Giảng viên có thể kiểm tra xem tiến trình Chrome đã mở đúng cổng gỡ lỗi và lấy các thông số định danh (Browser ID, WebSocket Debugger URL, Page ID) bằng 2 cách:

1. **Kiểm tra trực tiếp trên trình duyệt hoặc qua PowerShell:**
   Truy cập endpoint nội bộ: [http://localhost:9222/json/version](http://localhost:9222/json/version)
   Hoặc chạy lệnh PowerShell:
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:9222/json/version"
   ```
   *Kết quả trả về sẽ hiển thị thông tin Chrome ID và cổng lắng nghe:*
   ```json
   {
      "Browser": "Chrome/157.0.8103.79",
      "Protocol-Version": "1.3",
      "webSocketDebuggerUrl": "ws://localhost:9222/devtools/browser/076e586a-245e-485a-8c4f-90731b9e05cd"
   }
   ```

2. **Lấy ID tab và URL trang đang mở:**
   Truy cập [http://localhost:9222/json/list](http://localhost:9222/json/list) để lấy `id` của tab hiện tại, xác nhận tab ITviec hoặc Saramin đã sẵn sàng:
   ```powershell
   python -c "import urllib.request, json; [print('Tab ID:', t['id'], '| URL:', t['url']) for t in json.loads(urllib.request.urlopen('http://localhost:9222/json/list').read()) if t.get('type')=='page']"
   ```

#### Bước 2.3: Đăng nhập tài khoản trên cửa sổ Chrome đó
1. Trên cửa sổ Chrome vừa mở, Giảng viên truy cập [https://itviec.com](https://itviec.com) và [https://saramin.vn](https://saramin.vn).
2. Hoàn tất xác minh Cloudflare nếu có (trên Chrome thật chỉ cần tick 1 lần là duyệt ngay).
3. Đăng nhập tài khoản người dùng và **để nguyên cửa sổ Chrome mở trong suốt quá trình cào lương**.

---

### 3. Lệnh chạy nghiệm thu từng Crawler (Chế độ Demo kiểm tra nhanh)

Các lệnh dưới đây được cấu hình giới hạn số tin (`limit`) để Giảng viên có thể chạy thử và kiểm chứng trong vòng 1–2 phút:

#### A. Nguồn ITviec
1. **Cào dữ liệu danh sách và chi tiết công khai:**
   ```powershell
   python crawlers/itviec.py --nhom "Data Analyst" --chi-danh-muc --limit 5
   ```
2. **Bổ sung lương hiển thị qua Chrome thật (CDP):**
   ```powershell
   python crawlers/browser.py --cdp --limit 5
   ```

#### B. Nguồn Saramin
1. **Cào tin mới kèm bộ lọc kỹ năng Data (`--filter-skills`):**
   ```powershell
   python crawlers/saramin.py --cdp --filter-skills --keyword "Data Engineer" --target 5 --delay-min 3 --delay-max 5
   ```
2. **Chỉ bổ sung lương cho các tin đã có trong CSV qua Chrome thật:**
   ```powershell
   python -u crawlers/saramin.py --cdp --salary-only --salary-limit 5
   ```

#### C. Nguồn TopCV
```powershell
python crawlers/topcv.py --keyword "Data Analyst" --max-pages 1 --limit 5
```

#### D. Nguồn CareerViet
```powershell
python crawlers/carrerviet.py --max-pages 1 --target 5 --no-headless
```

#### E. Nguồn VietnamWorks
```powershell
python -m crawlers.vietnamworks --tu-khoa "Data Analyst" --so-trang 1 --gioi-han 5
```

---

### 4. Quy trình Rà soát & Kiểm tra Tính Đúng đắn của Dữ liệu

Sau khi chạy xong, Giảng viên có thể chạy các đoạn lệnh sau để nghiệm thu chất lượng dữ liệu:

#### 4.1. Kiểm tra cấu trúc 18 cột và số lượng bản ghi
```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/raw/raw_itviec.csv')
print(f'Số lượng bản ghi: {len(df)}')
print(f'Số cột: {len(df.columns)} (Kỳ vọng: 18)')
print('Danh sách cột:', df.columns.tolist())
"
```

#### 4.2. Kiểm tra tính toàn vẹn của các cột bắt buộc (Không được rỗng)
Theo `schema.json`, các cột `Tieu_De`, `Ten_Cong_Ty`, `Dia_Diem`, `Mo_Ta_Cong_Viec`, `URL_Goc` không được phép null:
```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/raw/raw_itviec.csv')
bat_buoc = ['Tieu_De', 'Ten_Cong_Ty', 'Dia_Diem', 'Mo_Ta_Cong_Viec', 'URL_Goc']
print('Kiểm tra ô trống các cột bắt buộc:')
for c in bat_buoc:
    print(f' - {c}: {df[c].isna().sum()} ô trống')
"
```

#### 4.3. Kiểm tra chuẩn 1 dòng vật lý trên mỗi tin
Kiểm tra xem file CSV có bị gãy dòng do ký tự xuống dòng trong mô tả công việc hay không (mỗi tin chiếm đúng 1 dòng vật lý):
```powershell
python -c "
with open('data/raw/raw_itviec.csv', 'r', encoding='utf-8-sig') as f:
    so_dong_file = sum(1 for _ in f)
import pandas as pd
so_dong_df = len(pd.read_csv('data/raw/raw_itviec.csv')) + 1
print(f'Số dòng vật lý trong file: {so_dong_file}')
print(f'Số dòng theo DataFrame (+header): {so_dong_df}')
assert so_dong_file == so_dong_df, 'LỖI: CSV không đạt chuẩn 1 dòng vật lý!'
print('=> Chuẩn 1 dòng vật lý: ĐẠT')
"
```

#### 4.4. Đối chiếu ngẫu nhiên với tin thực tế trên web
Mở 3 URL ngẫu nhiên trong CSV để đối chiếu với trang web gốc:
```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/raw/raw_itviec.csv')
mau = df.sample(min(3, len(df)))[['Tieu_De', 'Ten_Cong_Ty', 'Luong', 'URL_Goc']]
print(mau.to_string())
"
```

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
