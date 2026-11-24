import os
import sys
import csv
import threading
import queue
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import fitz
from PIL import Image, ImageChops, ImageFilter
import pytesseract

APP_VERSION = "1.2.0"
APP_AUTHOR = "Đào Duy An"
APP_AUTHOR_URL = "https://daoduyan.com"
APP_PUBLISHER = "HMDS"
APP_PUBLISHER_URL = "https://hmds.vn"
LIMIT = 500


def resource_path(*parts):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def configure_ocr():
    exe = resource_path("tesseract", "tesseract.exe")
    data = resource_path("tesseract", "tessdata")
    if exe.exists():
        pytesseract.pytesseract.tesseract_cmd = str(exe)
        os.environ["TESSDATA_PREFIX"] = str(data)
        return data
    return None


TESSDATA = configure_ocr()


def render_gray(page, scale=1.3):
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False
    )
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _channel_median(channel):
    """Tính trung vị kênh màu mà không cần thêm thư viện ngoài Pillow."""
    hist = channel.histogram()
    total = sum(hist)
    halfway = total // 2
    running = 0
    for value, count in enumerate(hist):
        running += count
        if running > halfway:
            return value
    return 255


def is_blank(page):
    """Nhận diện trang trắng theo nền giấy, không giả định giấy phải màu trắng."""
    pix = page.get_pixmap(
        matrix=fitz.Matrix(1.2, 1.2), colorspace=fitz.csRGB, alpha=False
    )
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # Bỏ viền giấy, bóng gáy và vệt mép scan.
    width, height = im.size
    im = im.crop((int(width * 0.03), int(height * 0.03),
                  int(width * 0.97), int(height * 0.97)))

    channels = im.split()
    background = tuple(_channel_median(channel) for channel in channels)
    background_image = Image.new("RGB", im.size, background)
    diff = ImageChops.difference(im, background_image)

    # Lấy sai khác lớn nhất giữa các kênh để nhận diện cả chữ/dấu có màu.
    max_diff = ImageChops.lighter(
        ImageChops.lighter(diff.getchannel("R"), diff.getchannel("G")),
        diff.getchannel("B")
    )
    mask = max_diff.point(lambda value: 255 if value >= 26 else 0)
    mask = mask.filter(ImageFilter.MedianFilter(3))

    foreground_pixels = sum(1 for value in mask.getdata() if value)
    total_pixels = mask.width * mask.height
    # Ngưỡng thấp để ưu tiên giữ trang có ít nội dung.
    return foreground_pixels < max(120, int(total_pixels * 0.00015))


def suggested_rotation(page):
    """Trả về góc cần hiệu chỉnh và độ tin cậy; None nghĩa là chưa đủ căn cứ."""
    if TESSDATA is None:
        return None, 0.0, "Thiếu dữ liệu OCR"
    try:
        im = render_gray(page, 2.0)
        cfg = f'--psm 0 --tessdata-dir "{TESSDATA}"'
        data = pytesseract.image_to_osd(
            im, output_type=pytesseract.Output.DICT, config=cfg, timeout=20
        )
        angle = int(data.get("rotate", 0)) % 360
        confidence = float(data.get("orientation_conf", 0))
        if angle in (0, 90, 180, 270) and confidence >= 2.0:
            return angle, confidence, ""
        return None, confidence, "Không đủ độ tin cậy; cần kiểm tra"
    except Exception as exc:
        return None, 0.0, f"Không nhận diện được: {exc}"


def process_pdf(src: Path, input_root: Path, output_root: Path, output_name: str):
    dest = output_root / output_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"File kết quả đã tồn tại: {dest.name}. Không ghi đè.")

    doc = fitz.open(src)
    try:
        if doc.needs_pass:
            raise ValueError("PDF được bảo vệ bằng mật khẩu.")

        before = len(doc)
        blanks = [i for i, page in enumerate(doc) if is_blank(page)]
        # Bảo vệ hồ sơ: không xóa toàn bộ tài liệu khi mọi trang đều bị nhận diện trắng.
        if before and len(blanks) == before:
            blanks = []

        for index in reversed(blanks):
            doc.delete_page(index)

        # Nhận diện riêng từng trang rồi tổng hợp hướng trong chính file PDF này.
        pages = list(doc)
        detections = [suggested_rotation(page) for page in pages]
        known_angles = [item[0] for item in detections if item[0] is not None]

        consensus_angle = None
        if known_angles:
            counts = {angle: known_angles.count(angle) for angle in set(known_angles)}
            dominant_angle = max(counts, key=counts.get)
            agreement = counts[dominant_angle] / len(known_angles)
            enough_evidence = len(known_angles) >= 2 or len(pages) == 1
            if enough_evidence and agreement >= 0.90:
                consensus_angle = dominant_angle

        rotated = inferred = uncertain = 0
        rotated_pages = []
        for page_number, (page, detection) in enumerate(zip(pages, detections), 1):
            angle, confidence, note = detection
            was_inferred = False

            if angle is None:
                if consensus_angle is not None:
                    angle = consensus_angle
                    was_inferred = True
                    inferred += 1
                else:
                    uncertain += 1
                    continue

            if angle:
                page.set_rotation((page.rotation + angle) % 360)
                rotated += 1
                suffix = " (suy luận theo hồ sơ)" if was_inferred else ""
                rotated_pages.append(f"{page_number}: {angle}°{suffix}")

        doc.save(dest, garbage=0, deflate=False, clean=False)
        return {
            "source_file": str(src.relative_to(input_root)),
            "status": "Thành công",
            "pages_before": before,
            "blank_removed": len(blanks),
            "pages_after": len(doc),
            "rotated": rotated,
            "orientation_inferred": inferred,
            "orientation_consensus": (
                f"{consensus_angle}°" if consensus_angle is not None else "Không xác lập"
            ),
            "orientation_uncertain": uncertain,
            "rotated_pages": "; ".join(rotated_pages),
            "output_file": output_name,
            "note": ""
        }
    finally:
        doc.close()


class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PDF Document Cleaner {APP_VERSION} - HMDS")
        self.root.geometry("900x610")
        self.root.minsize(780, 560)
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.start_number = tk.StringVar(value="1")
        self.year = tk.StringVar(value=str(datetime.now().year))
        self.events = queue.Queue()
        self.running = False
        self.build_ui()
        self.root.after(150, self.poll_events)

    def build_ui(self):
        pad = {"padx": 14, "pady": 6}
        ttk.Label(
            self.root, text="PDF DOCUMENT CLEANER",
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", **pad)
        ttk.Label(
            self.root,
            text=f"Phiên bản {APP_VERSION} | Xử lý hàng loạt tối đa {LIMIT} file PDF mỗi lượt."
        ).pack(anchor="w", padx=14)

        for label, var, callback in (
            ("Thư mục PDF nguồn:", self.source, self.pick_source),
            ("Thư mục lưu kết quả:", self.target, self.pick_target),
        ):
            row = ttk.Frame(self.root)
            row.pack(fill="x", **pad)
            ttk.Label(row, text=label, width=24).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
            ttk.Button(row, text="Chọn...", command=callback).pack(side="right")

        naming = ttk.LabelFrame(self.root, text="Quy tắc đặt tên file kết quả")
        naming.pack(fill="x", padx=14, pady=8)
        ttk.Label(naming, text="Số hồ sơ bắt đầu:").grid(row=0, column=0, padx=10, pady=9, sticky="w")
        ttk.Entry(naming, textvariable=self.start_number, width=14).grid(
            row=0, column=1, padx=8, pady=9, sticky="w"
        )
        ttk.Label(naming, text="Năm hồ sơ (4 chữ số):").grid(
            row=0, column=2, padx=(24, 8), pady=9, sticky="w"
        )
        ttk.Entry(naming, textvariable=self.year, width=14).grid(
            row=0, column=3, padx=8, pady=9, sticky="w"
        )
        ttk.Label(
            naming,
            text="Ví dụ: bắt đầu 125, năm 2026 → 125.2026.pdf, 126.2026.pdf, ..."
        ).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=LIMIT)
        self.progress.pack(fill="x", padx=14, pady=10)
        self.status = ttk.Label(self.root, text="Sẵn sàng", anchor="w")
        self.status.pack(fill="x", padx=14)
        self.logbox = tk.Text(self.root, height=12, wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True, padx=14, pady=8)

        buttons = ttk.Frame(self.root)
        buttons.pack(fill="x", padx=14, pady=8)
        self.start_button = ttk.Button(
            buttons, text=f"BẮT ĐẦU XỬ LÝ (TỐI ĐA {LIMIT} PDF)", command=self.start
        )
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="Thoát", command=self.root.destroy).pack(side="right")

        footer = ttk.Label(
            self.root,
            text="Bản quyền tác giả: Đào Duy An - daoduyan.com  |  Đơn vị phát hành: HMDS - hmds.vn",
            font=("Segoe UI", 8)
        )
        footer.pack(anchor="center", pady=(0, 8))

    def pick_source(self):
        value = filedialog.askdirectory(title="Chọn thư mục PDF nguồn")
        if value:
            self.source.set(value)

    def pick_target(self):
        value = filedialog.askdirectory(title="Chọn thư mục lưu kết quả")
        if value:
            self.target.set(value)

    def log(self, text):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", text + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def start(self):
        if self.running:
            return
        if not self.source.get() or not self.target.get():
            messagebox.showwarning("Thiếu thông tin", "Hãy chọn cả hai thư mục.")
            return

        try:
            start_number = int(self.start_number.get().strip())
            year_text = self.year.get().strip()
            year = int(year_text)
            if start_number < 1:
                raise ValueError("Số hồ sơ bắt đầu phải lớn hơn hoặc bằng 1.")
            if len(year_text) != 4 or year < 1000 or year > 9999:
                raise ValueError("Năm hồ sơ phải gồm đúng 4 chữ số.")
        except ValueError as exc:
            messagebox.showerror("Thông tin đặt tên không hợp lệ", str(exc))
            return

        source = Path(self.source.get()).resolve()
        target = Path(self.target.get()).resolve()
        if not source.is_dir():
            messagebox.showerror("Lỗi", "Thư mục nguồn không tồn tại.")
            return
        if target == source or target in source.parents or source in target.parents:
            messagebox.showerror(
                "Lỗi", "Thư mục kết quả phải tách biệt, không nằm trong hoặc bao chứa thư mục nguồn."
            )
            return

        pdfs = sorted(
            (p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
            key=lambda p: str(p.relative_to(source)).lower()
        )
        if not pdfs:
            messagebox.showinfo("Thông báo", "Không tìm thấy file PDF.")
            return

        found_total = len(pdfs)
        if found_total > LIMIT:
            proceed = messagebox.askyesno(
                f"Giới hạn {LIMIT} hồ sơ",
                f"Tìm thấy {found_total} file PDF. Xử lý {LIMIT} file đầu tiên theo thứ tự tên? "
                "Các file còn lại để lượt sau."
            )
            if not proceed:
                return
        pdfs = pdfs[:LIMIT]

        # Kiểm tra trước để tuyệt đối không ghi đè kết quả của lần chạy trước.
        target.mkdir(parents=True, exist_ok=True)
        conflicts = [
            target / f"{start_number + index}.{year}.pdf"
            for index in range(len(pdfs))
            if (target / f"{start_number + index}.{year}.pdf").exists()
        ]
        if conflicts:
            sample = ", ".join(path.name for path in conflicts[:5])
            messagebox.showerror(
                "Trùng tên file kết quả",
                f"Đã tồn tại {len(conflicts)} tên file trong thư mục kết quả, ví dụ: {sample}.\n"
                "Hãy chọn số hồ sơ bắt đầu khác hoặc thư mục kết quả khác. Không file nào bị ghi đè."
            )
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.progress.configure(maximum=len(pdfs), value=0)
        self.log(f"Bắt đầu xử lý {len(pdfs)} file; tên kết quả từ {start_number}.{year}.pdf.")
        threading.Thread(
            target=self.worker,
            args=(pdfs, source, target, found_total, start_number, year),
            daemon=True
        ).start()

    def worker(self, pdfs, source, target, found_total, start_number, year):
        rows = []
        for index, pdf in enumerate(pdfs):
            number = start_number + index
            output_name = f"{number}.{year}.pdf"
            self.events.put(("progress", index + 1, len(pdfs), pdf.name, output_name))
            try:
                result = process_pdf(pdf, source, target, output_name)
            except Exception as exc:
                result = {
                    "source_file": str(pdf.relative_to(source)),
                    "status": "Lỗi",
                    "pages_before": 0,
                    "blank_removed": 0,
                    "pages_after": 0,
                    "rotated": 0,
                    "orientation_inferred": 0,
                    "orientation_consensus": "Không xác lập",
                    "orientation_uncertain": 0,
                    "rotated_pages": "",
                    "output_file": output_name,
                    "note": str(exc)
                }
            rows.append(result)
            self.events.put(("row", result))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = target / f"PDF_Cleaner_Report_{timestamp}.csv"
        if rows:
            with report.open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
        self.events.put(("done", rows, found_total, str(report)))

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, number, total, source_name, output_name = event
                    self.progress["value"] = number - 1
                    self.status.configure(
                        text=f"Đang xử lý {number}/{total}: {source_name} → {output_name}"
                    )
                elif event[0] == "row":
                    row = event[1]
                    self.log(
                        f"{row['status']}: {row['source_file']} → {row['output_file']} | "
                        f"xóa {row['blank_removed']} trang trắng | "
                        f"xoay {row['rotated']} trang (suy luận {row['orientation_inferred']}) | "
                        f"chưa xác định hướng {row['orientation_uncertain']}"
                    )
                elif event[0] == "done":
                    _, rows, found_total, report = event
                    success = sum(row["status"] == "Thành công" for row in rows)
                    self.progress["value"] = len(rows)
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status.configure(
                        text=f"Hoàn tất: {success}/{len(rows)} thành công; {len(rows)-success} lỗi."
                    )
                    messagebox.showinfo(
                        "Đã hoàn tất",
                        f"Tổng số PDF tìm thấy: {found_total}\n"
                        f"Số PDF đưa vào xử lý: {len(rows)}\n"
                        f"Thành công: {success}\nLỗi: {len(rows)-success}\n\n"
                        f"Báo cáo: {report}\nFile gốc được giữ nguyên."
                    )
        except queue.Empty:
            pass
        self.root.after(150, self.poll_events)


if __name__ == "__main__":
    root = tk.Tk()
    CleanerApp(root)
    root.mainloop()
