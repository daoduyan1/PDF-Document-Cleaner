import os, sys, csv, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import fitz
from PIL import Image
import pytesseract

LIMIT = 100

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
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                          colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)

def is_blank(page, dark_ratio=0.00010):
    # Ngưỡng bảo thủ; vẫn cần thử nghiệm trên mẫu scan thực tế.
    im = render_gray(page, 1.2)
    hist = im.histogram()
    dark_pixels = sum(hist[:205])
    return dark_pixels / max(1, im.width * im.height) <= dark_ratio

def suggested_rotation(page):
    if TESSDATA is None:
        return 0, "Thiếu dữ liệu OCR"
    try:
        im = render_gray(page, 2.0)
        cfg = f'--psm 0 --tessdata-dir "{TESSDATA}"'
        data = pytesseract.image_to_osd(
            im, output_type=pytesseract.Output.DICT, config=cfg, timeout=20
        )
        angle = int(data.get("rotate", 0)) % 360
        confidence = float(data.get("orientation_conf", 0))
        if angle in (90, 180, 270) and confidence >= 2.0:
            return angle, ""
        return 0, "Không đủ độ tin cậy; giữ nguyên"
    except Exception as exc:
        return 0, f"Không nhận diện được: {exc}"

def process_pdf(src: Path, input_root: Path, output_root: Path):
    rel = src.relative_to(input_root)
    dest = (output_root / rel).with_name(src.stem + "_cleaned.pdf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError("File kết quả đã tồn tại; không ghi đè.")
    doc = fitz.open(src)
    try:
        if doc.needs_pass:
            raise ValueError("PDF được bảo vệ bằng mật khẩu.")
        before = len(doc)
        blanks = [i for i, page in enumerate(doc) if is_blank(page)]
        # Không để thuật toán xóa toàn bộ tài liệu nếu nhận diện bất thường.
        if before and len(blanks) == before:
            blanks = []
        for index in reversed(blanks):
            doc.delete_page(index)

        rotated, uncertain = 0, 0
        for page in doc:
            angle, note = suggested_rotation(page)
            if angle:
                page.set_rotation((page.rotation + angle) % 360)
                rotated += 1
            elif note:
                uncertain += 1

        doc.save(dest, garbage=0, deflate=False, clean=False)
        return {
            "file": str(rel), "status": "Thành công",
            "pages_before": before, "blank_removed": len(blanks),
            "pages_after": len(doc), "rotated": rotated,
            "orientation_uncertain": uncertain,
            "output": str(dest.relative_to(output_root)), "note": ""
        }
    finally:
        doc.close()

class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Document Cleaner")
        self.root.geometry("780x490")
        self.root.minsize(700, 420)
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.events = queue.Queue()
        self.running = False
        self.build_ui()
        self.root.after(150, self.poll_events)

    def build_ui(self):
        pad = {"padx": 14, "pady": 7}
        ttk.Label(self.root, text="PDF DOCUMENT CLEANER",
                  font=("Segoe UI", 18, "bold")).pack(anchor="w", **pad)
        ttk.Label(self.root,
                  text="Xử lý hàng loạt tối đa 100 file PDF mỗi lượt; mỗi PDF tương ứng một hồ sơ."
                  ).pack(anchor="w", padx=14)

        for label, var, callback in (
            ("Thư mục PDF nguồn:", self.source, self.pick_source),
            ("Thư mục lưu kết quả:", self.target, self.pick_target),
        ):
            row = ttk.Frame(self.root)
            row.pack(fill="x", **pad)
            ttk.Label(row, text=label, width=23).pack(side="left")
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
            ttk.Button(row, text="Chọn...", command=callback).pack(side="right")

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=14, pady=12)
        self.status = ttk.Label(self.root, text="Sẵn sàng", anchor="w")
        self.status.pack(fill="x", padx=14)
        self.logbox = tk.Text(self.root, height=11, wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True, padx=14, pady=8)

        buttons = ttk.Frame(self.root)
        buttons.pack(fill="x", padx=14, pady=10)
        self.start_button = ttk.Button(
            buttons, text="BẮT ĐẦU XỬ LÝ (TỐI ĐA 100 PDF)", command=self.start
        )
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="Thoát", command=self.root.destroy).pack(side="right")

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
        source = Path(self.source.get()).resolve()
        target = Path(self.target.get()).resolve()
        if not source.is_dir():
            messagebox.showerror("Lỗi", "Thư mục nguồn không tồn tại.")
            return
        if target == source or source in target.parents:
            messagebox.showerror(
                "Lỗi", "Thư mục kết quả phải nằm ngoài thư mục nguồn."
            )
            return

        pdfs = sorted(
            (p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
            key=lambda p: str(p).lower()
        )
        if not pdfs:
            messagebox.showinfo("Thông báo", "Không tìm thấy file PDF.")
            return
        total = len(pdfs)
        if total > LIMIT:
            proceed = messagebox.askyesno(
                "Giới hạn 100 hồ sơ",
                f"Tìm thấy {total} file PDF. Xử lý 100 file đầu tiên theo thứ tự tên? "
                "Các file còn lại để lượt sau."
            )
            if not proceed:
                return
        pdfs = pdfs[:LIMIT]
        self.running = True
        self.start_button.configure(state="disabled")
        self.progress.configure(maximum=len(pdfs), value=0)
        self.log(f"Bắt đầu xử lý {len(pdfs)} file.")
        threading.Thread(
            target=self.worker, args=(pdfs, source, target, total), daemon=True
        ).start()

    def worker(self, pdfs, source, target, total):
        rows = []
        for number, pdf in enumerate(pdfs, 1):
            self.events.put(("progress", number, len(pdfs), pdf.name))
            try:
                result = process_pdf(pdf, source, target)
            except Exception as exc:
                result = {
                    "file": str(pdf.relative_to(source)), "status": "Lỗi",
                    "pages_before": 0, "blank_removed": 0, "pages_after": 0,
                    "rotated": 0, "orientation_uncertain": 0,
                    "output": "", "note": str(exc)
                }
            rows.append(result)
            self.events.put(("row", result))

        target.mkdir(parents=True, exist_ok=True)
        report = target / "PDF_Cleaner_Report.csv"
        with report.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        self.events.put(("done", rows, total, str(report)))

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, number, total, name = event
                    self.progress["value"] = number - 1
                    self.status.configure(text=f"Đang xử lý {number}/{total}: {name}")
                elif event[0] == "row":
                    row = event[1]
                    self.log(
                        f"{row['status']}: {row['file']} | "
                        f"xóa {row['blank_removed']} trang trắng | "
                        f"xoay {row['rotated']} trang"
                    )
                elif event[0] == "done":
                    _, rows, total, report = event
                    success = sum(row["status"] == "Thành công" for row in rows)
                    self.progress["value"] = len(rows)
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status.configure(
                        text=f"Hoàn tất: {success}/{len(rows)} thành công; "
                             f"{len(rows)-success} lỗi."
                    )
                    messagebox.showinfo(
                        "Đã hoàn tất",
                        f"Tổng số PDF tìm thấy: {total}\n"
                        f"Đã xử lý: {len(rows)}\n"
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
