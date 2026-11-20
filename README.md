# Thu thập và khai phá dữ liệu tuyển dụng CNTT tại Việt Nam

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-3776AB)](requirements.txt)
[![pandas 3.1.1+](https://img.shields.io/badge/pandas-3.1.1%2B-150458)](requirements.txt)
[![scikit-learn 1.7.2+](https://img.shields.io/badge/scikit--learn-1.7.2%2B-F7931E)](requirements.txt)
[![mlxtend 0.23.4+](https://img.shields.io/badge/mlxtend-0.23.4%2B-6A5ACD)](requirements.txt)

**Nội dung:** [Mục tiêu](#2-mục-tiêu-và-câu-hỏi-nghiên-cứu) · [Nguồn dữ liệu](#4-nguồn-và-cách-thu-thập) · [Pipeline](#5-quy-trình-xử-lý-và-schema) · [Tải và chạy](#8-tải-cài-đặt-và-chạy-lại) · [Sản phẩm](#9-kết-quả-và-sản-phẩm-nộp) · [Tiến độ](#10-tiến-độ-và-phương-án-dự-phòng).

## 1. Giới thiệu

Đồ án môn **Khai phá dữ liệu (ITEC3417)** nghiên cứu tin tuyển dụng công nghệ thông tin và các ngành liên quan tại Việt Nam, với **trọng tâm Data Science, Data Analytics, AI và Machine Learning** theo bảng phân công. Nhóm tự xây dựng công cụ thu thập dữ liệu, tạo bộ dữ liệu thô và sạch, rồi thực hiện EDA, gom cụm, khai phá luật kết hợp và phân lớp theo yêu cầu đề bài.

| Thông tin | Nội dung |
| --- | --- |
| Nhóm | Tam Tấu |
| Thành viên | Lưu Đức Linh, Trần Đăng Khoa, Trần Minh Hiếu |
| Lớp | DH24DS01 |
| Thời gian thu thập trong bộ CSV hiện có | 19–20/11/2026, theo cột `Timestamp` |
| Hạn hoàn thiện và nộp dự kiến | Hoàn thiện báo cáo và slide ngày 25/11/2026, nộp ngày 26/11/2026 theo bảng phân công |
| Nguồn dữ liệu | CareerViet, Saramin, TopDev, ITviec, TopCV và VietnamWorks |

Mục tiêu thu thập theo đề bài là khoảng **800–1.500+ tin tuyển dụng thô**. Sáu CSV trong repository hiện có **1.089 bản ghi** trước khi gộp và khử trùng giữa các nguồn.

## 2. Mục tiêu và câu hỏi nghiên cứu

Nhóm dự kiến trả lời bốn câu hỏi sau trong phạm vi mẫu thu thập:

1. Những kỹ năng, vị trí, cấp bậc và khu vực nào xuất hiện nhiều trong tin tuyển CNTT?
2. Mức lương được công bố thay đổi thế nào theo cấp bậc, địa điểm và nhóm kỹ năng?
3. Có thể chia các tin tuyển thành những nhóm công việc nào dựa trên kỹ năng và nội dung mô tả? Những kỹ năng nào thường được yêu cầu cùng nhau?
4. Với những tin có lương số hợp lệ, có thể dự đoán **khoảng lương** từ cấp bậc, kinh nghiệm, địa điểm và kỹ năng không?


Đây là **câu hỏi và thiết kế dự kiến**, chưa phải kết luận về thị trường lao động Việt Nam.

## 3. Phạm vi và định nghĩa dữ liệu

- **Tin thuộc phạm vi.** Mảng `Nhom_Nganh` trong `keyword.json` gồm Data Analyst, Data Scientist, Data Engineer, AI Engineer và Database Administrator. Crawler từng nguồn áp dụng các nhóm này theo cách tìm kiếm của website.
- **Kỹ năng chuyên ngành.** Mảng `Ki_Nang` là danh sách kỹ năng kỹ thuật dùng chung cho năm nhóm ngành. Một số crawler dùng danh sách này để mở rộng truy vấn.
- **Thời điểm thu thập.** `Timestamp` ghi thời điểm crawler thu thập tin. `Ngay_Dang` lưu ngày đăng do website cung cấp khi có dữ liệu.
- **Tin trùng:** `khoa_url()` tạo khóa đối chiếu từ host và đường dẫn, bỏ toàn bộ query và dấu `/` cuối; URL gốc vẫn được lưu. Nếu website dùng query chứa mã tin, crawler nguồn phải tự xử lý trước khi dùng khóa này. **Không tự động xóa tin khác URL hoặc khác nguồn** khi chưa xác minh là cùng một vị trí.
- **Lương hợp lệ cho phân tích số:** có đơn vị tiền và kỳ trả lương xác định được. “Thỏa thuận”, khoảng không rõ đơn vị hoặc giá trị không chuyển đổi tin cậy được giữ trong cột gốc nhưng để thiếu ở cột lương số.
- **Tính đại diện:** mẫu là các tin tìm được theo nguồn, từ khóa và thời gian đã chọn; không mặc nhiên đại diện cho toàn bộ thị trường CNTT Việt Nam.

## 4. Nguồn và cách thu thập

| Nguồn | Người phụ trách | Script thu thập | CSV mặc định trong repository | Số bản ghi |
| --- | --- | --- | --- | ---: |
| CareerViet | Trần Đăng Khoa | `crawlers/carrerviet.py` | `data/raw/raw_careerviet.csv` | 239 |
| Saramin | Trần Đăng Khoa | `crawlers/saramin.py` | `data/raw/raw_saramin.csv` | 35 |
| TopDev | Trần Đăng Khoa | `crawlers/topdev.py` | `data/raw/raw_topdev.csv` | 26 |
| ITviec | Lưu Đức Linh | `crawlers/itviec.py` | `data/raw/raw_itviec.csv` | 198 |
| TopCV | Lưu Đức Linh | `crawlers/topcv.py` | `data/raw/raw_topcv.csv` | 203 |
| VietnamWorks | Trần Minh Hiếu | `crawlers/vietnamworks.py` | `data/raw/raw_vietnamworks.csv` | 388 |

Số bản ghi được đếm từ các CSV trong bảng, bỏ dòng tiêu đề. Các cột `Web`, `URL_Goc` và `Timestamp` hỗ trợ đối chiếu bản ghi với tin gốc. `URL_Tim_Kiem` và `Tu_Khoa_Tim_Kiem` ghi truy vấn đã dùng khi crawler có thông tin tương ứng.

### Thu thập có trách nhiệm

Trước khi chạy từng crawler, nhóm sẽ kiểm tra `robots.txt` và điều khoản của website đó, ghi lại quyết định sử dụng dữ liệu trong mục nguồn tham khảo. Crawler cần dùng tốc độ truy cập hợp lý, thời gian chờ giữa các yêu cầu và User-Agent có thể nhận diện; không vượt cơ chế đăng nhập hoặc kiểm soát truy cập. Nhóm không thu thập thông tin cá nhân của ứng viên và không đưa cookie, tài khoản hoặc khóa truy cập vào repository. Dữ liệu chỉ phục vụ đồ án học thuật; quyền chia sẻ từng tệp sẽ được xác nhận trước khi công bố.

```python
rp, ly_do = kiem_thu_robot(trang_chu, cac_url_muc_tieu, ten_bot)
if rp is None:
    print(ly_do)  # Dừng thu thập; đọc thông báo để biết nguyên nhân.
else:
    # Chỉ tiếp tục thu thập khi các URL mục tiêu được phép.
    pass
```

## 5. Quy trình xử lý và schema

`schema.json` quy định tên và thứ tự 18 cột của CSV. Các trường bắt buộc gồm `Web`, `URL_Goc`, `Timestamp`, `Tieu_De`, `Ten_Cong_Ty`, `Dia_Diem` và `Mo_Ta_Cong_Viec`. Những mục tùy chọn như `Luong`, `Kinh_Nghiem`, `Yeu_Cau_Chi_Tiet` và `Quyen_Loi` có thể để trống khi nguồn thiếu dữ liệu.

Sáu CSV đã lưu trong `data/raw/` dùng UTF-8 BOM và mỗi tin chiếm một dòng vật lý. Xuống dòng trong nội dung được biểu diễn bằng `\n` và có thể khôi phục bằng `.replace(r"\n", "\n")` khi xử lý văn bản. Dùng trình đọc CSV để xử lý đúng dấu phẩy và dấu ngoặc kép trong nội dung tin.

```text
Sáu crawler theo bảng phân công → sáu CSV nguồn trong data/raw/
    ↓
Khoa kiểm tra schema, gộp và khử trùng, cả nhóm đối soát
    ↓
data/raw_data.csv (bản gộp giữ nội dung gốc)
    ↓
Khoa chuẩn hóa lương, địa điểm, kinh nghiệm → data/normalized_data.csv
    ↓
Hiếu làm sạch mô tả và trích xuất kỹ năng → data/clean_data.csv
    ↓
Linh thực hiện EDA và phân lớp, Hiếu thực hiện gom cụm và luật kết hợp
    ↓
Cả nhóm ghép notebook và kiểm tra chéo
    ↓
Khoa phụ trách báo cáo, Linh và Hiếu phụ trách slide
```

### Pipeline và tệp dữ liệu

| Bước | Mã nguồn hoặc công cụ | Đầu ra | Trạng thái trong repository |
| --- | --- | --- | --- |
| Thu thập theo nguồn | Sáu script ở mục 4 | Sáu CSV nguồn ở `data/raw/` | Đã có mã nguồn và dữ liệu |
| Đọc, kiểm tra và ghi CSV nguồn | `doc_csv()` và `xuat_csv()` trong `crawlers/base_crawler.py` | CSV đúng thứ tự cột theo schema | Đã có hàm dùng chung |
| Gộp và khử trùng sáu nguồn | Công cụ gộp | `data/raw_data.csv` | Dự kiến |
| Chuẩn hóa lương, địa điểm và kinh nghiệm | `normalize_data.py` | `data/normalized_data.csv` | Dự kiến |
| Làm sạch mô tả và trích xuất kỹ năng | `clean_data.py` | `data/clean_data.csv` | Dự kiến |
| Khai phá dữ liệu | `notebooks/NhomTamTau_MiningPipeline.ipynb` | Bảng, biểu đồ và mô hình trong báo cáo | Dự kiến |

## 6. Phương pháp phân tích dự kiến

| Bước | Phương pháp và quyết định cần kiểm chứng |
| --- | --- |
| Làm sạch | Khoa dùng quy tắc/Regex cho lương dạng khoảng, “up to”, USD và “thỏa thuận”; tách `Luong_Min`/`Luong_Max`, quy đổi đơn vị, chuẩn hóa địa điểm (Hà Nội, TP.HCM, Đà Nẵng, Remote) và số năm kinh nghiệm; giữ cột gốc để truy xuất. |
| Văn bản và kỹ năng | Hiếu bỏ HTML và stop words Việt/Anh, dùng từ điển kỹ năng chuyên ngành theo ngôn ngữ lập trình, framework, cloud và database; tạo mảng kỹ năng hoặc ma trận nhị phân, kiểm tra thủ công một mẫu tin. |
| EDA | Linh thống kê lương theo Fresher/Junior/Middle/Senior/Lead, Top 15 kỹ năng và so sánh nhu cầu/lương giữa Hà Nội, TP.HCM, Đà Nẵng; ghi mẫu số và tỷ lệ thiếu trong biểu đồ. |
| Gom cụm | Mã hóa kỹ năng/nội dung tin; thử K-Means hoặc Hierarchical Clustering; chọn số cụm bằng Elbow và Silhouette, rồi diễn giải đặc điểm từng cụm. |
| Luật kết hợp | Tạo tập kỹ năng cho mỗi tin, thử Apriori hoặc FP-Growth; công bố ngưỡng Support và Confidence đã chọn, lọc theo Lift > 1,2 và kiểm tra Conviction. |
| Phân lớp | Linh dự đoán `salary_band` theo mục 2; so sánh Decision Tree có cắt tỉa `ccp_alpha` với ít nhất một mô hình đối chứng (KNN, Random Forest hoặc Logistic Regression), kiểm tra overfitting và báo cáo Macro F1 cùng ma trận nhầm lẫn. |

Ngưỡng cuối cùng, số cụm, mô hình đối chứng, cách chia tập và seed sẽ được ghi sau khi nhóm kiểm tra dữ liệu thực tế. Không chọn ngưỡng dựa trên kết quả kiểm tra rồi trình bày như quyết định đặt trước.

**Quy đổi USD/VND:** nhóm sẽ dùng **một tỷ giá áp dụng cho snapshot dữ liệu** để có thể tái lập, lưu giá trị tỷ giá, nguồn công bố, URL và ngày truy cập trong cấu hình và README trước khi chạy bước chuẩn hóa. Chưa có tỷ giá thực tế được chọn, nên hiện không thể diễn giải các cột lương quy đổi hoặc huấn luyện `salary_band`. Tin thiếu kỳ trả lương xác định sẽ không được tự quy đổi sang lương tháng.

## 7. Cấu trúc thư mục

```text
.
├── .gitignore
├── README.md
├── requirements.txt
├── schema.json
├── keyword.json
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

`crawlers/base_crawler.py` cung cấp các hàm dùng chung để kiểm tra `robots.txt`, đối chiếu URL, ghi thời điểm thu thập, thử lại khi gặp lỗi tạm thời và đọc/ghi CSV theo schema. `crawlers/__init__.py` xuất các hàm này cho crawler nguồn. `crawlers/browser.py` hỗ trợ phân trang TopCV và bổ sung lương ITviec bằng trình duyệt.

Git đang theo dõi sáu CSV trong cây thư mục trên. Quy tắc `.gitignore` cho phép thêm CSV mới trong `data/raw/` bằng `git add` và bỏ qua các tệp phụ như JSON do VietnamWorks tạo khi chạy.

## 8. Tải, cài đặt và chạy lại

Có thể đọc trực tiếp sáu CSV trong `data/raw/` để kiểm tra dữ liệu đầu vào. Các lệnh dưới đây đọc và ghi theo đường dẫn CSV mặc định ở mục 4. Trạng thái của từng bước xử lý tiếp theo được ghi ở mục 5.

### Tải mã nguồn

```bash
git clone https://github.com/LinhLaSieuSao/Data_Mining_Engineer.git
cd Data_Mining_Engineer
```
### Tạo môi trường và cài thư viện

Dùng Python 3.13 trở lên theo `requirements.txt`. Tạo môi trường ảo từ thư mục gốc của repository.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### CareerViet, Saramin và TopDev

Các crawler này dùng Playwright. `--max-pages` giới hạn số trang cho mỗi truy vấn và `--target` đặt tổng số bản ghi mục tiêu, tính cả các tin đã lưu. Dùng `--out` để chọn CSV khác khi cần.

```bash
python crawlers/carrerviet.py --max-pages 1
python crawlers/saramin.py --max-pages 1
python crawlers/topdev.py --max-pages 1
```

#### ITviec

Crawler ITviec đọc và ghi trực tiếp vào `data/raw/raw_itviec.csv`. Tùy chọn `--limit` giới hạn tổng số tin xử lý, gồm tin mới và tin cần bổ sung lương.

```bash
python crawlers/itviec.py --nhom "Data Analyst" --chi-danh-muc --limit 20
```

Có thể bổ sung các mức lương còn thiếu qua phiên trình duyệt đăng nhập thủ công. Công cụ này đọc và ghi cùng tệp với crawler ITviec.

```bash
python crawlers/browser.py --limit 20
```

#### TopCV

Crawler TopCV dùng `data/raw/raw_topcv.csv` mặc định. Tùy chọn `--limit` giới hạn số tin mới và `--output` cho phép chọn CSV khác khi cần.

```bash
python crawlers/topcv.py --keyword "Data Analyst" --max-pages 2 --limit 5
```

### VietnamWorks

Crawler dùng Playwright, chọn nhóm ngành từ `keyword.json` và ghi trực tiếp vào `data/raw/raw_vietnamworks.csv`. Khi lưu kết quả, crawler cũng tạo `data/raw/raw_vietnamworks.json` trên máy chạy.

```bash
python crawlers/vietnamworks.py --tu-khoa "Data Analyst" --so-trang 1 --gioi-han 20
```

### Đối chiếu kết quả

Sau khi thu thập, kiểm tra tiêu đề 18 cột theo `schema.json`, đối chiếu mẫu tin qua `URL_Goc` và thống kê số tin mới, tin trùng, tin lỗi theo từng nguồn. Báo cáo và notebook sẽ dùng bộ dữ liệu sau khi gộp, chuẩn hóa và làm sạch.

## 9. Kết quả và sản phẩm nộp

**Kết quả nghiên cứu:** [Để trống đến khi có số liệu và biểu đồ đã kiểm tra].

| Nội dung cần đối chiếu | Vị trí trong notebook | Bảng/hình trong báo cáo |
| --- | --- | --- |
| EDA và biểu đồ | [Điền sau] | [Điền sau] |
| Gom cụm và đánh giá | [Điền sau] | [Điền sau] |
| Luật kết hợp kỹ năng | [Điền sau] | [Điền sau] |
| Phân lớp và đánh giá | [Điền sau] | [Điền sau] |

| Sản phẩm theo đề bài | Đường dẫn | Trạng thái |
| --- | --- | --- |
| Mã nguồn crawler và hướng dẫn chạy | `crawlers/`, README này | Đã có |
| Danh sách thư viện | `requirements.txt` | Đã có |
| Dữ liệu thô theo nguồn | Sáu tệp `data/raw/raw_*.csv` ở mục 4 | Đã có |
| Dữ liệu thô đã gộp và dữ liệu sạch | `data/raw_data.csv`, `data/clean_data.csv` | Dự kiến |
| Notebook KDD | `notebooks/NhomTamTau_MiningPipeline.ipynb` | Dự kiến |
| Báo cáo PDF | `reports/NhomTamTau_BaoCao_BaiTapLon.pdf` | Dự kiến |
| Slide | `reports/NhomTamTau_Slide_BaoCao.pdf` | Dự kiến |

## 10. Tiến độ và phương án dự phòng

| Hạn theo bảng phân công | Công việc | Phụ trách | Trạng thái |
| --- | --- | --- | --- |
| 12/11/2026 | Chọn nguồn, từ khóa và thống nhất cấu trúc dữ liệu | Cả nhóm | Đã có danh sách nguồn, `keyword.json` và `schema.json` |
| 12/11/2026 | README hướng dẫn chạy, bảng tiến độ và `schema.json` | Lưu Đức Linh | Đã có trong repository |
| 12/11/2026 | `requirements.txt` | Trần Đăng Khoa | Đã có trong repository |
| 17/11/2026 | Khung cào dùng chung | Lưu Đức Linh | Đã có `crawlers/base_crawler.py` |
| 20/11/2026 | Thu thập CareerViet, Saramin và TopDev | Trần Đăng Khoa | Đã có crawler và CSV theo nguồn |
| 20/11/2026 | Thu thập ITviec và TopCV | Lưu Đức Linh | Đã có crawler và CSV theo nguồn |
| 20/11/2026 | Thu thập VietnamWorks | Trần Minh Hiếu | Đã có crawler và CSV theo nguồn |
| 21/11/2026 | Kiểm tra dữ liệu thô theo schema và thống kê bản ghi hợp lệ | Trần Đăng Khoa | Dự kiến |
| 21/11/2026 | Gộp sáu nguồn, đối soát và khử trùng để tạo `data/raw_data.csv` | Trần Đăng Khoa | Dự kiến |
| 22/11/2026 | Chuẩn hóa lương, địa điểm, kinh nghiệm | Trần Đăng Khoa | Dự kiến |
| 22/11/2026 | Làm sạch văn bản và trích xuất kỹ năng để tạo `data/clean_data.csv` | Trần Minh Hiếu, phối hợp Khoa | Dự kiến |
| 23/11/2026 | EDA và biểu đồ, phân lớp và đánh giá | Lưu Đức Linh | Dự kiến |
| 23/11/2026 | Gom cụm và luật kết hợp | Trần Minh Hiếu | Dự kiến |
| 24/11/2026 | Ghép notebook KDD và kiểm tra chéo | Cả nhóm | Dự kiến |
| 25/11/2026 | Hoàn thiện báo cáo PDF | Trần Đăng Khoa | Dự kiến |
| 25/11/2026 | Hoàn thiện slide PDF/PowerPoint | Lưu Đức Linh và Trần Minh Hiếu | Dự kiến |
| 26/11/2026 | Rà soát, nộp mã nguồn, dữ liệu, notebook, báo cáo và slide | Cả nhóm | Dự kiến |


## 11. Hạn chế dự kiến

Dữ liệu đến từ sáu nguồn ở mục 4. Mẫu phản ánh các tin tìm được theo từ khóa, bộ lọc và khoảng thời gian thu thập của nhóm.

Mỗi website có thuật toán hiển thị, bộ lọc, chính sách truy cập và cấu trúc dữ liệu khác nhau, nên số lượng và chất lượng tin thu được có thể chênh lệch. Một tin có thể xuất hiện trên nhiều website; nhiều tin không công bố lương hoặc chỉ ghi “thỏa thuận”. Kết quả phân tích cần ghi rõ số tin theo từng nguồn, tỷ lệ thiếu và quy tắc khử trùng. Những hạn chế thực tế sẽ được cập nhật sau khi thu thập và kiểm tra dữ liệu.

## 12. Tài liệu tham khảo 

- BÀI TẬP LỚN: THU THẬP VÀ KHAI PHÁ DỮ LIỆU TUYỂN DỤNG THỰC TẾ TRONG NGÀNH CNTT & KHOA HỌC DỮ LIỆU TẠI VIỆT NAM.
- Khung cào dữ liệu từ nhiều nguồn tham khảo (https://github.com/SonPhatTranDeveloper/vietnam-it-job-trends).
- Khung trình bày dữ liệu và khả năng tái lập tham khảo [Social Science Data Editors](https://github.com/social-science-data-editors/template_README).

