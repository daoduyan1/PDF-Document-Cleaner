PDF DOCUMENT CLEANER 1.5.0 – HMDS
Tác giả: Đào Duy An – daoduyan.com
Đơn vị phát hành: HMDS – hmds.vn

MỤC TIÊU PHIÊN BẢN 1.5.0
Phiên bản này tập trung vào chuẩn hóa PDF, giảm dung lượng bộ cài và đơn giản hóa quy trình xử lý. OCR được tách khỏi Cleaner và sẽ được phát triển thành phần mềm độc lập trong giai đoạn sau.

TÍNH NĂNG
- Xử lý tối đa 500 PDF mỗi lượt; không sửa đổi file nguồn.
- Giữ nguyên tên file theo mặc định; có thể bật đổi tên theo số bắt đầu + năm + hậu tố tối đa 4 ký tự.
- Tự động loại bỏ trang trắng có độ tin cậy cao.
- Đưa trang mờ hoặc trang có mẫu đã lưu vào danh sách cần duyệt; không tự động xóa trang nghi ngờ.
- Có thể chủ động xóa trang trong cửa sổ Duyệt / xoay hồ sơ.
- Có thể chọn xóa trang và ghi nhớ mẫu ảnh chính xác để bật tự xóa mẫu đó trong các lô sau.
- Xoay thủ công toàn bộ hồ sơ trong lô theo góc 90°, 180° hoặc 270°; mặc định không xoay.
- Trong cửa sổ duyệt, có thể xoay riêng từng hồ sơ 90°, 180° hoặc 270°.
- Báo cáo CSV ghi số trang trước/sau, số trang trắng tự động xóa, số trang xóa thủ công, số trang cần duyệt, số trang xoay và tên file kết quả.
- Có phím tắt: Delete để yêu cầu xóa trang đang xem; Enter hoặc Space để đồng ý trong hộp thoại xác nhận; Esc để hủy.

NHỮNG CHỨC NĂNG ĐÃ LOẠI BỎ
- Không tích hợp OCR hoặc Tesseract trong Cleaner.
- Không tự động nhận diện hướng trang.
- Không nhận diện trang có dấu gạch chéo chữ X.
- Không yêu cầu OpenCV hoặc NumPy.

PHÍM TẮT TRONG CỬA SỔ DUYỆT
1. Chọn hồ sơ và trang cần xem.
2. Nhấn Delete để mở hộp thoại xác nhận xóa trang đang xem.
3. Nhấn Enter hoặc Space để đồng ý; nhấn Esc để hủy.
4. Nếu con trỏ đang nằm trong ô nhập số trang, phím Delete chỉ xóa ký tự trong ô nhập, không xóa trang PDF.
5. Không thể xóa trang cuối cùng của một PDF.

CÀI ĐẶT VÀ BIÊN DỊCH
1. Giải nén toàn bộ ZIP.
2. Upload các file và thư mục trong ZIP lên repository daoduyan1/PDF-Document-Cleaner, giữ nguyên thư mục .github.
3. Xóa file pdf_ocr.py cũ khỏi repository nếu còn; file này không còn thuộc dự án Cleaner.
4. Xóa thư mục tesseract cũ khỏi repository nếu trước đây đã upload vào dự án Cleaner.
5. Commit vào nhánh main.
6. Mở Actions và chờ workflow Build Windows installer chạy thành công.
7. Tải artifact PDF-Document-Cleaner-v1.5.0-Windows-Setup.
8. Cài PDF_Document_Cleaner_Setup.exe.

LƯU Ý AN TOÀN
- File nguồn luôn được giữ nguyên; kết quả được ghi vào thư mục đích riêng.
- Trang nghi ngờ không tự động bị xóa, trừ trường hợp mẫu ảnh chính xác đã được người dùng ghi nhớ và bật tùy chọn tự xóa.
- Không nên bật tự xóa mẫu đã ghi nhớ trên hồ sơ chính thức trước khi kiểm tra một lô thử nghiệm.
- Xoay thủ công theo lô sẽ áp dụng cùng góc xoay cho tất cả trang của từng PDF trong lô. Nếu lô có hồ sơ khác hướng nhau, chọn Không xoay rồi mở Duyệt / xoay hồ sơ để xoay riêng từng hồ sơ.
- OCR sẽ được phát triển thành chương trình độc lập; Cleaner 1.5.0 không cài, không chạy và không đóng gói OCR.

BẢN QUYỀN
Bản quyền tác giả: Đào Duy An – daoduyan.com
Đơn vị phát hành: HMDS – hmds.vn

LƯU Ý VỀ MẪU ĐÃ GHI NHỚ TỪ PHIÊN BẢN CŨ
- Phiên bản 1.5.0 sử dụng kho mẫu mới blank_patterns_v150.json.
- Các mẫu đã ghi nhớ ở phiên bản trước không tự động nhập sang phiên bản này. Việc tách kho mẫu nhằm tránh các mẫu trang gạch X đã lưu ở phiên bản cũ tiếp tục bị nhận diện và tự xóa ngoài ý muốn.
- Nếu có mẫu trang trắng cần dùng lại, hãy mở hồ sơ trong cửa sổ duyệt, chọn trang và sử dụng “Xóa + ghi nhớ mẫu” trong phiên bản 1.5.0.
- Khi cài đè lên bản 1.4.x, bộ cài 1.5.0 tự xóa thư mục OCR/Tesseract cũ trong thư mục cài đặt và các shortcut OCR cũ.
