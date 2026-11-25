"""PDF OCR - module độc lập, chạy sau khi PDF Document Cleaner chuẩn hóa hồ sơ."""
import os, sys, threading, queue
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from PIL import Image
import pytesseract

APP_VERSION="1.0.1"
AUTHOR="Đào Duy An - daoduyan.com"
PUBLISHER="HMDS - hmds.vn"
LIMIT=500

def resource_path(*parts):
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent)).joinpath(*parts)

TESS=resource_path("tesseract","tesseract.exe")
DATA=resource_path("tesseract","tessdata")
if TESS.exists():
    pytesseract.pytesseract.tesseract_cmd=str(TESS)
    os.environ["TESSDATA_PREFIX"]=str(DATA)


def ocr_pdf(src:Path, root:Path, out:Path, lang:str):
    rel=src.relative_to(root)
    dest=(out/rel).with_suffix(".txt")
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists(): raise FileExistsError(f"Tệp TXT đã tồn tại: {dest}")
    chunks=[]
    with fitz.open(src) as doc:
        if doc.needs_pass: raise ValueError("PDF được bảo vệ bằng mật khẩu.")
        for i,page in enumerate(doc,1):
            pix=page.get_pixmap(matrix=fitz.Matrix(300/72,300/72),colorspace=fitz.csRGB,alpha=False)
            image=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
            text=pytesseract.image_to_string(image,lang=lang,config="--oem 1 --psm 3",timeout=180)
            chunks.append(f"===== TRANG {i} =====\n{text.strip()}\n")
    dest.write_text("\n".join(chunks),encoding="utf-8-sig")
    return dest, len(chunks)

class OCRApp:
    def __init__(self,root):
        self.root=root;root.title(f"PDF OCR {APP_VERSION} - HMDS");root.geometry("850x600");root.minsize(760,520)
        self.source=tk.StringVar();self.target=tk.StringVar();self.lang=tk.StringVar(value="vie+eng");self.q=queue.Queue();self.running=False
        self.ui();root.after(150,self.poll)
    def ui(self):
        pad={"padx":14,"pady":7}
        ttk.Label(self.root,text="PDF OCR – NHẬN DẠNG VĂN BẢN",font=("Segoe UI",17,"bold")).pack(anchor="w",**pad)
        ttk.Label(self.root,text="Phân hệ độc lập. Đầu vào là PDF đã chuẩn hóa; đầu ra là TXT UTF-8.").pack(anchor="w",padx=14)
        for label,var,cmd in (("Thư mục PDF đã chuẩn hóa:",self.source,self.pick_src),("Thư mục lưu TXT:",self.target,self.pick_out)):
            row=ttk.Frame(self.root);row.pack(fill="x",**pad);ttk.Label(row,text=label,width=27).pack(side="left");ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True,padx=6);ttk.Button(row,text="Chọn...",command=cmd).pack(side="right")
        row=ttk.Frame(self.root);row.pack(fill="x",**pad);ttk.Label(row,text="Ngôn ngữ OCR:",width=27).pack(side="left");ttk.Combobox(row,textvariable=self.lang,values=["vie+eng","vie","eng"],state="readonly",width=16).pack(side="left",padx=6)
        ttk.Label(self.root,text="vie+eng: tiếng Việt và tiếng Anh. Mỗi PDF tạo một TXT cùng cấu trúc thư mục tương ứng.").pack(anchor="w",padx=14,pady=3)
        self.progress=ttk.Progressbar(self.root,mode="determinate",maximum=LIMIT);self.progress.pack(fill="x",padx=14,pady=10)
        self.status=ttk.Label(self.root,text="Sẵn sàng",anchor="w");self.status.pack(fill="x",padx=14)
        self.logbox=tk.Text(self.root,height=16,state="disabled",wrap="word");self.logbox.pack(fill="both",expand=True,padx=14,pady=8)
        row=ttk.Frame(self.root);row.pack(fill="x",padx=14,pady=8);self.go=ttk.Button(row,text="BẮT ĐẦU OCR (TỐI ĐA 500 PDF)",command=self.start);self.go.pack(side="left");ttk.Button(row,text="Thoát",command=self.root.destroy).pack(side="right")
        ttk.Label(self.root,text=f"Bản quyền tác giả: {AUTHOR}  |  Đơn vị phát hành: {PUBLISHER}",font=("Segoe UI",8)).pack(pady=(0,8))
    def pick_src(self):
        x=filedialog.askdirectory(title="Chọn thư mục PDF đã chuẩn hóa");self.source.set(x) if x else None
    def pick_out(self):
        x=filedialog.askdirectory(title="Chọn thư mục lưu TXT");self.target.set(x) if x else None
    def log(self,s):
        self.logbox.configure(state="normal");self.logbox.insert("end",s+"\n");self.logbox.see("end");self.logbox.configure(state="disabled")
    def start(self):
        if self.running:return
        src=Path(self.source.get()).resolve();out=Path(self.target.get()).resolve()
        if not src.is_dir() or not self.target.get():messagebox.showwarning("Thiếu thông tin","Hãy chọn đủ hai thư mục.");return
        if not (DATA/"vie.traineddata").exists():messagebox.showerror("Thiếu dữ liệu tiếng Việt","Bộ cài chưa có vie.traineddata. Hãy cài lại gói OCR đầy đủ.");return
        if out==src or out in src.parents or src in out.parents:messagebox.showerror("Lỗi","Thư mục TXT phải tách biệt thư mục PDF nguồn.");return
        pdfs=sorted((p for p in src.rglob("*") if p.is_file() and p.suffix.lower()==".pdf"),key=lambda p:str(p.relative_to(src)).lower())
        if not pdfs:messagebox.showinfo("Thông báo","Không tìm thấy PDF.");return
        if len(pdfs)>LIMIT and not messagebox.askyesno("Giới hạn",f"Tìm thấy {len(pdfs)} PDF. Chỉ xử lý {LIMIT} file đầu tiên?"):return
        pdfs=pdfs[:LIMIT];out.mkdir(parents=True,exist_ok=True)
        self.running=True;self.go.configure(state="disabled");self.progress.configure(maximum=len(pdfs),value=0)
        threading.Thread(target=self.worker,args=(pdfs,src,out,self.lang.get()),daemon=True).start()
    def worker(self,pdfs,src,out,lang):
        ok=0;errors=[]
        for i,p in enumerate(pdfs):
            self.q.put(("progress",i+1,len(pdfs),p.name))
            try:
                dest,n=ocr_pdf(p,src,out,lang);ok+=1;self.q.put(("log",f"OK: {p.name} → {dest.name} ({n} trang)"))
            except Exception as e:errors.append((str(p),str(e)));self.q.put(("log",f"LỖI: {p.name}: {e}"))
        self.q.put(("done",ok,len(pdfs),errors,str(out)))
    def poll(self):
        try:
            while True:
                e=self.q.get_nowait()
                if e[0]=="progress":self.progress["value"]=e[1]-1;self.status.configure(text=f"OCR {e[1]}/{e[2]}: {e[3]}")
                elif e[0]=="log":self.log(e[1])
                elif e[0]=="done":
                    _,ok,total,errors,out=e;self.running=False;self.go.configure(state="normal");self.progress["value"]=total;self.status.configure(text=f"Hoàn tất: {ok}/{total} thành công; {len(errors)} lỗi.")
                    messagebox.showinfo("Hoàn tất OCR",f"Thành công: {ok}\nLỗi: {len(errors)}\nThư mục TXT: {out}\n\nPDF gốc không bị thay đổi.")
        except queue.Empty:pass
        self.root.after(150,self.poll)

if __name__=="__main__":
    root=tk.Tk();OCRApp(root);root.mainloop()
