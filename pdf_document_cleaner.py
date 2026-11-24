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
                    "rotated": 0, "orientation_inferred": 0,
                    "orientation_consensus": "Không xác lập",
                    "orientation_uncertain": 0, "rotated_pages": "",
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
                        f"xoay {row['rotated']} trang "
                        f"(suy luận {row['orientation_inferred']}) | "
                        f"chưa xác định hướng {row['orientation_uncertain']}"
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
