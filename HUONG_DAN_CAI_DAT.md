# HƯỚNG DẪN CÀI ĐẶT — Tự động gửi Báo cáo Tin tức mỗi sáng

Hệ thống này sẽ: **tự chạy mỗi sáng (7h VN) → lấy tin → tóm tắt AI → xuất PDF → lưu Google Drive → gửi email cho khách hàng**, hoàn toàn không cần bạn mở máy hay bấm nút gì cả. Lịch chạy được host miễn phí trên **GitHub Actions**.

Bạn cần làm 4 bước một lần duy nhất. Sau đó nó tự chạy mãi mãi.

---

## Bước 1 — Đưa code lên GitHub

1. Tạo một tài khoản GitHub (nếu chưa có): https://github.com/signup
2. Tạo một **repository mới**, đặt **Private** (để bảo mật code/khách hàng), ví dụ tên `ysvn-daily-news`.
3. Upload toàn bộ các file trong thư mục này (`main.py`, `requirements.txt`, và thư mục `.github/`) vào repo đó.
   - Cách dễ nhất: vào trang repo trên GitHub → "Add file" → "Upload files" → kéo thả tất cả file/folder vào → Commit.
   - **Lưu ý**: giữ đúng cấu trúc — file `daily_news.yml` phải nằm trong `.github/workflows/daily_news.yml`, không để lẫn ra ngoài.

---

## Bước 2 — Tạo "Mật khẩu ứng dụng" (App Password) cho Gmail

Gmail không cho phép đăng nhập bằng mật khẩu thường từ code, cần mật khẩu ứng dụng riêng:

1. Vào tài khoản Gmail bạn muốn dùng để **gửi** báo cáo đi.
2. Bật **Xác minh 2 bước (2-Step Verification)** nếu chưa bật: https://myaccount.google.com/security
3. Vào https://myaccount.google.com/apppasswords → tạo App Password mới (chọn tên bất kỳ, ví dụ "YSVN Daily News") → Google sẽ cho bạn 1 mã 16 ký tự (dạng `abcd efgh ijkl mnop`). **Lưu lại mã này**, đây chính là `GMAIL_APP_PASSWORD`.

---

## Bước 3 — Tạo Service Account để lưu PDF vào Google Drive

Vì hệ thống chạy tự động (không có ai đăng nhập), nó cần một "tài khoản máy" riêng để được phép ghi vào Drive của bạn:

1. Vào https://console.cloud.google.com/ → tạo project mới (hoặc dùng project đã có sẵn API Gemini của bạn).
2. Vào **APIs & Services → Library** → tìm "Google Drive API" → Enable.
3. Vào **APIs & Services → Credentials** → "Create Credentials" → "Service account" → đặt tên bất kỳ → Create.
4. Mở service account vừa tạo → tab **Keys** → "Add Key" → "Create new key" → chọn **JSON** → tải file JSON này về máy. Nội dung file này chính là `GDRIVE_SERVICE_ACCOUNT_JSON`.
5. Mở file JSON, tìm dòng `"client_email": "...@....iam.gserviceaccount.com"` — copy địa chỉ email này.
6. Vào Google Drive → mở thư mục `YSVN/Daily_News` (thư mục bạn đang lưu PDF) → **Chia sẻ (Share)** → dán email service account vào, cấp quyền **Editor**.
7. Mở thư mục đó trên trình duyệt, copy **Folder ID** từ đường link, ví dụ:
   `https://drive.google.com/drive/folders/1AbCDefGHijKLmnoPQRstuVWxyz` → Folder ID là `1AbCDefGHijKLmnoPQRstuVWxyz`.

---

## Bước 4 — Khai báo Secrets trên GitHub

Vào repo trên GitHub → **Settings → Secrets and variables → Actions → New repository secret**, tạo từng secret sau:

| Tên Secret | Giá trị |
|---|---|
| `GEMINI_API_KEY` | API key Gemini bạn đang dùng (trước đây là Colab Secret `MY_KEY`) |
| `MEDIA_STACK_API_KEY` | API key Mediastack (trước đây là Colab Secret `MEDIA_STACK_API`) |
| `GMAIL_ADDRESS` | Địa chỉ Gmail dùng để gửi đi, ví dụ `baocao.ysvn@gmail.com` |
| `GMAIL_APP_PASSWORD` | Mã 16 ký tự lấy ở Bước 2 (bỏ khoảng trắng) |
| `RECIPIENT_EMAILS` | Danh sách email khách hàng, cách nhau bằng dấu phẩy: `khach1@gmail.com,khach2@yahoo.com` |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Dán **toàn bộ nội dung** file JSON lấy ở Bước 3 |
| `GDRIVE_FOLDER_ID` | Folder ID lấy ở Bước 3 |

---

## Bước 5 — Chạy thử

1. Vào tab **Actions** của repo → chọn workflow "Bao cao tin tuc thi truong hang ngay" → nút **Run workflow** (góc phải) → Run.
2. Theo dõi log chạy trực tiếp. Nếu có lỗi, log sẽ chỉ rõ thiếu secret nào hoặc lỗi ở bước nào.
3. Nếu chạy thành công, bạn sẽ thấy email báo cáo trong vài phút và file PDF xuất hiện trong Google Drive.

Sau khi chạy thử ổn, **không cần làm gì thêm** — từ ngày mai, hệ thống tự chạy lúc 7h sáng (giờ VN) mỗi ngày.

---

## Một vài lưu ý

- **Giờ chạy**: hiện đặt 7h00 sáng VN để có 1 giờ đệm trước 8h. Nếu bạn thấy quy trình chạy nhanh/chậm hơn dự kiến, có thể chỉnh lại dòng `cron: "0 0 * * *"` trong file `.github/workflows/daily_news.yml` (giờ UTC = giờ VN − 7).
- **Riêng tư khách hàng**: email gửi đi đặt khách hàng vào trường **Bcc** nên các khách hàng sẽ không thấy email của nhau.
- **Chi phí**: GitHub Actions miễn phí cho repo private tới 2.000 phút/tháng — một lượt chạy như này chỉ tốn vài phút, nên dùng hàng ngày là dư dùng.
- **Nếu repo Public**: secrets vẫn an toàn (GitHub luôn ẩn giá trị secret trong log), nhưng nên để **Private** để bảo vệ code và domain nghiệp vụ.
- Nếu muốn đổi danh sách khách hàng, chỉ cần sửa secret `RECIPIENT_EMAILS`, không cần sửa code.
