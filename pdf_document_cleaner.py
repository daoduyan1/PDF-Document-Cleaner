import os, csv, json, threading, queue, hashlib
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from PIL import Image, ImageChops, ImageFilter

APP_VERSION = "1.5.0"
APP_AUTHOR = "Đào Duy An"
APP_AUTHOR_URL = "https://daoduyan.com"
APP_PUBLISHER = "HMDS"
APP_PUBLISHER_URL = "https://hmds.vn"
LIMIT = 500


def app_data_dir():
    p = Path(os.environ.get("APPDATA", Path.home())) / "PDFDocumentCleaner"
    p.mkdir(parents=True, exist_ok=True)
    return p


PATTERN_FILE = app_data_dir() / "blank_patterns_v150.json"


def page_image(page, scale=1.25):
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def foreground_ratio(page):
    im = page_image(page, 1.25)
    w, h = im.size
    im = im.crop((int(w*.03), int(h*.03), int(w*.97), int(h*.97)))
    bg = tuple(ch.histogram().index(max(ch.histogram())) for ch in im.split())
    bgim = Image.new("RGB", im.size, bg)
    diff = ImageChops.difference(im, bgim)
    mx = ImageChops.lighter(ImageChops.lighter(diff.getchannel("R"), diff.getchannel("G")), diff.getchannel("B"))
    mask = mx.point(lambda v: 255 if v >= 22 else 0).filter(ImageFilter.MedianFilter(3))
    data = mask.getdata()
    return sum(1 for v in data if v) / max(1, len(data))


def load_patterns():
    try: return json.loads(PATTERN_FILE.read_text(encoding="utf-8"))
    except Exception: return []


def save_pattern(value):
    patterns = load_patterns()
    if value not in patterns:
        patterns.append(value)
        PATTERN_FILE.write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")


def exact_pattern(page):
    im = page_image(page, 1.5)
    return "exact:" + hashlib.sha256(str(im.size).encode() + im.tobytes()).hexdigest()


def process_pdf(src, input_root, output_root, output_name, rotate_degrees=0, learned_auto=False):
    """Normalize one PDF. Rotation is manual and uniform for this batch only."""
    dest = output_root / output_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"File kết quả đã tồn tại: {dest.name}")

    doc = fitz.open(src)
    try:
        if doc.needs_pass:
            raise ValueError("PDF được bảo vệ bằng mật khẩu.")

        before = len(doc)
        blank, reasons = [], {}
        patterns = load_patterns()

        for i, page in enumerate(doc):
            ratio = foreground_ratio(page)
            learned_exact = bool(patterns) and exact_pattern(page) in patterns
            if learned_auto and learned_exact:
                blank.append(i)
            elif ratio <= 0.00015 and not page.get_text().strip():
                blank.append(i)
            elif ((ratio <= 0.005 and not page.get_text().strip())
                  or learned_exact):
                reasons[i + 1] = "Trang mờ / mẫu đã lưu"

        # Never delete every page automatically; retain the whole PDF for review.
        if before and len(blank) == before:
            reasons = {i: "Toàn bộ hồ sơ nghi trắng" for i in range(1, before + 1)}
            blank = []

        for i in reversed(blank):
            doc.delete_page(i)

        # Re-index review pages after confirmed blank-page removal.
        suspicious = sorted(
            pno - sum(1 for b in blank if b < pno - 1)
            for pno in reasons
        )
        rotated = 0
        if rotate_degrees in (90, 180, 270):
            for page in doc:
                page.set_rotation((page.rotation + rotate_degrees) % 360)
                rotated += 1

        doc.save(dest, garbage=0, deflate=False, clean=False)
        rotation_label = f"Xoay thủ công {rotate_degrees}°" if rotate_degrees else "Không xoay"
        return {
            "source_file": str(src.relative_to(input_root)),
            "status": "Thành công",
            "pages_before": before,
            "blank_removed": len(blank),
            "manual_deleted": 0,
            "pages_after": len(doc),
            "rotated": rotated,
            "suspicious_pages": ";".join(map(str, suspicious)),
            "suspicious_count": len(suspicious),
            "output_file": str(output_name),
            "rotation_mode": rotation_label,
            "note": "; ".join(f"{k}: {v}" for k, v in reasons.items()),
        }
    finally:
        doc.close()


class ReviewWindow:
    def __init__(self, root, output_dir, report_path):
        self.root = root
        self.output_dir = Path(output_dir)
        self.report_path = Path(report_path)
        self.rows = []
        self.current = None
        self.photo = None
        self.shown = None

        with self.report_path.open(encoding="utf-8-sig", newline="") as f:
            self.rows = list(csv.DictReader(f))
        # Add fields introduced in 1.5.0 when opening an older report.
        for row in self.rows:
            row.setdefault("manual_deleted", "0")
            row.setdefault("suspicious_pages", "")
            row.setdefault("suspicious_count", "0")
            row.setdefault("note", "")

        self.win = tk.Toplevel(root)
        self.win.title("Duyệt, xóa và xoay hồ sơ")
        self.win.geometry("1050x740")
        self.win.minsize(900, 620)

        left = ttk.Frame(self.win)
        left.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Label(left, text="Hồ sơ kết quả").pack(anchor="w")
        self.files = tk.Listbox(left, width=42, height=30, exportselection=False)
        self.files.pack(fill="y", expand=True)
        self.items = [r for r in self.rows if r.get("status") == "Thành công" and r.get("output_file")]
        for row in self.items:
            self.files.insert("end", self.file_label(row))
        self.files.bind("<<ListboxSelect>>", self.select_file)

        right = ttk.Frame(self.win)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ttk.Label(right, text="Trang mờ / trang cần duyệt (số trang trong PDF kết quả)").pack(anchor="w")
        self.pages = tk.Listbox(right, height=5, exportselection=False)
        self.pages.pack(fill="x")
        self.pages.bind("<<ListboxSelect>>", self.preview)

        nav = ttk.Frame(right)
        nav.pack(fill="x", pady=(6, 0))
        self.page_no = tk.StringVar(value="1")
        ttk.Label(nav, text="Số trang:").pack(side="left")
        self.page_entry = ttk.Entry(nav, textvariable=self.page_no, width=7)
        self.page_entry.pack(side="left", padx=(4, 8))
        ttk.Button(nav, text="Xem trang", command=self.preview_number).pack(side="left")
        self.page_entry.bind("<Return>", lambda _event: self.preview_number())
        for angle in (90, 180, 270):
            ttk.Button(nav, text=f"Xoay cả hồ sơ {angle}°", command=lambda a=angle: self.rotate_file(a)).pack(side="left", padx=3)

        self.preview_label = ttk.Label(right, text="Chọn hồ sơ và trang để xem trước", anchor="center")
        self.preview_label.pack(fill="both", expand=True, pady=8)

        buttons = ttk.Frame(right)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Xóa trang (Delete)", command=lambda: self.delete_remember(False)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Xóa + ghi nhớ mẫu", command=lambda: self.delete_remember(True)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Giữ trang", command=self.keep).pack(side="left", padx=4)
        ttk.Button(buttons, text="Đóng", command=self.win.destroy).pack(side="right")
        ttk.Label(
            right,
            text="Phím tắt: Delete = xóa trang đang xem | Enter hoặc Space = đồng ý | Esc = hủy",
            foreground="#555",
        ).pack(anchor="w", pady=(8, 0))

        # Delete works from the review window, but not while editing the page-number field.
        self.win.bind("<Delete>", self.on_delete_key)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)

    @staticmethod
    def file_label(row):
        return f"{row['output_file']} ({row.get('suspicious_count', '0')} trang cần duyệt)"

    def refresh_file_labels(self):
        self.files.delete(0, "end")
        for row in self.items:
            self.files.insert("end", self.file_label(row))
        if self.current in self.items:
            idx = self.items.index(self.current)
            self.files.selection_set(idx)
            self.files.see(idx)

    def on_delete_key(self, event=None):
        focus = self.win.focus_get()
        if isinstance(focus, (tk.Entry, ttk.Entry, tk.Text)):
            return "break"
        if not self.current or not self.shown:
            self.win.bell()
            return "break"
        self.delete_remember(False)
        return "break"

    def confirm_delete(self, message):
        dialog = tk.Toplevel(self.win)
        dialog.title("Xác nhận xóa trang")
        dialog.transient(self.win)
        dialog.resizable(False, False)
        dialog.grab_set()
        result = {"confirmed": False}

        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=message, wraplength=430, justify="left").pack(anchor="w", pady=(0, 14))
        ttk.Label(body, text="Nhấn Enter hoặc Space để đồng ý; Esc để hủy.", foreground="#555").pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(body)
        actions.pack(fill="x")

        def accept(event=None):
            result["confirmed"] = True
            dialog.destroy()
            return "break"

        def cancel(event=None):
            dialog.destroy()
            return "break"

        ttk.Button(actions, text="Đồng ý", command=accept).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Hủy", command=cancel).pack(side="right")
        dialog.bind("<Return>", accept)
        dialog.bind("<KP_Enter>", accept)
        dialog.bind("<space>", accept)
        dialog.bind("<Escape>", cancel)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.update_idletasks()
        x = self.win.winfo_rootx() + (self.win.winfo_width() - dialog.winfo_width()) // 2
        y = self.win.winfo_rooty() + (self.win.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.focus_force()
        self.win.wait_window(dialog)
        self.win.focus_set()
        return result["confirmed"]

    def select_file(self, _=None):
        sel = self.files.curselection()
        if not sel:
            return
        self.current = self.items[sel[0]]
        self.refresh_pages()

    def refresh_pages(self):
        self.pages.delete(0, "end")
        vals = [x for x in self.current.get("suspicious_pages", "").split(";") if x]
        for value in vals:
            self.pages.insert("end", value)
        if vals:
            self.pages.selection_set(0)
            self.preview()
        else:
            self.page_no.set("1")
            self.preview_number()

    def preview(self, _=None):
        sel = self.pages.curselection()
        if not sel or not self.current:
            return
        self.page_no.set(self.pages.get(sel[0]))
        self.preview_number()

    def preview_number(self):
        if not self.current:
            return
        self.shown = None
        try:
            n = int(self.page_no.get())
            path = self.output_dir / self.current["output_file"]
            with fitz.open(path) as doc:
                if not 1 <= n <= len(doc):
                    raise ValueError("Số trang không hợp lệ")
                im = page_image(doc[n - 1], 1.5)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=self.win)
            return
        self.shown = (self.current, n)
        im.thumbnail((760, 560))
        self.photo = ImageTk.PhotoImage(im)
        self.preview_label.configure(image=self.photo, text="")

    def selected_page(self):
        if not self.current or getattr(self, "shown", None) != (self.current, int(self.page_no.get())):
            raise ValueError("Hãy xem trước trang cần thao tác.")
        return int(self.page_no.get())

    def delete_remember(self, remember=False):
        try:
            n = self.selected_page()
            path = self.output_dir / self.current["output_file"]
            extra = " Mẫu ảnh chính xác sẽ được ghi nhớ để anh có thể bật tự xóa ở các lần sau." if remember else ""
            if not self.confirm_delete(f"Xóa trang {n} khỏi hồ sơ {path.name}?{extra}"):
                return

            with fitz.open(path) as doc:
                if len(doc) <= 1:
                    raise ValueError("Không được xóa trang cuối cùng của hồ sơ.")
                pattern = exact_pattern(doc[n - 1]) if remember else None
                doc.delete_page(n - 1)
                tmp = path.with_name(path.stem + ".review.tmp.pdf")
                doc.save(tmp, garbage=0, deflate=False)
            os.replace(tmp, path)
            if pattern:
                save_pattern(pattern)

            vals = [int(x) for x in self.current.get("suspicious_pages", "").split(";") if x and int(x) != n]
            self.current["suspicious_pages"] = ";".join(str(x - (x > n)) for x in vals)
            self.current["suspicious_count"] = str(len(vals))
            self.current["pages_after"] = str(int(self.current["pages_after"]) - 1)
            self.current["manual_deleted"] = str(int(self.current.get("manual_deleted", "0")) + 1)
            note = f"Xóa thủ công trang {n}" + (" và ghi nhớ mẫu" if remember else "")
            self.current["note"] = (self.current.get("note", "") + " | " + note).strip(" |")
            self.write_report()
            self.refresh_file_labels()
            self.refresh_pages()
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=self.win)

    def rotate_file(self, angle):
        if not self.current:
            return
        path = self.output_dir / self.current["output_file"]
        if not messagebox.askyesno("Xác nhận", f"Xoay toàn bộ {path.name} {angle}° theo chiều kim đồng hồ?", parent=self.win):
            return
        try:
            with fitz.open(path) as doc:
                page_count = len(doc)
                for page in doc:
                    page.set_rotation((page.rotation + angle) % 360)
                tmp = path.with_name(path.stem + ".review.tmp.pdf")
                doc.save(tmp, garbage=0, deflate=False)
            os.replace(tmp, path)
            self.current["rotated"] = str(int(self.current.get("rotated", "0")) + page_count)
            self.current["note"] = (self.current.get("note", "") + f" | Xoay thủ công toàn hồ sơ {angle}°").strip(" |")
            self.write_report()
            self.preview_number()
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=self.win)

    def keep(self):
        try:
            n = self.selected_page()
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=self.win)
            return
        vals = [x for x in self.current.get("suspicious_pages", "").split(";") if x and int(x) != n]
        self.current["suspicious_pages"] = ";".join(vals)
        self.current["suspicious_count"] = str(len(vals))
        self.write_report()
        self.refresh_file_labels()
        self.refresh_pages()

    def write_report(self):
        if not self.rows:
            return
        successful = [r for r in self.rows if r.get("status") == "Thành công"]
        for row in self.rows:
            if row.get("status") == "TỔNG HỢP":
                for key in ("pages_before", "blank_removed", "manual_deleted", "pages_after", "rotated", "suspicious_count"):
                    if key in row or any(key in r for r in successful):
                        row[key] = sum(int(r.get(key, 0) or 0) for r in successful)
        fields = list(self.rows[0].keys())
        if "manual_deleted" not in fields:
            fields.append("manual_deleted")
        with self.report_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.rows)


# ImageTk import after tkinter is initialized
from PIL import ImageTk

class CleanerApp:
    def __init__(self,root):
        self.root=root; root.title(f"PDF Document Cleaner {APP_VERSION} - HMDS"); root.geometry("970x720"); root.minsize(850,650)
        self.source=tk.StringVar(); self.target=tk.StringVar(); self.start_number=tk.StringVar(value="1"); self.year=tk.StringVar(value=str(datetime.now().year)); self.suffix=tk.StringVar()
        self.rename=tk.BooleanVar(value=False); self.rotate=tk.StringVar(value="Không xoay"); self.learned_auto=tk.BooleanVar(value=False); self.events=queue.Queue(); self.running=False; self.last_report=None; self.last_target=None
        self.build_ui(); root.after(150,self.poll_events)

    def build_ui(self):
        pad={"padx":14,"pady":5}
        ttk.Label(self.root,text="PDF DOCUMENT CLEANER",font=("Segoe UI",18,"bold")).pack(anchor="w",**pad)
        ttk.Label(self.root,text=f"Phiên bản {APP_VERSION} | Tối đa {LIMIT} PDF mỗi lượt | Không tích hợp OCR, không tự nhận diện hướng.").pack(anchor="w",padx=14)
        for label,var,cb in (("Thư mục PDF nguồn:",self.source,self.pick_source),("Thư mục lưu kết quả:",self.target,self.pick_target)):
            row=ttk.Frame(self.root); row.pack(fill="x",**pad); ttk.Label(row,text=label,width=23).pack(side="left"); ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True,padx=6); ttk.Button(row,text="Chọn...",command=cb).pack(side="right")
        naming=ttk.LabelFrame(self.root,text="Quy tắc đặt tên file kết quả"); naming.pack(fill="x",padx=14,pady=7)
        ttk.Checkbutton(naming,text="Đổi tên theo mã hồ sơ (bỏ chọn để giữ nguyên tên)",variable=self.rename,command=self.toggle_naming).grid(row=2,column=0,columnspan=6,sticky="w",padx=8)
        self.naming=naming
        ttk.Label(naming,text="Số hồ sơ bắt đầu:").grid(row=0,column=0,padx=8,pady=8); ttk.Entry(naming,textvariable=self.start_number,width=12).grid(row=0,column=1,padx=5)
        ttk.Label(naming,text="Năm hồ sơ:").grid(row=0,column=2,padx=8); ttk.Entry(naming,textvariable=self.year,width=10).grid(row=0,column=3,padx=5)
        ttk.Label(naming,text="Hậu tố (0–4 ký tự):").grid(row=0,column=4,padx=8); ttk.Entry(naming,textvariable=self.suffix,width=8).grid(row=0,column=5,padx=5)
        ttk.Label(naming,text="Ví dụ: 125.2026A.pdf (để trống hậu tố nếu không cần).",foreground="#555").grid(row=1,column=0,columnspan=6,padx=8,pady=(0,7),sticky="w")
        opts=ttk.LabelFrame(self.root,text="Tùy chọn xử lý lô"); opts.pack(fill="x",padx=14,pady=5)
        ttk.Label(opts,text="Xoay thủ công toàn bộ trang của mỗi hồ sơ trong lô:").pack(anchor="w",padx=8,pady=(5,0))
        ttk.Combobox(opts,textvariable=self.rotate,state="readonly",values=["Không xoay","Xoay 90°","Xoay 180°","Xoay 270°"],width=24).pack(anchor="w",padx=8,pady=3)
        ttk.Checkbutton(opts,text="Tự xóa trang có mẫu ảnh đã ghi nhớ chính xác",variable=self.learned_auto).pack(anchor="w",padx=8,pady=(0,5))
        self.toggle_naming()
        self.progress=ttk.Progressbar(self.root,mode="determinate",maximum=LIMIT); self.progress.pack(fill="x",padx=14,pady=9)
        self.status=ttk.Label(self.root,text="Sẵn sàng",anchor="w"); self.status.pack(fill="x",padx=14)
        self.logbox=tk.Text(self.root,height=13,wrap="word",state="disabled"); self.logbox.pack(fill="both",expand=True,padx=14,pady=7)
        buttons=ttk.Frame(self.root); buttons.pack(fill="x",padx=14,pady=7)
        self.start_button=ttk.Button(buttons,text="BẮT ĐẦU XỬ LÝ (TỐI ĐA 500 PDF)",command=self.start); self.start_button.pack(side="left")
        self.review_button=ttk.Button(buttons,text="Duyệt / xoay hồ sơ",command=self.open_review); self.review_button.pack(side="left",padx=8)
        ttk.Button(buttons,text="Thoát",command=self.root.destroy).pack(side="right")
        ttk.Label(self.root,text="Bản quyền tác giả: Đào Duy An - daoduyan.com  |  Đơn vị phát hành: HMDS - hmds.vn",font=("Segoe UI",8)).pack(pady=(0,8))

    def toggle_naming(self):
        for w in self.naming.winfo_children():
            if isinstance(w,ttk.Entry):w.configure(state="normal" if self.rename.get() else "disabled")

    def pick_source(self):
        v=filedialog.askdirectory(title="Chọn thư mục PDF nguồn"); self.source.set(v) if v else None
    def pick_target(self):
        v=filedialog.askdirectory(title="Chọn thư mục lưu kết quả"); self.target.set(v) if v else None
    def log(self,s):
        self.logbox.configure(state="normal"); self.logbox.insert("end",s+"\n"); self.logbox.see("end"); self.logbox.configure(state="disabled")

    def start(self):
        if self.running:return
        try:
            start=int(self.start_number.get().strip()) if self.rename.get() else 1; year=self.year.get().strip() if self.rename.get() else "2000"; suffix=self.suffix.get().strip() if self.rename.get() else ""
            if start<1:raise ValueError("Số hồ sơ bắt đầu phải từ 1 trở lên.")
            if len(year)!=4 or not year.isdigit():raise ValueError("Năm phải gồm đúng 4 chữ số.")
            if len(suffix)>4 or any(c in '<>:/\\|?*"' for c in suffix):raise ValueError("Hậu tố tối đa 4 ký tự và không chứa ký tự đặc biệt của tên file.")
        except Exception as e:messagebox.showerror("Thông tin không hợp lệ",str(e));return
        src=Path(self.source.get()).resolve(); out=Path(self.target.get()).resolve()
        if not self.source.get() or not src.is_dir() or not self.target.get():messagebox.showwarning("Thiếu thư mục","Hãy chọn thư mục nguồn và kết quả hợp lệ.");return
        if out==src or out in src.parents or src in out.parents:messagebox.showerror("Lỗi","Thư mục kết quả phải tách biệt thư mục nguồn.");return
        pdfs=sorted((p for p in src.rglob("*") if p.is_file() and p.suffix.lower()==".pdf"),key=lambda p:str(p.relative_to(src)).lower())
        if not pdfs:messagebox.showinfo("Thông báo","Không tìm thấy PDF.");return
        total=len(pdfs)
        if total>LIMIT and not messagebox.askyesno("Giới hạn 500 PDF",f"Tìm thấy {total} PDF. Xử lý 500 file đầu tiên theo thứ tự tên?"):return
        pdfs=pdfs[:LIMIT]; out.mkdir(parents=True,exist_ok=True)
        names=[f"{start+i}.{year}{suffix}.pdf" if self.rename.get() else str(p.relative_to(src)) for i,p in enumerate(pdfs)]
        conflicts=[n for n in names if (out/n).exists()]
        if conflicts:messagebox.showerror("Trùng tên",f"Đã tồn tại {len(conflicts)} tên file, ví dụ: {', '.join(conflicts[:5])}. Không ghi đè file nào.");return
        self.running=True; self.review_button.configure(state="disabled"); self.start_button.configure(state="disabled"); self.progress.configure(maximum=len(pdfs),value=0)
        self.log(f"Bắt đầu {len(pdfs)} hồ sơ; xoay trang: {self.rotate.get()}; đổi tên: {self.rename.get()}.")
        rotation = {"Không xoay": 0, "Xoay 90°": 90, "Xoay 180°": 180, "Xoay 270°": 270}[self.rotate.get()]
        threading.Thread(target=self.worker,args=(pdfs,src,out,total,names,rotation,self.learned_auto.get()),daemon=True).start()

    def worker(self,pdfs,src,out,total,names,rotate_degrees,learned_auto):
        rows=[]
        for i,p in enumerate(pdfs):
            name=names[i]; self.events.put(("progress",i+1,len(pdfs),p.name))
            try:r=process_pdf(p,src,out,name,rotate_degrees,learned_auto)
            except Exception as e:r={"source_file":str(p.relative_to(src)),"status":"Lỗi","pages_before":0,"blank_removed":0,"manual_deleted":0,"pages_after":0,"rotated":0,"suspicious_pages":"","suspicious_count":0,"output_file":name,"rotation_mode":"Không xác định","note":str(e)}
            rows.append(r); self.events.put(("row",r))
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); report=out/f"PDF_Cleaner_Report_{stamp}.csv"
        if rows:
            with report.open("w",encoding="utf-8-sig",newline="") as f:
                fields=list(rows[0].keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
                successful=[r for r in rows if r["status"]=="Thành công"]
                summary={k:"" for k in fields}
                summary.update({"source_file":"TỔNG CỘNG","status":"TỔNG HỢP",
                    "pages_before":sum(int(r["pages_before"]) for r in successful),
                    "blank_removed":sum(int(r["blank_removed"]) for r in successful),
                    "manual_deleted":sum(int(r.get("manual_deleted", 0)) for r in successful),
                    "pages_after":sum(int(r["pages_after"]) for r in successful),
                    "rotated":sum(int(r["rotated"]) for r in successful),
                    "suspicious_count":sum(int(r["suspicious_count"]) for r in successful),
                    "note":f"Số PDF thành công: {len(successful)} / {len(rows)}"})
                w.writerow(summary)
        self.events.put(("done",rows,total,str(report),str(out)))

    def open_review(self):
        if self.running:return
        report=self.last_report or filedialog.askopenfilename(title="Chọn báo cáo CSV của lô đã xử lý",filetypes=[("CSV","*.csv")])
        if report and Path(report).exists():
            window=ReviewWindow(self.root,Path(report).parent,report); window.win.transient(self.root); window.win.grab_set()

    def poll_events(self):
        try:
            while True:
                e=self.events.get_nowait()
                if e[0]=="progress":self.progress["value"]=e[1]-1;self.status.configure(text=f"Đang xử lý {e[1]}/{e[2]}: {e[3]}")
                elif e[0]=="row":
                    r=e[1];self.log(f"{r['status']}: {r['source_file']} → {r['output_file']} | tự xóa {r['blank_removed']} trang trắng | xóa thủ công {r.get('manual_deleted', 0)} trang | còn {r['pages_after']} trang | cần duyệt {r['suspicious_count']} trang | xoay thủ công {r['rotated']} trang")
                elif e[0]=="done":
                    _,rows,total,report,out=e;ok=sum(r["status"]=="Thành công" for r in rows);pages=sum(int(r["pages_after"]) for r in rows if r["status"]=="Thành công");sus=sum(int(r["suspicious_count"]) for r in rows)
                    self.running=False;self.start_button.configure(state="normal");self.progress["value"]=len(rows);self.last_report=report;self.last_target=out;self.review_button.configure(state="normal")
                    self.status.configure(text=f"Hoàn tất: {ok}/{len(rows)} thành công; tổng {pages} trang; {sus} trang nghi ngờ.")
                    manual=sum(int(r.get("manual_deleted",0)) for r in rows if r.get("status")=="Thành công")
                    messagebox.showinfo("Hoàn tất",f"Tổng PDF tìm thấy: {total}\nĐã xử lý: {len(rows)}\nThành công: {ok}; lỗi: {len(rows)-ok}\nTổng số trang sau chuẩn hóa: {pages}\nTrang trắng tự động xóa: {sum(int(r['blank_removed']) for r in rows if r.get('status')=='Thành công')}\nTrang đã xóa thủ công: {manual}\nTrang mờ cần duyệt: {sus}\n\nBáo cáo CSV: {report}\nFile nguồn được giữ nguyên.")
        except queue.Empty:pass
        self.root.after(150,self.poll_events)

if __name__=="__main__":
    root=tk.Tk(); CleanerApp(root); root.mainloop()
