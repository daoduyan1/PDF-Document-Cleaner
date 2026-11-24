PDF DOCUMENT CLEANER – GÓI ĐƯA LÊN GITHUB

1. Giải nén gói này.
2. Trong repository daoduyan1/PDF-Document-Cleaner, chọn Add file > Upload files.
3. Tải lên toàn bộ nội dung đã giải nén, bao gồm thư mục .github.
4. Nhấn Commit changes vào nhánh main.
5. Mở tab Actions, chọn workflow Build Windows installer và nhấn Run workflow.
6. Khi workflow thành công, mở lần chạy đó, tải artifact PDF-Document-Cleaner-Windows-Setup.
7. Giải nén artifact để lấy PDF_Document_Cleaner_Setup.exe.

Ứng dụng xử lý tối đa 100 PDF mỗi lượt, mỗi PDF là một hồ sơ. File nguồn không bị sửa.
Nếu có hơn 100 PDF, ứng dụng hỏi xác nhận và xử lý 100 file đầu tiên theo thứ tự tên.
Trang trắng được nhận diện theo ngưỡng điểm ảnh bảo thủ. Trang xoay được nhận diện bằng Tesseract OSD;
trang không đủ độ tin cậy sẽ được giữ nguyên. Cần kiểm thử trên bản scan thực tế trước khi dùng đại trà.
