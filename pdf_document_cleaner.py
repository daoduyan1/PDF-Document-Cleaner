import os, sys, csv, json, threading, queue, subprocess, hashlib, tempfile
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from PIL import Image, ImageChops, ImageFilter
import pytesseract

APP_VERSION = "1.4.2"
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


def exact_pattern(page):
    im = page_image(page, 1.5)
    return "exact:" + hashlib.sha256(str(im.size).encode() + im.tobytes()).hexdigest()


def is_learned_blank(page, patterns=None):
    patterns = load_patterns() if patterns is None else patterns
    legacy = [x for x in patterns if isinstance(x,str) and len(x)==16]
    return bool(legacy) and any(hash_distance(dhash(page), x)<=3 for x in legacy)


def straight_crossed_page(page):
    # Global Hough voting can join interrupted strokes across printed text.
    im = page_image(page, 1.5)
    im.thumbnail((850,1100))
    rgb = np.asarray(im)
    h,w = rgb.shape[:2]
    if min(h,w)<40: return False
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,9)
    color = rgb.max(axis=2).astype(np.int16)-rgb.min(axis=2).astype(np.int16)
    colored = ((color>30)&(rgb.min(axis=2)<220)).astype(np.uint8)*255
    diag = np.hypot(w,h)
    for mask in (colored, ink):
        if not np.any(mask): continue
        # Restrict Hough candidates to diagonals, ignoring horizontal text/rules.
        lines = cv2.HoughLines(mask,1,np.pi/360,max(30,int(min(w,h)*.09)))
        if lines is None: continue
        near = cv2.dilate(mask,np.ones((7,7),np.uint8))
        pos,neg=[],[]
        for rho,theta in lines[:600,0]:
            st,ct=np.sin(theta),np.cos(theta)
            if abs(st)<.20 or abs(ct)<.20: continue
            m=-ct/st; c=rho/st
            if not .30 < abs(m)*w/h < 3.0: continue
            xs=np.linspace(.03*w,.97*w,160); ys=m*xs+c
            valid=(ys>=.03*h)&(ys<.97*h)
            xs=xs[valid].astype(int); ys=ys[valid].astype(int)
            if len(xs)<50: continue
            hit=near[ys,xs]>0
            if hit.mean()<.46: continue
            xx,yy=xs[hit],ys[hit]
            if np.ptp(xx)<.40*w or np.ptp(yy)<.40*h: continue
            if sum(np.any(part) for part in np.array_split(hit,8))<7: continue
            target=pos if m>0 else neg
            target.append((m,c,xx.min(),xx.max()))
            if len(pos)>=30 and len(neg)>=30: break
        for m,c,l,r in pos:
            for n,d,ll,rr in neg:
                x=(d-c)/(m-n); y=m*x+c
                if .12*w<=x<=.88*w and .12*h<=y<=.88*h and l<=x<=r and ll<=x<=rr: return True
    return False


def curved_crossed_page(page):
    # Faint curved cancellation strokes: local background subtraction, remove
    # horizontal rules, then look for a thin connected hourglass-shaped trace.
    im = page_image(page, 1.5)
    im.thumbnail((750, 1050))
    gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    if min(h,w) < 100: return False
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((15,15),np.uint8))
    delta = cv2.subtract(bg,gray)
    for threshold in (8, 5):
        mask = (delta >= threshold).astype(np.uint8)*255
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1,max(25,w//16)),np.uint8))
        mask = cv2.subtract(mask,horizontal)
        mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        mask[:int(.035*h)] = 0; mask[int(.965*h):] = 0
        mask[:,:int(.025*w)] = 0; mask[:,int(.975*w):] = 0
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        for i,(x,y,bw,bh,area) in enumerate(stats[1:],1):
            if bw < .40*w or bh < .55*h or area/(bw*bh) > .12: continue
            ys,xs = np.where(labels[y:y+bh,x:x+bw] == i)
            # Both arms must be visible across the top and bottom, with a
            # narrow crossing between them. Quantiles resist isolated noise.
            bands = []
            for j in range(12):
                xx = xs[(ys >= j*bh/12)&(ys < (j+1)*bh/12)]
                if len(xx)<8: bands.append(None); continue
                lo,hi=np.quantile(xx,[.12,.88]); bands.append((lo,hi))
            if any(b is None for b in bands): continue
            widths=np.array([b[1]-b[0] for b in bands])
            k=int(np.argmin(widths[3:9]))+3
            if min(max(widths[:3]),max(widths[-3:])) < .40*bw: continue
            if widths[k] > .30*bw: continue
            left=np.array([b[0] for b in bands]); right=np.array([b[1] for b in bands])
            if min(left[k]-left[1],right[1]-right[k],left[k]-left[10],right[10]-right[k]) < .12*bw: continue
            return True
    return False


def crossed_page(page):
    return straight_crossed_page(page) or curved_crossed_page(page)


def orientation_score(im):
    # Compare actual recognized word confidence, not only OSD confidence.
    d=pytesseract.image_to_data(im,lang="vie+eng",config=f'--dpi 180 --psm 6 --tessdata-dir "{TESSDATA}"',output_type=pytesseract.Output.DICT,timeout=25)
    words=[(str(t),float(c)) for t,c in zip(d['text'],d['conf']) if str(t).strip() and float(c)>=0]
    good=[(t,c) for t,c in words if c>=55 and sum(ch.isalpha() for ch in t)>=2]
    return sum(min(len(t),12)*c/100 for t,c in good),len(good)


def suggested_rotation(page):
    if TESSDATA is None: return None,0.0,"Thiếu Tesseract trong Cleaner"
    im=page_image(page,2.5).convert('L')
    angle=None; conf=0.; error=""
    try:
        d=pytesseract.image_to_osd(im,output_type=pytesseract.Output.DICT,config=f'--dpi 180 --tessdata-dir "{TESSDATA}"',timeout=20)
        angle=int(d.get('rotate',0))%360; conf=float(d.get('orientation_conf',0))
        if angle in (0,90,180,270) and conf>=10: return angle,conf,"OSD"
    except Exception as e: error=str(e)
    try:
        # For weak OSD, compare upright and upside-down text; consider sideways
        # if OSD suggests it. Positive PDF rotation is clockwise.
        angles=(0,90,180,270) if angle in (90,270) else (0,180)
        scores=[]
        for a in angles:
            candidate=im if a==0 else im.rotate(-a,expand=True)
            score,n=orientation_score(candidate)
            scores.append((score,n,a))
        scores.sort(reverse=True); best,n,a=scores[0]; second=scores[1][0]
        if n>=5 and best>=12 and best>=second*1.45+5: return a, best/(second+1),"OCR đối chiếu"
        return None,conf,"Không đủ bằng chứng hướng trang"+("; OSD: "+error[:180] if error else "")
    except Exception as e: return None,conf,"OCR lỗi: "+str(e)[:250]+("; OSD: "+error[:150] if error else "")


def process_pdf(src, input_root, output_root, output_name, rotate_enabled, detect_x=True, learned_auto=False):
    dest = output_root / output_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists(): raise FileExistsError(f"File kết quả đã tồn tại: {dest.name}")
    doc = fitz.open(src)
    try:
        if doc.needs_pass: raise ValueError("PDF được bảo vệ bằng mật khẩu.")
        before = len(doc)
        blank, suspicious = [], []
        patterns = load_patterns()
        reasons = {}
        for i, page in enumerate(doc):
            ratio = foreground_ratio(page)
            if learned_auto and patterns and exact_pattern(page) in patterns:
                blank.append(i)
            elif detect_x and crossed_page(page):
                suspicious.append(i+1); reasons[i+1] = "Dấu X"
            elif ratio <= 0.00015 and not page.get_text().strip(): blank.append(i)
            elif (ratio <= 0.005 and not page.get_text().strip()) or is_learned_blank(page, patterns) or (patterns and exact_pattern(page) in patterns):
                suspicious.append(i+1); reasons[i+1] = "Trang mờ / mẫu đã lưu"
        if before and len(blank) == before:
            suspicious = list(range(1,before+1)); reasons = {i:"Toàn bộ hồ sơ nghi trắng" for i in suspicious}; blank = []
        for i in reversed(blank): doc.delete_page(i)
        # Re-index suspicious pages after definite blank deletion.
        reasons = {p - sum(1 for b in blank if b < p-1): v for p,v in reasons.items()}
        suspicious = sorted(reasons)
        rotated = inferred = uncertain = 0
        orientation_notes = []
        consensus = None
        if rotate_enabled in (90,180,270):
            for page in doc: page.set_rotation((page.rotation+rotate_enabled)%360); rotated += 1
            consensus=rotate_enabled
        elif rotate_enabled is True and len(doc):
            detections = [suggested_rotation(p) for p in doc]
            known = [a for a,c,n in detections if a is not None]
            if known:
                counts = {a:known.count(a) for a in set(known)}
                dominant = max(counts, key=counts.get)
                if (len(known)>=2 or len(doc)==1) and counts[dominant]/len(known)>=.90: consensus=dominant
            for index, (page, (angle, conf, method)) in enumerate(zip(doc, detections),1):
                if angle is None: orientation_notes.append(f"Trang {index}: {method}")
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
          "suspicious_count":len(suspicious),"output_file":str(output_name),"note":"; ".join([*(f"{k}: {v}" for k,v in reasons.items()), *orientation_notes])}
    finally: doc.close()


class ReviewWindow:
    def __init__(self, root, output_dir, report_path):
        self.root=root; self.output_dir=Path(output_dir); self.report_path=Path(report_path)
        self.rows=[]; self.current=None; self.photo=None
        with self.report_path.open(encoding="utf-8-sig", newline="") as f: self.rows=list(csv.DictReader(f))
        self.win=tk.Toplevel(root); self.win.title("Duyệt, xóa và xoay hồ sơ"); self.win.geometry("1000x700")
        left=ttk.Frame(self.win); left.pack(side="left",fill="y",padx=8,pady=8)
        ttk.Label(left,text="Hồ sơ kết quả (tất cả)").pack(anchor="w")
        self.files=tk.Listbox(left,width=42,height=28,exportselection=False); self.files.pack(fill="y",expand=True)
        self.items=[r for r in self.rows if r.get("status")=="Thành công" and r.get("output_file")]
        for r in self.items: self.files.insert("end",f"{r['output_file']} ({r['suspicious_count']} trang)")
        self.files.bind("<<ListboxSelect>>",self.select_file)
        right=ttk.Frame(self.win); right.pack(side="left",fill="both",expand=True,padx=8,pady=8)
        ttk.Label(right,text="Trang nghi ngờ (số trang trong PDF kết quả)").pack(anchor="w")
        self.pages=tk.Listbox(right,height=4,exportselection=False); self.pages.pack(fill="x")
        self.pages.bind("<<ListboxSelect>>",self.preview)
        nav=ttk.Frame(right); nav.pack(fill="x")
        self.page_no=tk.StringVar(value="1")
        ttk.Entry(nav,textvariable=self.page_no,width=7).pack(side="left")
        ttk.Button(nav,text="Xem trang bất kỳ",command=self.preview_number).pack(side="left")
        for angle in (90,180,270):
            ttk.Button(nav,text=f"Xoay cả hồ sơ {angle}°",command=lambda a=angle:self.rotate_file(a)).pack(side="left",padx=2)
        self.preview_label=ttk.Label(right,text="Chọn hồ sơ và trang để xem trước"); self.preview_label.pack(fill="both",expand=True,pady=8)
        buttons=ttk.Frame(right); buttons.pack(fill="x")
        ttk.Button(buttons,text="Xóa trang",command=lambda:self.delete_remember(False)).pack(side="left",padx=4)
        ttk.Button(buttons,text="Xóa + ghi nhớ mẫu",command=self.delete_remember).pack(side="left",padx=4)
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
        else:self.page_no.set("1"); self.preview_number()

    def preview(self,_=None):
        sel=self.pages.curselection()
        if not sel or not self.current:return
        self.page_no.set(self.pages.get(sel[0])); self.preview_number()

    def preview_number(self):
        if not self.current:return
        self.shown=None
        try:
            n=int(self.page_no.get()); path=self.output_dir/self.current["output_file"]
            with fitz.open(path) as d:
                if not 1<=n<=len(d):raise ValueError("Số trang không hợp lệ")
                im=page_image(d[n-1],1.5)
        except Exception as e:
            messagebox.showerror("Lỗi",str(e),parent=self.win);return
        self.shown=(self.current,n)
        im.thumbnail((650,520)); self.photo=ImageTk.PhotoImage(im)
        self.preview_label.configure(image=self.photo,text="")

    def selected_page(self):
        if not self.current or getattr(self,"shown",None)!=(self.current,int(self.page_no.get())):
            raise ValueError("Hãy xem trước trang cần thao tác.")
        return int(self.page_no.get())

    def delete_remember(self, remember=True):
        try:
            n=self.selected_page(); path=self.output_dir/self.current["output_file"]
            if not messagebox.askyesno("Xác nhận",f"Xóa trang {n} khỏi {path.name}?" + (" Ghi nhớ mẫu chính xác." if remember else ""),parent=self.win):return
            with fitz.open(path) as d:
                if len(d)<=1:raise ValueError("Không được xóa trang cuối cùng.")
                pattern=exact_pattern(d[n-1]) if remember else None
                d.delete_page(n-1); tmp=path.with_suffix(".review.tmp")
                d.save(tmp,garbage=0,deflate=False)
            os.replace(tmp,path)
            if pattern:save_pattern(pattern)
            vals=[int(x) for x in self.current.get("suspicious_pages", "").split(";") if x and int(x)!=n]
            self.current["suspicious_pages"]=";".join(str(x-(x>n)) for x in vals)
            self.current["suspicious_count"]=str(len(vals)); self.current["pages_after"]=str(int(self.current["pages_after"])-1)
            self.current["blank_removed"]=str(int(self.current["blank_removed"])+1)
            self.current["note"]+=f" | Xóa thủ công trang {n}"
            self.write_report(); self.refresh_pages()
        except Exception as e:messagebox.showerror("Lỗi",str(e),parent=self.win)

    def rotate_file(self, angle):
        if not self.current:return
        path=self.output_dir/self.current["output_file"]
        if not messagebox.askyesno("Xác nhận",f"Xoay toàn bộ {path.name} {angle}° theo chiều kim đồng hồ?",parent=self.win):return
        try:
            with fitz.open(path) as d:
                for page in d:page.set_rotation((page.rotation+angle)%360)
                tmp=path.with_suffix(".review.tmp"); d.save(tmp,garbage=0,deflate=False)
            os.replace(tmp,path)
            self.current["note"]+=f" | Xoay thủ công toàn hồ sơ {angle}°"
            self.write_report(); self.preview_number()
        except Exception as e:messagebox.showerror("Lỗi",str(e),parent=self.win)

    def keep(self):
        try:n=self.selected_page()
        except Exception as e:messagebox.showerror("Lỗi",str(e),parent=self.win);return
        vals=[x for x in self.current.get("suspicious_pages", "").split(";") if x and int(x)!=n]
        self.current["suspicious_pages"]=";".join(vals); self.current["suspicious_count"]=str(len(vals)); self.write_report(); self.refresh_pages()

    def write_report(self):
        if not self.rows:return
        ok=[r for r in self.rows if r.get("status")=="Thành công"]
        for row in self.rows:
            if row.get("status")=="TỔNG HỢP":
                for k in ("pages_before","blank_removed","pages_after","suspicious_count"):
                    row[k]=sum(int(r[k]) for r in ok)
        with self.report_path.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(self.rows[0].keys())); w.writeheader(); w.writerows(self.rows)


# ImageTk import after tkinter is initialized
from PIL import ImageTk

class CleanerApp:
    def __init__(self,root):
        self.root=root; root.title(f"PDF Document Cleaner {APP_VERSION} - HMDS"); root.geometry("970x720"); root.minsize(850,650)
        self.source=tk.StringVar(); self.target=tk.StringVar(); self.start_number=tk.StringVar(value="1"); self.year=tk.StringVar(value=str(datetime.now().year)); self.suffix=tk.StringVar()
        self.rename=tk.BooleanVar(value=False); self.rotate=tk.StringVar(value="Tự nhận diện"); self.detect_x=tk.BooleanVar(value=True); self.learned_auto=tk.BooleanVar(value=False); self.events=queue.Queue(); self.running=False; self.last_report=None; self.last_target=None
        self.build_ui(); root.after(150,self.poll_events)

    def build_ui(self):
        pad={"padx":14,"pady":5}
        ttk.Label(self.root,text="PDF DOCUMENT CLEANER",font=("Segoe UI",18,"bold")).pack(anchor="w",**pad)
        ttk.Label(self.root,text=f"Phiên bản {APP_VERSION} | Tối đa {LIMIT} PDF mỗi lượt | OCR là phân hệ riêng.").pack(anchor="w",padx=14)
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
        ttk.Combobox(opts,textvariable=self.rotate,state="readonly",values=["Không xoay","Tự nhận diện","Xoay 90°","Xoay 180°","Xoay 270°"],width=24).pack(anchor="w",padx=8,pady=3)
        ttk.Checkbutton(opts,text="Phát hiện dấu X lớn (đưa vào danh sách duyệt)",variable=self.detect_x).pack(anchor="w",padx=8)
        ttk.Checkbutton(opts,text="Tự xóa mẫu đã ghi nhớ nếu ảnh khớp chính xác",variable=self.learned_auto).pack(anchor="w",padx=8)
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
        if self.rotate.get()=="Tự nhận diện":
            try:
                if TESSDATA is None: raise RuntimeError("Không tìm thấy Tesseract trong bộ cài Cleaner.")
                langs=pytesseract.get_languages(config=f'--tessdata-dir "{TESSDATA}"')
                if not {"osd","vie","eng"}.issubset(langs): raise RuntimeError("Thiếu dữ liệu osd/vie/eng.")
            except Exception as e: messagebox.showerror("Không thể nhận diện hướng",str(e));return
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
        threading.Thread(target=self.worker,args=(pdfs,src,out,total,names,{"Không xoay":False,"Tự nhận diện":True,"Xoay 90°":90,"Xoay 180°":180,"Xoay 270°":270}[self.rotate.get()],self.detect_x.get(),self.learned_auto.get()),daemon=True).start()

    def worker(self,pdfs,src,out,total,names,rotate,detect_x,learned_auto):
        rows=[]
        for i,p in enumerate(pdfs):
            name=names[i]; self.events.put(("progress",i+1,len(pdfs),p.name))
            try:r=process_pdf(p,src,out,name,rotate,detect_x,learned_auto)
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
                    r=e[1];self.log(f"{r['status']}: {r['source_file']} → {r['output_file']} | xóa {r['blank_removed']} trang | còn {r['pages_after']} trang | nghi ngờ {r['suspicious_count']} trang | xoay {r['rotated']} | chưa xác định {r['orientation_uncertain']}")
                elif e[0]=="done":
                    _,rows,total,report,out=e;ok=sum(r["status"]=="Thành công" for r in rows);pages=sum(int(r["pages_after"]) for r in rows if r["status"]=="Thành công");sus=sum(int(r["suspicious_count"]) for r in rows)
                    self.running=False;self.start_button.configure(state="normal");self.progress["value"]=len(rows);self.last_report=report;self.last_target=out;self.review_button.configure(state="normal")
                    self.status.configure(text=f"Hoàn tất: {ok}/{len(rows)} thành công; tổng {pages} trang; {sus} trang nghi ngờ.")
                    messagebox.showinfo("Hoàn tất",f"Tổng PDF tìm thấy: {total}\nĐã xử lý: {len(rows)}\nThành công: {ok}; lỗi: {len(rows)-ok}\nTổng số trang sau chuẩn hóa: {pages}\nTrang nghi ngờ cần duyệt: {sus}\n\nBáo cáo CSV: {report}\nFile nguồn được giữ nguyên.")
        except queue.Empty:pass
        self.root.after(150,self.poll_events)

if __name__=="__main__":
    root=tk.Tk(); CleanerApp(root); root.mainloop()
