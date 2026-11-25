PDF DOCUMENT CLEANER 1.3.2 – HMDS
Tác giả: Đào Duy An – daoduyan.com
Đơn vị phát hành: HMDS – hmds.vn

CẤU TRÚC CHỨC NĂNG
1. PDF Document Cleaner: chuẩn hóa PDF, chạy độc lập, không thực hiện OCR văn bản.
2. PDF OCR: module riêng, nhận PDF đã chuẩn hóa và xuất TXT UTF-8. Có thể nâng cấp sau này theo biểu mẫu/trường dữ liệu.

TÍNH NĂNG CLEANER
- Xử lý tối đa 500 PDF mỗi lượt; file nguồn không bị thay đổi.
- Đặt tên theo số bắt đầu + năm + hậu tố tùy chọn tối đa 4 ký tự.
- Bật/tắt nhận diện và tự xoay trang cho từng lô.
- Xóa trang trắng có độ tin cậy cao; trang nghi ngờ được giữ lại và đưa vào báo cáo CSV.
- Công cụ duyệt trang nghi ngờ cho phép xem trước, xóa thủ công hoặc đánh dấu giữ.
- Khi người dùng chọn “Xóa trang + ghi nhớ mẫu”, mẫu ảnh được lưu cục bộ để nhận diện các trang tương tự ở các lần sau. Ngưỡng khớp bảo thủ; cần kiểm tra kết quả trên tài liệu thực tế.
- Báo cáo CSV ghi số trang trước/sau, số trang xóa, số trang nghi ngờ, số trang xoay và tên file đầu ra.

TÍNH NĂNG OCR
- Chạy riêng sau khi Cleaner hoàn tất.
- OCR tiếng Việt + tiếng Anh (vie+eng), tiếng Việt (vie) hoặc tiếng Anh (eng).
- Mỗi PDF tạo một tệp TXT UTF-8 có đánh dấu số trang; giữ cấu trúc thư mục tương đối.
- Xử lý tối đa 500 PDF mỗi lượt; không sửa PDF nguồn.
- OCR là nhận dạng văn bản tổng quát, chưa phải bóc tách biểu mẫu hoặc xác định trường dữ liệu. Chức năng biểu mẫu sẽ được phát triển thành phiên bản riêng sau khi có mẫu tài liệu và yêu cầu trường dữ liệu.

CÀI ĐẶT VÀ BIÊN DỊCH
1. Giải nén toàn bộ ZIP.
2. Upload toàn bộ nội dung vào repository daoduyan1/PDF-Document-Cleaner, giữ nguyên thư mục .github.
3. Commit vào nhánh main.
4. Mở Actions, chọn Build Windows installer và chạy workflow (hoặc đợi workflow tự chạy sau push).
5. Chỉ tải artifact PDF-Document-Cleaner-v1.3.2-Windows-Setup khi workflow có dấu xanh.
6. Cài PDF_Document_Cleaner_Setup.exe. Bộ cài tạo hai shortcut: PDF Document Cleaner và PDF OCR.

LƯU Ý AN TOÀN
- Trang nghi ngờ không tự động bị xóa.
- Chức năng ghi nhớ mẫu chỉ áp dụng khi người dùng chủ động chọn xóa và ghi nhớ. Kiểm tra kỹ các kết quả đầu tiên trước khi sử dụng trên lô lớn.
- Nên thử nghiệm trên bản sao của hồ sơ trước khi xử lý dữ liệu nghiệp vụ chính thức.
- Tesseract OCR và dữ liệu ngôn ngữ được đóng gói offline; không cần API OCR tính phí. Cần giữ thông báo giấy phép của các thành phần bên thứ ba theo giấy phép tương ứng.
