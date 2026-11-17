# Thu thập và khai phá dữ liệu tuyển dụng CNTT tại Việt Nam

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-3776AB)](requirements.txt)
[![Playwright 1.65.1+](https://img.shields.io/badge/Playwright-1.65.1%2B-2EAD33)](requirements.txt)
[![pandas 3.1.1+](https://img.shields.io/badge/pandas-3.1.1%2B-150458)](requirements.txt)
[![scikit-learn 1.7.2+](https://img.shields.io/badge/scikit--learn-1.7.2%2B-F7931E)](requirements.txt)
[![mlxtend 0.23.4+](https://img.shields.io/badge/mlxtend-0.23.4%2B-6A5ACD)](requirements.txt)
![Project status: planning](https://img.shields.io/badge/status-planning-yellow)

**Nội dung:** [Mục tiêu](#2-mục-tiêu-và-câu-hỏi-nghiên-cứu) · [Nguồn dữ liệu](#4-nguồn-và-cách-thu-thập) · [Pipeline](#5-quy-trình-xử-lý-và-schema) · [Tải và chạy](#8-tải-cài-đặt-và-chạy-lại) · [Sản phẩm](#9-kết-quả-và-sản-phẩm-nộp) · [Tiến độ](#10-tiến-độ-và-phương-án-dự-phòng).

## 1. Giới thiệu

Đồ án môn **Khai phá dữ liệu (ITEC3417)** nghiên cứu tin tuyển dụng công nghệ thông tin và các ngành liên quan tại Việt Nam, với **trọng tâm Data Science, Data Analytics, AI và Machine Learning** theo bảng phân công. Nhóm tự xây dựng công cụ thu thập dữ liệu, tạo bộ dữ liệu thô và sạch, rồi thực hiện EDA, gom cụm, khai phá luật kết hợp và phân lớp theo yêu cầu đề bài.

| Thông tin | Nội dung |
| --- | --- |
| Nhóm | Tam Tấu |
| Thành viên | Lưu Đức Linh; Trần Đăng Khoa; Trần Minh Hiếu |
| Lớp | DH24DS01 |
| Thời gian thu thập dự kiến | Hạn hoàn thành các công cụ cào theo bảng phân công: 20/11/2026; thời gian cào thực tế sẽ bổ sung sau |
| Hạn hoàn thiện và nộp dự kiến | Hoàn thiện báo cáo và slide 25/11; nộp 26/11/2026 theo bảng phân công |
| Nguồn dự kiến | ITviec, TopCV, VietnamWorks, LinkedIn, TopDev |

Mục tiêu thu thập theo đề bài là khoảng **800–1.500+ tin tuyển dụng thô**. Số tin thực tế, tỷ lệ thiếu dữ liệu và kết quả phân tích sẽ chỉ được ghi sau khi chạy và kiểm tra.

## 2. Mục tiêu và câu hỏi nghiên cứu

Nhóm dự kiến trả lời bốn câu hỏi sau trong phạm vi mẫu thu thập:

1. Những kỹ năng, vị trí, cấp bậc và khu vực nào xuất hiện nhiều trong tin tuyển CNTT?
2. Mức lương được công bố thay đổi thế nào theo cấp bậc, địa điểm và nhóm kỹ năng?
3. Có thể chia các tin tuyển thành những nhóm công việc nào dựa trên kỹ năng và nội dung mô tả? Những kỹ năng nào thường được yêu cầu cùng nhau?
4. Với những tin có lương số hợp lệ, có thể dự đoán **khoảng lương** từ cấp bậc, kinh nghiệm, địa điểm và kỹ năng không?


Đây là **câu hỏi và thiết kế dự kiến**, chưa phải kết luận về thị trường lao động Việt Nam.

## 3. Phạm vi và định nghĩa dữ liệu

- **Tin thuộc phạm vi:** bộ lọc tiêu đề trong `keyword.json` nhận năm nhóm Data Analyst (DA), Data Scientist (DS), Data Engineer (DE), AI Engineer (AI) và Backend Developer (BE). Giữ Backend để đối chiếu với các vị trí dữ liệu khi phân tích. Cụm từ được so khớp sau khi bỏ dấu và không phân biệt hoa thường; từ viết tắt được so khớp nguyên từ, có phân biệt hoa thường trên tiêu đề gốc. Nhóm AI chỉ khớp các cụm chức danh AI Engineer, không khớp từ AI đứng riêng. Lọc theo tiêu đề có thể bỏ sót tin có tên chung chung.
- **Tìm kiếm theo kỹ năng:** crawler từng nguồn dự kiến đưa các kỹ năng như Python, SQL, Power BI hoặc Spark vào truy vấn tìm kiếm phù hợp với website; phần này chưa được triển khai. `keyword.json` chỉ lọc nhóm vị trí theo tiêu đề.
- **Khoảng thu thập:** bảng phân công đặt hạn hoàn thành các công cụ cào là 20/11/2026; khoảng thời gian thu thập thực tế sẽ ghi sau khi chạy. Thời điểm đăng tin trên website có thể khác thời điểm crawler thu thập.
- **Tin trùng:** `khoa_url()` tạo khóa đối chiếu từ host và đường dẫn, bỏ toàn bộ query và dấu `/` cuối; URL gốc vẫn được lưu. Nếu website dùng query chứa mã tin, crawler nguồn phải tự xử lý trước khi dùng khóa này. Tin có cùng tên công ty, tiêu đề và địa điểm sẽ được đánh dấu để kiểm tra; **không tự động xóa tin khác URL hoặc khác nguồn** khi chưa xác minh là cùng một vị trí.
- **Lương hợp lệ cho phân tích số:** có đơn vị tiền và kỳ trả lương xác định được. “Thỏa thuận”, khoảng không rõ đơn vị hoặc giá trị không chuyển đổi tin cậy được giữ trong cột gốc nhưng để thiếu ở cột lương số.
- **Tính đại diện:** mẫu là các tin tìm được theo nguồn, từ khóa và thời gian đã chọn; không mặc nhiên đại diện cho toàn bộ thị trường CNTT Việt Nam.

## 4. Nguồn và cách thu thập

| Nguồn | Người phụ trách | Script dự kiến | CSV nguồn dự kiến |
| --- | --- | --- | --- |
| ITviec | Lưu Đức Linh | `crawlers/scrape_itviec.py` | `data/raw/raw_itviec.csv` |
| TopCV | Trần Đăng Khoa | `crawlers/scrape_topcv.py` | `data/raw/raw_topcv.csv` |
| VietnamWorks | Trần Minh Hiếu | `crawlers/scrape_vietnamworks.py` | `data/raw/raw_vietnamworks.csv` |
| LinkedIn | Trần Minh Hiếu | `crawlers/scrape_Linkedin.py` | `data/raw/raw_Linkedin.csv` |
| TopDev | Trần Đăng Khoa | `crawlers/scrape_topdev.py` | `data/raw/raw_topdev.csv` |

**URL tìm kiếm, từ khóa thực dùng, bộ lọc, phân trang và số tin theo từng nguồn:** [Bổ sung trước và sau khi cào]. Các hàm trong `crawlers/base_crawler.py` hỗ trợ kiểm tra robots, thử lại, đối chiếu URL và đọc/ghi CSV theo schema; `crawlers/loc_keyword.py` lọc nhóm vị trí theo tiêu đề. Từng crawler nguồn tự chọn Playwright hoặc HTTP/API, cách phân trang và lấy nội dung chi tiết. Chưa có các script nguồn nên chưa xác nhận khả năng cào thực tế. Mỗi bản ghi giữ văn bản gốc, `URL_Goc`, `Timestamp` và tên nguồn để giảng viên đối chiếu ngẫu nhiên với tin đăng và chạy demo tại lớp.

Bảng phân công liệt kê năm nguồn cần phát triển, nhưng mục kiểm tra và gộp trong cùng tài liệu vẫn ghi ba nguồn; nhóm cần xác nhận những nguồn sẽ đưa vào bộ dữ liệu cuối.

### Thu thập có trách nhiệm

Trước khi chạy từng crawler, nhóm sẽ kiểm tra `robots.txt` và điều khoản của website đó, ghi lại quyết định sử dụng dữ liệu trong mục nguồn tham khảo. Crawler cần dùng tốc độ truy cập hợp lý, thời gian chờ giữa các yêu cầu và User-Agent có thể nhận diện; không vượt cơ chế đăng nhập hoặc kiểm soát truy cập. Nhóm không thu thập thông tin cá nhân của ứng viên và không đưa cookie, tài khoản hoặc khóa truy cập vào repository. Dữ liệu chỉ phục vụ đồ án học thuật; quyền chia sẻ từng tệp sẽ được xác nhận trước khi công bố.

`kiem_thu_robot()` trả `(rp, "")` khi các URL mục tiêu được phép; nếu không, hàm trả `(None, ly_do)` và crawler phải dừng, đồng thời có thể hiển thị lý do. Thông báo phân biệt robots không tồn tại (404), đường dẫn bị cấm, lỗi mạng và các mã HTTP khác. Nhóm chủ động dừng khi gặp 404 theo chính sách thận trọng; RFC 9309 cho phép crawler tiếp tục trong trường hợp này.

```python
rp, ly_do = kiem_thu_robot(trang_chu, cac_url_muc_tieu, ten_bot)
if rp is None:
    print(ly_do)  # Dừng thu thập; đọc thông báo để biết nguyên nhân.
else:
    # Chỉ tiếp tục thu thập khi các URL mục tiêu được phép.
    pass
```

## 5. Quy trình xử lý và schema

```text
Cả nhóm: chốt README, requirements.txt, schema.json và khung crawler
    ↓
Các nguồn tuyển dụng theo bảng phân công → CSV nguồn trong data/raw/
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
| Kiểm tra và ghi CSV nguồn | `crawlers/base_crawler.py`: `doc_csv`, `xuat_csv` | Dữ liệu nguồn, `schema.json` | CSV có header đúng thứ tự và các cột không cho phép null có giá trị |
| Gộp và khử trùng | Công cụ gộp dự kiến | Các CSV nguồn được chọn | `data/raw_data.csv` |
| Chuẩn hóa | `normalize_data.py` | `data/raw_data.csv` | `data/normalized_data.csv` |
| Làm sạch văn bản | `clean_data.py` | `data/normalized_data.csv` | `data/clean_data.csv` |
| Khai phá dữ liệu | `notebooks/NhomTamTau_MiningPipeline.ipynb` | `data/clean_data.csv` | Bảng, biểu đồ và mô hình trong báo cáo |

Các script nguồn, công cụ gộp và bước chuẩn hóa/làm sạch vẫn là **dự kiến**. Bộ công cụ chung đã được kiểm thử bằng dữ liệu giả, chưa chạy trên CSV cào thật.

| Tệp dữ liệu dự kiến | Vai trò |
| --- | --- |
| `data/raw/raw_*.csv` | Tin gốc theo từng nguồn, giữ `URL_Goc` và `Timestamp`. |
| `data/raw_data.csv` | Bản gộp các nguồn được chọn sau kiểm tra schema và xử lý trùng. |
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
keyword.json
.gitignore
crawlers/
  __init__.py
  base_crawler.py
  loc_keyword.py
tests/
  test_base_crawler.py
data/
  raw_data/
```

Đây là **cấu trúc hiện có**. `crawlers/__init__.py` xuất các hàm dùng chung; `crawlers/base_crawler.py` cung cấp các hàm xử lý robots, thời gian, URL, retry và CSV; `crawlers/loc_keyword.py` đọc `keyword.json` để lọc tiêu đề. Crawler nguồn tự tạo `Timestamp` trước khi tải chi tiết, quản lý danh sách tin và gọi `xuat_csv()` để lưu checkpoint. Bộ kiểm thử dùng các module trong `crawlers/`.

`tests/test_base_crawler.py` kiểm tra các hàm bằng dữ liệu giả. Các file `scrape_*.py`, công cụ gộp, bước xử lý sau cào, notebook và báo cáo vẫn là dự kiến. `.gitignore` loại trừ file tạm và thư mục `data/`; CSV cần đưa vào gói nộp riêng sau khi kiểm tra quyền chia sẻ.

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

**Thứ tự dự kiến:** cào từng nguồn → kiểm tra và gộp CSV → chuẩn hóa → làm sạch → chạy notebook. Lệnh cào từng nguồn, công cụ gộp và toàn bộ pipeline cần bổ sung sau khi được triển khai; nếu chỉ tái tạo phân tích, dùng snapshot `data/clean_data.csv` thay vì cào lại.

Chạy kiểm thử bộ công cụ chung từ thư mục gốc repository:

```bash
python -m unittest discover -s tests -v
```

Các kiểm thử dùng dữ liệu giả, mô phỏng robots và không gửi request thật.

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
| 12/11/2026 | Chọn nguồn, từ khóa và thống nhất cấu trúc dữ liệu | Cả nhóm | Đã làm |
| 12/11/2026 | README hướng dẫn chạy và bảng tiến độ; `schema.json` | Lưu Đức Linh | Đã làm |
| 12/11/2026 | `requirements.txt` | Trần Đăng Khoa | Đã làm |
| 17/11/2026 | Khung cào dùng chung | Lưu Đức Linh | Đang làm |
| 20/11/2026 | Cào ITviec | Lưu Đức Linh | Đang làm |
| 20/11/2026 | Cào TopCV và TopDev | Trần Đăng Khoa | Đang làm |
| 20/11/2026 | Cào VietnamWorks và LinkedIn | Trần Minh Hiếu | Đang làm |
| 21/11/2026 | Kiểm tra dữ liệu thô theo schema; thống kê dòng hợp lệ/lỗi | Trần Đăng Khoa | Chưa làm |
| 21/11/2026 | Gộp ba nguồn, đối soát và khử trùng để tạo `raw_data.csv` | Trần Đăng Khoa | Đã làm theo bảng; chưa đối chiếu sản phẩm |
| 22/11/2026 | Chuẩn hóa lương, địa điểm, kinh nghiệm | Trần Đăng Khoa | Chưa làm |
| 22/11/2026 | Làm sạch văn bản và trích xuất kỹ năng; ghép thành `clean_data.csv` | Trần Minh Hiếu, phối hợp Khoa | Chưa làm |
| 23/11/2026 | EDA và biểu đồ; phân lớp và đánh giá | Lưu Đức Linh | Chưa làm |
| 23/11/2026 | Gom cụm và luật kết hợp | Trần Minh Hiếu | Chưa làm |
| 24/11/2026 | Ghép notebook KDD và kiểm tra chéo | Cả nhóm | Chưa làm |
| 25/11/2026 | Hoàn thiện báo cáo PDF | Trần Đăng Khoa | Chưa làm |
| 25/11/2026 | Hoàn thiện slide PDF/PowerPoint | Lưu Đức Linh; Trần Minh Hiếu | Chưa làm |
| 26/11/2026 | Rà soát, nộp mã nguồn, dữ liệu, notebook, báo cáo và slide | Cả nhóm | Chưa làm |

Trạng thái được ghi theo bảng phân công trong PDF, chưa xác nhận tiến độ thực tế. Bảng đặt hạn báo cáo/slide là 25/11 và hạn nộp là 26/11, nhưng phần yêu cầu chi tiết ở cuối PDF vẫn ghi lần lượt 20/11 và 21/11; nhóm cần xác nhận hạn chính thức với giảng viên.

### Quy trình cộng tác

Theo bảng phân công, mỗi thành viên làm trên nhánh Git riêng và tạo Pull Request để nhóm review trước khi gộp vào nhánh chính. Sau mỗi phần việc, nhóm đồng bộ tiến độ và kiểm tra chéo. Mọi thành viên cần giải thích được mã nguồn, thuật toán và số liệu khi vấn đáp; tỷ lệ đóng góp thực tế sẽ được xác nhận trong báo cáo.

## 11. Hạn chế dự kiến

Dự án dự kiến thu thập từ năm nền tảng: ITviec, TopCV, VietnamWorks, LinkedIn và TopDev. Dù có nhiều nguồn, dữ liệu vẫn chỉ phản ánh các tin tìm được trong khoảng thời gian và phạm vi tìm kiếm của nhóm, không đại diện cho toàn bộ thị trường tuyển dụng CNTT Việt Nam.

Mỗi website có thuật toán hiển thị, bộ lọc, chính sách truy cập và cấu trúc dữ liệu khác nhau, nên số lượng và chất lượng tin thu được có thể chênh lệch. Một tin có thể xuất hiện trên nhiều website; nhiều tin không công bố lương hoặc chỉ ghi “thỏa thuận”. Kết quả phân tích cần ghi rõ số tin theo từng nguồn, tỷ lệ thiếu và quy tắc khử trùng. Những hạn chế thực tế sẽ được cập nhật sau khi thu thập và kiểm tra dữ liệu.

## 12. Tài liệu tham khảo và giấy phép

- [Đề bài lớn của môn Khai phá dữ liệu — nguồn nội bộ của nhóm].
- [URL trang tìm kiếm, `robots.txt`, điều khoản sử dụng và ngày truy cập của từng nguồn — bổ sung trước khi thu thập].
- [Tài liệu phương pháp làm sạch, gom cụm, luật kết hợp và phân lớp — bổ sung khi triển khai].
- Khung trình bày dữ liệu và khả năng tái lập tham khảo [Social Science Data Editors](https://github.com/social-science-data-editors/template_README).

