# Thu thập và khai phá dữ liệu tuyển dụng CNTT tại Việt Nam

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-3776AB)](requirements.txt)
[![Playwright 1.65.1+](https://img.shields.io/badge/Playwright-1.65.1%2B-2EAD33)](requirements.txt)
[![pandas 3.1.1+](https://img.shields.io/badge/pandas-3.1.1%2B-150458)](requirements.txt)
[![scikit-learn 1.7.2+](https://img.shields.io/badge/scikit--learn-1.7.2%2B-F7931E)](requirements.txt)
[![mlxtend 0.23.4+](https://img.shields.io/badge/mlxtend-0.23.4%2B-6A5ACD)](requirements.txt)
![Project status: planning](https://img.shields.io/badge/status-planning-yellow)

**Nội Dung:** [Mục tiêu](#2-mục-tiêu-và-câu-hỏi-nghiên-cứu) · [Nguồn dữ liệu](#4-nguồn-và-cách-thu-thập) · [Pipeline](#5-quy-trình-xử-lý-và-schema) · [Tải và chạy](#8-tải-cài-đặt-và-chạy-lại) · [Sản phẩm](#9-kết-quả-và-sản-phẩm-nộp) · [Tiến độ](#10-tiến-độ-và-phương-án-dự-phòng).

## 1. Giới thiệu

Đồ án môn **Khai phá dữ liệu (ITEC3417)** nghiên cứu tin tuyển dụng công nghệ thông tin và các ngành liên quan tại Việt Nam, với **trọng tâm Data Science, Data Analytics, AI và Machine Learning** theo bảng phân công. Nhóm tự xây dựng công cụ thu thập dữ liệu, tạo bộ dữ liệu thô và sạch, rồi thực hiện EDA, gom cụm, khai phá luật kết hợp và phân lớp theo yêu cầu đề bài.

| Thông tin | Nội dung |
| --- | --- |
| Nhóm | Tam Tấu |
| Thành viên | Lưu Đức Linh; Trần Đăng Khoa; Trần Minh Hiếu |
| Lớp | DH24DS01 |
| Thời gian thu thập dự kiến | 12–16/11/2026 |
| Hạn hoàn thiện và nộp dự kiến | Hoàn thiện báo cáo/slide 20/11; nộp trên LMS 21/11/2026 |
| Nguồn dự kiến | ITviec, TopCV, VietnamWorks |

Mục tiêu thu thập theo đề bài là khoảng **800–1.500+ tin tuyển dụng thô**. Số tin thực tế, tỷ lệ thiếu dữ liệu và kết quả phân tích sẽ chỉ được ghi sau khi chạy và kiểm tra.

## 2. Mục tiêu và câu hỏi nghiên cứu

Nhóm dự kiến trả lời bốn câu hỏi sau trong phạm vi mẫu thu thập:

1. Những kỹ năng, vị trí, cấp bậc và khu vực nào xuất hiện nhiều trong tin tuyển CNTT?
2. Mức lương được công bố thay đổi thế nào theo cấp bậc, địa điểm và nhóm kỹ năng?
3. Có thể chia các tin tuyển thành những nhóm công việc nào dựa trên kỹ năng và nội dung mô tả? Những kỹ năng nào thường được yêu cầu cùng nhau?
4. Với những tin có lương số hợp lệ, có thể dự đoán **khoảng lương** từ cấp bậc, kinh nghiệm, địa điểm và kỹ năng không?


Đây là **câu hỏi và thiết kế dự kiến**, chưa phải kết luận về thị trường lao động Việt Nam.

## 3. Phạm vi và định nghĩa dữ liệu

- **Tin thuộc phạm vi:** vị trí Data Science, Data Analytics, AI, Machine Learning và các vị trí CNTT liên quan có nhiệm vụ/kỹ năng công nghệ rõ ràng. Bộ từ khóa gồm tên vị trí và kỹ năng cốt lõi; các ví dụ trong bảng phân công là Python, SQL, Power BI, PyTorch và Spark. Danh sách tìm kiếm chính thức, nhóm vị trí được nhận/loại và cách xử lý tin mơ hồ: [Ghi lại bộ lọc đã chốt].
- **Khoảng thu thập:** 12–16/11/2026; thời điểm đăng tin trên website có thể khác thời điểm crawler thu thập.
- **Tin trùng:** trước tiên nhận diện cùng URL sau khi bỏ tham số theo dõi và dấu `/` cuối. Tin có cùng tên công ty, tiêu đề và địa điểm sẽ được đánh dấu để kiểm tra; **không tự động xóa tin khác URL hoặc khác nguồn** khi chưa xác minh là cùng một vị trí.
- **Lương hợp lệ cho phân tích số:** có đơn vị tiền và kỳ trả lương xác định được. “Thỏa thuận”, khoảng không rõ đơn vị hoặc giá trị không chuyển đổi tin cậy được giữ trong cột gốc nhưng để thiếu ở cột lương số.
- **Tính đại diện:** mẫu là các tin tìm được theo nguồn, từ khóa và thời gian đã chọn; không mặc nhiên đại diện cho toàn bộ thị trường CNTT Việt Nam.

## 4. Nguồn và cách thu thập

| Nguồn | Người phụ trách | Script dự kiến | CSV nguồn dự kiến |
| --- | --- | --- | --- |
| ITviec | Lưu Đức Linh | `crawlers/scrape_itviec.py` | `data/raw/raw_itviec.csv` |
| TopCV | Trần Đăng Khoa | `crawlers/scrape_topcv.py` | `data/raw/raw_topcv.csv` |
| VietnamWorks | Trần Minh Hiếu | `crawlers/scrape_vietnamworks.py` | `data/raw/raw_vietnamworks.csv` |

**URL tìm kiếm, từ khóa thực dùng, bộ lọc, phân trang và số tin theo từng nguồn:** [Bổ sung trước và sau khi cào]. Khung `BaseCrawler` thống nhất đầu ra; từng crawler nguồn tự chọn Playwright hoặc HTTP/API, cách phân trang và lấy nội dung chi tiết. Chưa có ba script nguồn trên nhánh này nên chưa xác nhận khả năng cào thực tế. Mỗi bản ghi giữ văn bản gốc, `URL_Goc`, `Timestamp` và tên nguồn để giảng viên đối chiếu ngẫu nhiên với tin đăng và chạy demo tại lớp.

### Thu thập có trách nhiệm

Trước khi chạy từng crawler, nhóm sẽ kiểm tra `robots.txt` và điều khoản của website đó, ghi lại quyết định sử dụng dữ liệu trong mục nguồn tham khảo. Crawler cần dùng tốc độ truy cập hợp lý, thời gian chờ giữa các yêu cầu và User-Agent có thể nhận diện; không vượt cơ chế đăng nhập hoặc kiểm soát truy cập. Nhóm không thu thập thông tin cá nhân của ứng viên và không đưa cookie, tài khoản hoặc khóa truy cập vào repository. Dữ liệu chỉ phục vụ đồ án học thuật; quyền chia sẻ từng tệp sẽ được xác nhận trước khi công bố.

## 5. Quy trình xử lý và schema

```text
Cả nhóm: chốt README, requirements.txt, schema.json và khung crawler
    ↓
ITviec / TopCV / VietnamWorks → 3 CSV nguồn trong data/raw/
    ↓
Ánh xạ cột theo nguồn → kiểm tra schema → cả nhóm gộp và khử trùng
    ↓
data/raw_data.csv (bản gộp còn giữ nội dung gốc)
    ↓
Khoa: chuẩn hóa lương, địa điểm, kinh nghiệm → data/normalized_data.csv
    ↓
Hiếu: làm sạch mô tả, trích xuất kỹ năng → data/clean_data.csv
    ↓
Linh: EDA, phân lớp · Hiếu: gom cụm, luật kết hợp
    ↓
Cả nhóm: ghép notebook và kiểm tra chéo 
    ↓
Khoa: báo cáo
    ↓
Linh và Hiếu: slide
```

### Bảng pipeline dự kiến

| Bước | Script / notebook | Đầu vào | Đầu ra |
| --- | --- | --- | --- |
| Thu thập | `crawlers/scrape_*.py` | URL tìm kiếm và bộ lọc từng nguồn | `data/raw/raw_*.csv` |
| Kiểm tra cấu trúc | `crawlers/schema_utils.py`: `load_raw`, `check_row` | Ba CSV nguồn, `schema.json` | Số dòng hợp lệ/không hợp lệ khi gộp |
| Gộp và khử trùng | `crawlers/schema_utils.py`: `merge_raw` | Ba CSV nguồn | `data/raw_data.csv` |
| Chuẩn hóa | `normalize_data.py` | `data/raw_data.csv` | `data/normalized_data.csv` |
| Làm sạch văn bản | `clean_data.py` | `data/normalized_data.csv` | `data/clean_data.csv` |
| Khai phá dữ liệu | `notebooks/NhomTamTau_MiningPipeline.ipynb` | `data/clean_data.csv` | Bảng, biểu đồ và mô hình trong báo cáo |

Các script nguồn và bước chuẩn hóa/làm sạch vẫn là **dự kiến**; `schema_utils.py` đã có nhưng chưa chạy trên CSV cào thật.

| Tệp dữ liệu dự kiến | Vai trò |
| --- | --- |
| `data/raw/raw_itviec.csv`, `raw_topcv.csv`, `raw_vietnamworks.csv` | Tin gốc theo từng nguồn, giữ `URL_Goc` và `Timestamp`. |
| `data/raw_data.csv` | Bản gộp ba nguồn sau kiểm tra schema và xử lý trùng. |
| `data/normalized_data.csv` | Bản sau chuẩn hóa lương, địa điểm, kinh nghiệm. |
| `data/clean_data.csv` | Bản sau xử lý mô tả và trích xuất kỹ năng để phân tích. |

## 6. Phương pháp phân tích dự kiến

| Bước | Phương pháp và quyết định cần kiểm chứng |
| --- | --- |
| Làm sạch | Khoa dùng quy tắc/Regex cho lương dạng khoảng, “up to”, USD và “thỏa thuận”; tách `Luong_Min`/`Luong_Max`, quy đổi đơn vị, chuẩn hóa địa điểm (Hà Nội, TP.HCM, Đà Nẵng, Remote) và số năm kinh nghiệm; giữ cột gốc để truy xuất. |
| Văn bản và kỹ năng | Hiếu bỏ HTML và stop words Việt/Anh, lập từ điển kỹ năng theo nhóm ngôn ngữ lập trình, framework, cloud, database và kỹ năng mềm; tạo mảng kỹ năng hoặc ma trận nhị phân, kiểm tra thủ công một mẫu tin. |
| EDA | Linh thống kê lương theo Fresher/Junior/Middle/Senior/Lead, Top 15 kỹ năng và so sánh nhu cầu/lương giữa Hà Nội, TP.HCM, Đà Nẵng; ghi mẫu số và tỷ lệ thiếu trong biểu đồ. |
| Gom cụm | Mã hóa kỹ năng/nội dung tin; thử K-Means hoặc Hierarchical Clustering; chọn số cụm bằng Elbow và Silhouette, rồi diễn giải đặc điểm từng cụm. |
| Luật kết hợp | Tạo tập kỹ năng cho mỗi tin, thử Apriori hoặc FP-Growth; công bố ngưỡng Support và Confidence đã chọn, lọc theo Lift > 1,2 và kiểm tra Conviction. |
| Phân lớp | Linh dự đoán `salary_band` theo mục 2; so sánh Decision Tree có cắt tỉa `ccp_alpha` với ít nhất một mô hình đối chứng (KNN, Random Forest hoặc Logistic Regression), kiểm tra overfitting và báo cáo Macro F1 cùng ma trận nhầm lẫn. |

Ngưỡng cuối cùng, số cụm, mô hình đối chứng, cách chia tập và seed sẽ được ghi sau khi nhóm kiểm tra dữ liệu thực tế. Không chọn ngưỡng dựa trên kết quả kiểm tra rồi trình bày như quyết định đặt trước.

**Quy đổi USD/VND:** nhóm sẽ dùng **một tỷ giá áp dụng cho snapshot dữ liệu** để có thể tái lập, lưu giá trị tỷ giá, nguồn công bố, URL và ngày truy cập trong cấu hình và README trước khi chạy bước chuẩn hóa. Chưa có tỷ giá thực tế được chọn, nên hiện không thể diễn giải các cột lương quy đổi hoặc huấn luyện `salary_band`. Tin thiếu kỳ trả lương xác định sẽ không được tự quy đổi sang lương tháng.

## 7. Cấu trúc thư mục

```text
README.md
requirements.txt
schema.json
.gitignore
crawlers/
  __init__.py
  base_crawler.py
  schema_utils.py
  http_client.py
  scrape_itviec.py
  scrape_topcv.py
  scrape_vietnamworks.py
tests/
  __init__.py
  test_base_crawler.py
normalize_data.py
clean_data.py
data/
  raw/
    raw_itviec.csv
    raw_topcv.csv
    raw_vietnamworks.csv
  raw_data.csv
  normalized_data.csv
  clean_data.csv
notebooks/NhomTamTau_MiningPipeline.ipynb
reports/NhomTamTau_BaoCao_BaiTapLon.pdf
reports/NhomTamTau_Slide_BaoCao.pdf
```

Đây là **cấu trúc đích**; các file `scrape_*.py` và bước xử lý sau cào vẫn chưa có. `crawlers/base_crawler.py` cung cấp `BaseCrawler`: mỗi crawler đặt `SOURCE` và triển khai `iter_jobs(max_pages=...)` để trả bản ghi theo `schema.json`. Base giữ giá trị gốc, gắn `Timestamp`, ghi CSV và tách file partial nếu lần cào dừng hoặc CSV chính đang mở; `schema_utils.py` đọc, kiểm tra và gộp CSV, còn `http_client.py` là tiện ích tùy chọn cho crawler dùng HTTP. `tests/test_base_crawler.py` kiểm tra khung bằng dữ liệu giả. `.gitignore` loại trừ file tạm và thư mục `data/`; CSV cần đưa vào gói nộp riêng sau khi kiểm tra quyền chia sẻ.

## 8. Tải, cài đặt và chạy lại

> **Dành cho giảng viên:** Các bước dưới đây là khung hướng dẫn. Nhóm phải thay URL và điền lệnh đã kiểm thử cho từng script trước khi nộp; ở trạng thái hiện tại chưa thể chạy toàn bộ pipeline từ README này.

### Tải mã nguồn

```bash
git clone <URL_REPOSITORY_CUA_NHOM>
cd <TEN_THU_MUC_REPOSITORY>
```

Nếu nộp bằng ZIP, giải nén và mở terminal trong thư mục chứa `README.md`.

### Tạo môi trường và cài thư viện

**Python đã kiểm thử:** [Bổ sung phiên bản].

```bash
python -m venv .venv
```

Kích hoạt môi trường: Windows PowerShell dùng `.\.venv\Scripts\Activate.ps1`; macOS/Linux dùng `source .venv/bin/activate`. Sau đó:

```bash
python -m pip install -r requirements.txt
```

**Trình duyệt/Playwright, thông tin đăng nhập và cấu hình:** [Chốt sau khi crawler được triển khai và kiểm thử]. `requirements.txt` vẫn cần được hoàn thiện và thử cài trên môi trường mới. Không đưa tài khoản hoặc khóa vào repository.

### Chạy pipeline

**Thứ tự dự kiến:** cào từng nguồn → kiểm tra và gộp bằng `merge_raw` trong `crawlers/schema_utils.py` → chuẩn hóa → làm sạch → chạy notebook. Khung và hàm gộp đã được kiểm thử bằng dữ liệu giả; lệnh cào từng nguồn và toàn bộ pipeline cần bổ sung sau khi có script nguồn. Có thể gọi `crawl(max_jobs=5)` để thử ít tin; nếu chỉ tái tạo phân tích, dùng snapshot `data/clean_data.csv` thay vì cào lại.

### Đối chiếu kết quả

**Số bản ghi theo từng bước, số tin lỗi/trùng và ví dụ kiểm tra `URL_Goc`:** [Bổ sung sau khi chạy]. Notebook cuối cùng cần chạy từ đầu đến cuối trên snapshot `clean_data.csv`.

## 9. Kết quả và sản phẩm nộp

**Kết quả nghiên cứu:** [Để trống đến khi có số liệu và biểu đồ đã kiểm tra].

| Nội dung cần đối chiếu | Vị trí trong notebook | Bảng/hình trong báo cáo |
| --- | --- | --- |
| EDA và biểu đồ | [Điền sau] | [Điền sau] |
| Gom cụm và đánh giá | [Điền sau] | [Điền sau] |
| Luật kết hợp kỹ năng | [Điền sau] | [Điền sau] |
| Phân lớp và đánh giá | [Điền sau] | [Điền sau] |

| Sản phẩm theo đề bài | Đường dẫn dự kiến |
| --- | --- |
| Mã nguồn crawler và hướng dẫn chạy | `crawlers/`, README này |
| Danh sách thư viện | `requirements.txt` |
| Dữ liệu thô và sạch | `data/raw_data.csv`, `data/clean_data.csv` |
| Notebook KDD | `notebooks/NhomTamTau_MiningPipeline.ipynb` |
| Báo cáo PDF | `reports/NhomTamTau_BaoCao_BaiTapLon.pdf` |
| Slide | `reports/NhomTamTau_Slide_BaoCao.pdf` |

Theo **đề bài gốc đã đối chiếu**, báo cáo dài **15–25 trang** (không tính phụ lục), gồm sáu chương: tổng quan; thu thập và tiền xử lý; EDA; gom cụm và luật kết hợp; phân lớp và đánh giá; kết luận và khuyến nghị. Phần thuyết trình kéo dài **10–12 phút**. Báo cáo cần có bảng phân công, tỷ lệ đóng góp được nhóm xác nhận, nguồn hình/bảng và phần giới hạn nghiên cứu. Slide dùng cùng số liệu với notebook và báo cáo.

## 10. Tiến độ và phương án dự phòng

| Hạn theo bảng phân công | Công việc | Phụ trách | Trạng thái trong bảng |
| --- | --- | --- | --- |
| 12/11 | Chọn nguồn, từ khóa và thống nhất cấu trúc dữ liệu | Cả nhóm | Đã làm |
| 12/11 | README hướng dẫn chạy và bảng tiến độ; `requirements.txt`; `schema.json`; `crawlers/base_crawler.py` | Lưu Đức Linh | Đang làm |
| 16/11 | Cào và kiểm tra mẫu ITviec, TopCV, VietnamWorks; lưu `URL_Goc` và `Timestamp` | Linh; Khoa; Hiếu theo bảng nguồn | Chưa làm |
| 17/11 | Kiểm tra và gộp CSV nguồn bằng `crawlers/schema_utils.py`; thống kê dòng hợp lệ/lỗi | Trần Đăng Khoa | Chưa chạy trên CSV thật |
| 17/11 | Gộp ba nguồn, khử trùng và tạo `raw_data.csv` | Cả nhóm; Khoa phụ trách công cụ và thống kê gộp | Chưa làm |
| 18/11 | Chuẩn hóa lương, địa điểm, kinh nghiệm | Trần Đăng Khoa | Chưa làm |
| 18/11 | Làm sạch văn bản và trích xuất kỹ năng; ghép thành `clean_data.csv` | Trần Minh Hiếu, phối hợp Khoa | Chưa làm |
| 19/11 | EDA và biểu đồ; phân lớp và đánh giá | Lưu Đức Linh | Chưa làm |
| 19/11 | Gom cụm và luật kết hợp | Trần Minh Hiếu | Chưa làm |
| 19/11 | Ghép notebook KDD, chạy từ đầu đến cuối và kiểm tra chéo | Cả nhóm | Chưa làm |
| 20/11 | Hoàn thiện báo cáo PDF | Trần Đăng Khoa, nhận kết quả từ cả nhóm | Chưa làm |
| 20/11 | Hoàn thiện slide PDF/PowerPoint và kịch bản 10–12 phút | Lưu Đức Linh; Trần Minh Hiếu | Chưa làm |
| 21/11 | Rà soát tệp, nộp đủ sản phẩm trên LMS | Cả nhóm | Chưa làm |

### Quy trình cộng tác

Theo bảng phân công, mỗi thành viên làm trên nhánh Git riêng và tạo Pull Request để nhóm review trước khi gộp vào nhánh chính. Sau mỗi phần việc, nhóm đồng bộ tiến độ và kiểm tra chéo. Mọi thành viên cần giải thích được mã nguồn, thuật toán và số liệu khi vấn đáp; tỷ lệ đóng góp thực tế sẽ được xác nhận trong báo cáo.

## 11. Hạn chế dự kiến

Dữ liệu chỉ đến từ ba nền tảng và một khoảng thu thập ngắn; thuật toán hiển thị, bộ lọc và chính sách của từng website có thể tạo thiên lệch mẫu. Một tin có thể xuất hiện ở nhiều nguồn; nhiều tin không công bố lương hoặc chỉ ghi “thỏa thuận”. Kết quả phân tích vì vậy cần ghi rõ mẫu số, tỷ lệ thiếu, quy tắc khử trùng và phạm vi suy luận. Hạn chế thực tế sẽ được cập nhật sau khi có dữ liệu.

## 12. Tài liệu tham khảo và giấy phép

- [Đề bài lớn của môn Khai phá dữ liệu — nguồn nội bộ của nhóm].
- [URL trang tìm kiếm, `robots.txt`, điều khoản sử dụng và ngày truy cập của từng nguồn — bổ sung trước khi thu thập].
- [Tài liệu phương pháp làm sạch, gom cụm, luật kết hợp và phân lớp — bổ sung khi triển khai].
- Khung trình bày dữ liệu và khả năng tái lập tham khảo [Social Science Data Editors](https://github.com/social-science-data-editors/template_README).

