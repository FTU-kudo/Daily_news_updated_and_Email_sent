# 📰 Daily news updated & Email sent 🚀

**Daily news updated & Email sent** là một dự án tự động hóa giúp người dùng cập nhật tin tức buổi sáng một cách nhanh chóng, tự động và thông minh. 

Hệ thống tự động tổng hợp tin tức từ nhiều nguồn uy tín, sử dụng trí tuệ nhân tạo (AI) để tóm tắt các điểm chính, đóng gói thành một file PDF chuyên nghiệp và tự động gửi trực tiếp đến email của khách hàng vào đúng **8:00 AM mỗi sáng**.

---

## 🛠️ Kiến trúc hệ thống (Pipeline)

Quy trình xử lý dữ liệu của dự án được thiết kế theo một pipeline khép kín và tự động hóa hoàn toàn:

1. **Thu thập tin tức (Data Crawling & Ingestion):**
   * 🇻🇳 **Tiếng Việt:** Thu thập dữ liệu từ *Google News*, *CafeF*, *CafeBiz*.
   * 🇬🇧 **Tiếng Anh:** Thu thập dữ liệu từ *Google News*, *MediaStack API*.
2. **Tóm tắt nội dung bằng AI (AI Summarization):**
   * Sử dụng **Gemini API** tiên tiến để phân tích, lọc bỏ thông tin nhiễu và tóm tắt các bài báo thành những nội dung ngắn gọn, súc tích và dễ nắm bắt nhất.
3. **Tạo tài liệu (PDF Generation):**
   * Chuyển đổi toàn bộ nội dung đã tóm tắt thành một file báo cáo PDF đẹp mắt, có bố cục rõ ràng, chuyên nghiệp.
4. **Phân phối tự động (Email Delivery):**
   * Kích hoạt hệ thống SMTP tự động gửi email đính kèm file PDF đến danh sách khách hàng vào đúng **8:00 AM**.

---

## ✨ Tính năng nổi bật

* ⏰ **Đúng giờ & Tự động:** Hoạt động hoàn toàn tự động vào lúc 8 giờ sáng mỗi ngày mà không cần sự can thiệp thủ công.
* 🌐 **Đa ngôn ngữ & Đa nguồn:** Tổng hợp cả tin tức trong nước và quốc tế từ các nguồn kinh tế, tài chính, xã hội uy tín.
* 🧠 **Tóm tắt thông minh bởi Gemini:** Sử dụng Gemini để tóm tắt nội dung, giúp người đọc nhanh chóng nắm bắt thông tin.
* 👆 **Truy cập link đọc báo tức thì:** Link được đính kèm ngay trong phần tiêu đề bài báo, giúp người đọc có thể truy cập ngay lập tức bằng cách nhấn vào tiêu đề.
* 📄 **Định dạng chuyên nghiệp:** File PDF được thiết kế tối giản, dễ đọc trên cả điện thoại và máy tính.
* 📩 **Gửi email hàng loạt:** Quản lý danh sách người nhận và gửi email đồng loạt với độ tin cậy cao.

## 📋 Yêu cầu hệ thống
* Python 3.8 trở lên
* Tài khoản và API Key của **Gemini**: 👉 [Google AI Studio](https://aistudio.google.com/api-keys)
* Tài khoản và API Key của **MediaStack**: 👉 [MediaStack](https://mediastack.com/)
* Cấu hình SMTP Email (ví dụ: App Password của Gmail)
