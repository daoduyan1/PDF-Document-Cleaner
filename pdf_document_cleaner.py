import os, sys, csv, json, threading, queue, subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from PIL import Image, ImageChops, ImageFilter
import pytesseract

APP_VERSION = "1.3.0"
APP_AUTHOR = "Đào Duy An"
APP_AUTHOR_URL = "https://daoduyan.com"
APP_PUBLISHER = "HMDS"
APP_PUBLISHER_URL = "https://hmds.vn"
LIMIT = 500


def resource_path(*parts):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).joinpath(*parts)


def app_data_dir():
    p = Path(os.environ.get("APPDATA", Path.home())) / "PDFDocumentCleaner"
    p.mkdir(parents=True, exist_ok=True)
    return p


def configure_tesseract():
    exe = resource_path("tesseract", "tesseract.exe")
    data = resource_path("tesseract", "tessdata")
    if exe.exists():
        pytesseract.pytesseract.tesseract_cmd = str(exe)
        os.environ["TESSDATA_PREFIX"] = str(data)
        return data
    return None

TESSDATA = configure_tesseract()
PATTERN_FILE = app_data_dir() / "blank_patterns.json"


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


def dhash(page):
    im = page_image(page, 0.8).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            i = y*9+x
            bits = (bits << 1) | int(px[i] > px[i+1])
    return f"{bits:016x}"


def load_patterns():
    try: return json.loads(PATTERN_FILE.read_text(encoding="utf-8"))
    except Exception: return []


def save_pattern(value):
    patterns = load_patterns()
    if value not in patterns:
        patterns.append(value)
        PATTERN_FILE.write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_distance(a, b):
    try: return (int(a, 16) ^ int(b, 16)).bit_count()
    except Exception: return 64


def is_learned_blank(page):
    h = dhash(page)
    return any(hash_distance(h, x) <= 3 for x in load_patterns())


def suggested_rotation(page):
    if TESSDATA is None: return None, 0.0
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2,2), colorspace=fitz.csGRAY, alpha=False)
        im = Image.frombytes("L", (pix.width,pix.height), pix.samples)
        cfg = f'--psm 0 --tessdata-dir "{TESSDATA}"'
        d = pytesseract.image_to_osd(im, output_type=pytesseract.Output.DICT, config=cfg, timeout=20)
        angle, conf = int(d.get("rotate",0)) % 360, float(d.get("orientation_conf",0))
        return (angle, conf) if angle in (0,90,180,270) and conf >= 2 else (None, conf)
    except Exception: return None, 0.0


def process_pdf(src, input_root, output_root, output_name, rotate_enabled):
    dest = output_root / output_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists(): raise FileExistsError(f"File kết quả đã tồn tại: {dest.name}")
    doc = fitz.open(src)
    try:
        if doc.needs_pass: raise ValueError("PDF được bảo vệ bằng mật khẩu.")
        before = len(doc)
        blank, suspicious = [], []
        for i, page in enumerate(doc):
            ratio = foreground_ratio(page)
            if ratio <= 0.00015 or is_learned_blank(page): blank.append(i)
            elif ratio <= 0.005: suspicious.append(i+1)
        if before and len(blank) == before: blank = []
        for i in reversed(blank): doc.delete_page(i)
        # Re-index suspicious pages after definite blank deletion.
        suspicious = [p - sum(1 for b in blank if b < p-1) for p in suspicious]
        rotated = inferred = uncertain = 0
        consensus = None
        if rotate_enabled and len(doc):
            detections = [suggested_rotation(p) for p in doc]
            known = [a for a,c in detections if a is not None]
            if known:
                counts = {a:known.count(a) for a in set(known)}
                dominant = max(counts, key=counts.get)
                if (len(known)>=2 or len(doc)==1) and counts[dominant]/len(known)>=.90: consensus=dominant
            for page, (angle, conf) in zip(doc, detections):
                if angle is None:
                    if consensus is not None: angle=consensus; inferred += 1
                    else: uncertain += 1; continue
                if angle:
                    page.set_rotation((page.rotation+angle)%360); rotated += 1
        doc.save(dest, garbage=0, deflate=False, clean=False)
        return {"source_file":str(src.relative_to(input_root)),"status":"Thành công","pages_before":before,
          "blank_removed":len(blank),"pages_after":len(doc),"rotated":rotated,"orientation_inferred":inferred,
          "orientation_consensus":f"{consensus}°" if consensus is not None else "Không xác lập" if rotate_enabled else "Đã tắt",
          "orientation_uncertain":uncertain,"suspicious_pages":";".join(map(str,suspicious)),
          "suspicious_count":len(suspicious),"output_file":output_name,"note":""}
    finally: doc.close()


class ReviewWindow:
    def __init__(self, root, output_dir, report_path):
        self.root=root; self.output_dir=Path(output_dir); self.report_path=Path(report_path)
        self.rows=[]; self.current=None; self.photo=None
        with self.report_path.open(encoding="utf-8-sig", newline="") as f: self.rows=list(csv.DictReader(f))
        self.win=tk.Toplevel(root); self.win.title("Duyệt trang nghi ngờ là trang trắng"); self.win.geometry("1000x700")
        left=ttk.Frame(self.win); left.pack(side="left",fill="y",padx=8,pady=8)
        ttk.Label(left,text="Hồ sơ cần duyệt").pack(anchor="w")
        self.files=tk.Listbox(left,width=42,height=28); self.files.pack(fill="y",expand=True)
        self.items=[r for r in self.rows if r.get("suspicious_pages")]
        for r in self.items: self.files.insert("end",f"{r['output_file']} ({r['suspicious_count']} trang)")
        self.files.bind("<<ListboxSelect>>",self.select_file)
        right=ttk.Frame(self.win); right.pack(side="left",fill="both",expand=True,padx=8,pady=8)
        ttk.Label(right,text="Trang nghi ngờ (số trang trong PDF kết quả)").pack(anchor="w")
        self.pages=tk.Listbox(right,height=4); self.pages.pack(fill="x")
        self.pages.bind("<<ListboxSelect>>",self.preview)
        self.preview_label=ttk.Label(right,text="Chọn hồ sơ và trang để xem trước"); self.preview_label.pack(fill="both",expand=True,pady=8)
        buttons=ttk.Frame(right); buttons.pack(fill="x")
        ttk.Button(buttons,text="Xóa trang khỏi PDF + ghi nhớ mẫu",command=self.delete_remember).pack(side="left",padx=4)
        ttk.Button(buttons,text="Giữ trang (loại khỏi danh sách duyệt)",command=self.keep).pack(side="left",padx=4)
        ttk.Button(buttons,text="Đóng",command=self.win.destroy).pack(side="right")

    def select_file(self,_=None):
        sel=self.files.curselection()
        if not sel:return
        self.current=self.items[sel[0]]; self.refresh_pages()

    def refresh_pages(self):
        self.pages.delete(0,"end")
        vals=[x for x in self.current.get("suspicious_pages","").split(";") if x]
        for x in vals:self.pages.insert("end",x)
        if vals:self.pages.selection_set(0); self.preview()
        else:self.preview_label.configure(text="Không còn trang cần duyệt.",image="")

    def preview(self,_=None):
        sel=self.pages.curselection()
        if not sel or not self.current:return
        n=int(self.pages.get(sel[0])); path=self.output_dir/self.current["output_file"]
        with fitz.open(path) as d:
            pix=d[n-1].get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False)
            im=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
        im.thumbnail((650,520)); self.photo=ImageTk.PhotoImage(im)
        self.preview_label.configure(image=self.photo,text="")

    def delete_remember(self):
        sel=self.pages.curselection()
        if not sel or not self.current:return
        n=int(self.pages.get(sel[0])); path=self.output_dir/self.current["output_file"]
        if not messagebox.askyesno("Xác nhận",f"Xóa trang {n} khỏi {path.name} và ghi nhớ mẫu để nhận diện lần sau?",parent=self.win):return
        with fitz.open(path) as d:
            save_pattern(dhash(d[n-1]))
            d.delete_page(n-1); tmp=path.with_suffix(".review.tmp.pdf"); d.save(tmp,garbage=3,deflate=True)
        os.replace(tmp,path)
        vals=[x for x in self.current.get("suspicious_pages","").split(";") if x]
        vals.remove(str(n)); self.current["suspicious_pages"]=";".join(str(int(x)-(1 if int(x)>n else 0)) for x in vals)
        self.current["suspicious_count"]=str(len(vals)); self.current["pages_after"]=str(max(0,int(self.current.get("pages_after",0))-1))
        for row in self.rows:
            if row.get("status")=="TỔNG HỢP":
                row["pages_after"]=str(max(0,int(row.get("pages_after",0))-1))
                row["suspicious_count"]=str(max(0,int(row.get("suspicious_count",0))-1))
        self.write_report(); self.refresh_pages()

    def keep(self):
        sel=self.pages.curselection()
        if not sel or not self.current:return
        n=int(self.pages.get(sel[0])); vals=[x for x in self.current.get("suspicious_pages","").split(";") if x and int(x)!=n]
        self.current["suspicious_pages"]=";".join(vals); self.current["suspicious_count"]=str(len(vals)); self.write_report(); self.refresh_pages()

    def write_report(self):
        if not self.rows:return
        with self.report_path.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(self.rows[0].keys())); w.writeheader(); w.writerows(self.rows)


# ImageTk import after tkinter is initialized
from PIL import ImageTk

class CleanerApp:
    def __init__(self,root):
        self.root=root; root.title(f"PDF Document Cleaner {APP_VERSION} - HMDS"); root.geometry("970x720"); root.minsize(850,650)
        self.source=tk.StringVar(); self.target=tk.StringVar(); self.start_number=tk.StringVar(value="1"); self.year=tk.StringVar(value=str(datetime.now().year)); self.suffix=tk.StringVar()
        self.rotate=tk.BooleanVar(value=False); self.events=queue.Queue(); self.running=False; self.last_report=None; self.last_target=None
        self.build_ui(); root.after(150,self.poll_events)

    def build_ui(self):
        pad={"padx":14,"pady":5}
        ttk.Label(self.root,text="PDF DOCUMENT CLEANER",font=("Segoe UI",18,"bold")).pack(anchor="w",**pad)
        ttk.Label(self.root,text=f"Phiên bản {APP_VERSION} | Tối đa {LIMIT} PDF mỗi lượt | OCR là phân hệ riêng.").pack(anchor="w",padx=14)
        for label,var,cb in (("Thư mục PDF nguồn:",self.source,self.pick_source),("Thư mục lưu kết quả:",self.target,self.pick_target)):
            row=ttk.Frame(self.root); row.pack(fill="x",**pad); ttk.Label(row,text=label,width=23).pack(side="left"); ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True,padx=6); ttk.Button(row,text="Chọn...",command=cb).pack(side="right")
        naming=ttk.LabelFrame(self.root,text="Quy tắc đặt tên file kết quả"); naming.pack(fill="x",padx=14,pady=7)
        ttk.Label(naming,text="Số hồ sơ bắt đầu:").grid(row=0,column=0,padx=8,pady=8); ttk.Entry(naming,textvariable=self.start_number,width=12).grid(row=0,column=1,padx=5)
        ttk.Label(naming,text="Năm hồ sơ:").grid(row=0,column=2,padx=8); ttk.Entry(naming,textvariable=self.year,width=10).grid(row=0,column=3,padx=5)
        ttk.Label(naming,text="Hậu tố (0–4 ký tự):").grid(row=0,column=4,padx=8); ttk.Entry(naming,textvariable=self.suffix,width=8).grid(row=0,column=5,padx=5)
        ttk.Label(naming,text="Ví dụ: 125.2026A.pdf (để trống hậu tố nếu không cần).",foreground="#555").grid(row=1,column=0,columnspan=6,padx=8,pady=(0,7),sticky="w")
        opts=ttk.LabelFrame(self.root,text="Tùy chọn xử lý lô"); opts.pack(fill="x",padx=14,pady=5)
        ttk.Checkbutton(opts,text="Nhận diện và tự xoay trang (tốn thêm thời gian; chỉ bật khi lô có trang sai chiều)",variable=self.rotate).pack(anchor="w",padx=8,pady=7)
        self.progress=ttk.Progressbar(self.root,mode="determinate",maximum=LIMIT); self.progress.pack(fill="x",padx=14,pady=9)
        self.status=ttk.Label(self.root,text="Sẵn sàng",anchor="w"); self.status.pack(fill="x",padx=14)
        self.logbox=tk.Text(self.root,height=13,wrap="word",state="disabled"); self.logbox.pack(fill="both",expand=True,padx=14,pady=7)
        buttons=ttk.Frame(self.root); buttons.pack(fill="x",padx=14,pady=7)
        self.start_button=ttk.Button(buttons,text="BẮT ĐẦU XỬ LÝ (TỐI ĐA 500 PDF)",command=self.start); self.start_button.pack(side="left")
        self.review_button=ttk.Button(buttons,text="Duyệt trang nghi ngờ",command=self.open_review,state="disabled"); self.review_button.pack(side="left",padx=8)
        ttk.Button(buttons,text="Thoát",command=self.root.destroy).pack(side="right")
        ttk.Label(self.root,text="Bản quyền tác giả: Đào Duy An - daoduyan.com  |  Đơn vị phát hành: HMDS - hmds.vn",font=("Segoe UI",8)).pack(pady=(0,8))

    def pick_source(self):
        v=filedialog.askdirectory(title="Chọn thư mục PDF nguồn"); self.source.set(v) if v else None
    def pick_target(self):
        v=filedialog.askdirectory(title="Chọn thư mục lưu kết quả"); self.target.set(v) if v else None
    def log(self,s):
        self.logbox.configure(state="normal"); self.logbox.insert("end",s+"\n"); self.logbox.see("end"); self.logbox.configure(state="disabled")

    def start(self):
        if self.running:return
        try:
            start=int(self.start_number.get().strip()); year=self.year.get().strip(); suffix=self.suffix.get().strip()
            if start<1:raise ValueError("Số hồ sơ bắt đầu phải từ 1 trở lên.")
            if len(year)!=4 or not year.isdigit():raise ValueError("Năm phải gồm đúng 4 chữ số.")
            if len(suffix)>4 or any(c in '<>:/\\|?*"' for c in suffix):raise ValueError("Hậu tố tối đa 4 ký tự và không chứa ký tự đặc biệt của tên file.")
        except Exception as e:messagebox.showerror("Thông tin không hợp lệ",str(e));return
        src=Path(self.source.get()).resolve(); out=Path(self.target.get()).resolve()
        if not src.is_dir() or not self.target.get():messagebox.showwarning("Thiếu thư mục","Hãy chọn thư mục nguồn và kết quả hợp lệ.");return
        if out==src or out in src.parents or src in out.parents:messagebox.showerror("Lỗi","Thư mục kết quả phải tách biệt thư mục nguồn.");return
        pdfs=sorted((p for p in src.rglob("*") if p.is_file() and p.suffix.lower()==".pdf"),key=lambda p:str(p.relative_to(src)).lower())
        if not pdfs:messagebox.showinfo("Thông báo","Không tìm thấy PDF.");return
        total=len(pdfs)
        if total>LIMIT and not messagebox.askyesno("Giới hạn 500 PDF",f"Tìm thấy {total} PDF. Xử lý 500 file đầu tiên theo thứ tự tên?"):return
        pdfs=pdfs[:LIMIT]; out.mkdir(parents=True,exist_ok=True)
        names=[f"{start+i}.{year}{suffix}.pdf" for i in range(len(pdfs))]
        conflicts=[n for n in names if (out/n).exists()]
        if conflicts:messagebox.showerror("Trùng tên",f"Đã tồn tại {len(conflicts)} tên file, ví dụ: {', '.join(conflicts[:5])}. Không ghi đè file nào.");return
        self.running=True; self.start_button.configure(state="disabled"); self.progress.configure(maximum=len(pdfs),value=0)
        self.log(f"Bắt đầu {len(pdfs)} hồ sơ; xoay trang: {'BẬT' if self.rotate.get() else 'TẮT'}; hậu tố: {suffix or '(không)'}.")
        threading.Thread(target=self.worker,args=(pdfs,src,out,total,start,year,suffix,self.rotate.get()),daemon=True).start()

    def worker(self,pdfs,src,out,total,start,year,suffix,rotate):
        rows=[]
        for i,p in enumerate(pdfs):
            name=f"{start+i}.{year}{suffix}.pdf"; self.events.put(("progress",i+1,len(pdfs),p.name))
            try:r=process_pdf(p,src,out,name,rotate)
            except Exception as e:r={"source_file":str(p.relative_to(src)),"status":"Lỗi","pages_before":0,"blank_removed":0,"pages_after":0,"rotated":0,"orientation_inferred":0,"orientation_consensus":"","orientation_uncertain":0,"suspicious_pages":"","suspicious_count":0,"output_file":name,"note":str(e)}
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
                    "pages_after":sum(int(r["pages_after"]) for r in successful),
                    "rotated":sum(int(r["rotated"]) for r in successful),
                    "orientation_inferred":sum(int(r["orientation_inferred"]) for r in successful),
                    "orientation_uncertain":sum(int(r["orientation_uncertain"]) for r in successful),
                    "suspicious_count":sum(int(r["suspicious_count"]) for r in successful),
                    "note":f"Số PDF thành công: {len(successful)} / {len(rows)}"})
                w.writerow(summary)
        self.events.put(("done",rows,total,str(report),str(out)))

    def open_review(self):
        if self.last_report and Path(self.last_report).exists():ReviewWindow(self.root,self.last_target,self.last_report)

    def poll_events(self):
        try:
            while True:
                e=self.events.get_nowait()
                if e[0]=="progress":self.progress["value"]=e[1]-1;self.status.configure(text=f"Đang xử lý {e[1]}/{e[2]}: {e[3]}")
                elif e[0]=="row":
                    r=e[1];self.log(f"{r['status']}: {r['source_file']} → {r['output_file']} | xóa {r['blank_removed']} trang | còn {r['pages_after']} trang | nghi ngờ {r['suspicious_count']} trang | xoay {r['rotated']}")
                elif e[0]=="done":
                    _,rows,total,report,out=e;ok=sum(r["status"]=="Thành công" for r in rows);pages=sum(int(r["pages_after"]) for r in rows if r["status"]=="Thành công");sus=sum(int(r["suspicious_count"]) for r in rows)
                    self.running=False;self.start_button.configure(state="normal");self.progress["value"]=len(rows);self.last_report=report;self.last_target=out;self.review_button.configure(state="normal")
                    self.status.configure(text=f"Hoàn tất: {ok}/{len(rows)} thành công; tổng {pages} trang; {sus} trang nghi ngờ.")
                    messagebox.showinfo("Hoàn tất",f"Tổng PDF tìm thấy: {total}\nĐã xử lý: {len(rows)}\nThành công: {ok}; lỗi: {len(rows)-ok}\nTổng số trang sau chuẩn hóa: {pages}\nTrang nghi ngờ cần duyệt: {sus}\n\nBáo cáo CSV: {report}\nFile nguồn được giữ nguyên.")
        except queue.Empty:pass
        self.root.after(150,self.poll_events)

if __name__=="__main__":
    root=tk.Tk(); CleanerApp(root); root.mainloop()
