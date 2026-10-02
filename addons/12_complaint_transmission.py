"""Data transmission item: Complaint report (99.3.21.4) to GAS."""
import datetime
import re
import time

import customtkinter as ctk
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from addon_kit import GAS_BUSY, LEGACY_NAMES, begin_transmission, get_login, receive_rows, run_transmission
from qad_report import KEY_CTRL_F, KEY_F1, ReportShell, send_to_gas_via_browser

try:
    from ctkdateentry import CTkDateEntry
    HAS_CTK_DATE_ENTRY = True
except ImportError:
    HAS_CTK_DATE_ENTRY = False

ADDON = {"id": "complaint_transmission", "name": "Complaint送信"}
GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbyEwl3D8kjtbkk34V_9aJGrlgt39B480O_W3zCI6JiSC4glpS4XNj6JSC4ZiyMNKA/exec"
CODE_RE = re.compile(r"^[\x21-\x7e]{1,40}$")


def extract(shell, progress, item_num, start_day, end_day, item_lot):
    shell.open(width=132, height=24)
    progress("📋 [2/6] QADメニューを移動中...")
    shell.login("Roll Japan Production", 12)
    shell.clear()
    shell.send("99.3.21.4\r")
    shell.wait_text("Item Number", timeout=15)
    shell.clear()
    progress("⚡ [3/6] 条件を一括貼り付け入力中...")
    lot_part = f"{item_lot}\r{item_lot}\r" if item_lot else "\r\r"
    shell.send(
        f"{item_num}\r{item_num}\r"     # Item Number (From/To)
        "\r\r"                           # Site (From/To)
        f"{start_day}\r{end_day}\r"     # Effective Date (From/To)
        "1fgi\r1fgi\r"                   # Prod Line (From/To)
        "\r\r\r\r"                       # Order / Customer
        f"{lot_part}"                    # Lot (From/To)
        + ("\r" * 11)                    # 11 fields up to Output
    )
    shell.pause(0.3)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    progress("🚀 [4/6] レポート実行開始...")
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def validate_complaint_input(item_text, start_text, end_text, lot_text):
    """Return QAD values or raise ValueError before anything is typed into QAD."""
    item = item_text.strip()
    lot = lot_text.strip()
    if not item:
        raise ValueError("Item code は必須項目です。")
    if not CODE_RE.match(item):
        raise ValueError("Item code は空白を含まない半角英数字・記号で入力してください。")
    if lot and not CODE_RE.match(lot):
        raise ValueError("Cheese lot / Nlot は空白を含まない半角英数字・記号で入力してください。")
    days = []
    for label, text in (("Start date", start_text), ("End date", end_text)):
        try:
            days.append(date_parser.parse(text.strip()).date())
        except (ValueError, OverflowError, TypeError):
            raise ValueError(f"{label} を日付として読み取れません: {text.strip() or '空欄'}") from None
    if days[0] > days[1]:
        raise ValueError("Start date が End date より後になっています。")
    return item, days[0].strftime("%m/%d/%y"), days[1].strftime("%m/%d/%y"), lot


class ComplaintDialog(ctk.CTkToplevel):
    """99.3.21.4 から Complaint データを抽出して GAS へ転送する条件入力ダイアログ"""

    def __init__(self, parent, font_family, on_submit):
        super().__init__(parent)
        self.font_family = font_family
        self.on_submit_callback = on_submit
        self.running = False
        self.title("Complaint 抽出＆GAS転送")
        self.geometry("440x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 440) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 480) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self._build_ui()

    def _date_input(self, frame, value):
        if HAS_CTK_DATE_ENTRY:
            widget = CTkDateEntry(frame, width=380)
            widget.variable.set(value.strftime("%Y/%m/%d"))
            widget.variable.trace_add("write", lambda *args: self._format_date_var(widget.variable))
            widget.get_text = lambda: widget.variable.get().strip()
        else:
            widget = ctk.CTkEntry(frame, width=380)
            widget.insert(0, value.strftime("%Y/%m/%d"))
            widget.get_text = lambda: widget.get().strip()
        widget.pack(fill="x", padx=16, pady=(0, 10))
        return widget

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(frame, text="📝 Complaint 抽出＆GAS転送 (99.3.21.4)",
                     font=ctk.CTkFont(family=self.font_family, size=16, weight="bold")).pack(pady=(6, 14))
        ctk.CTkLabel(frame, text="Item code (必須):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.item_entry = ctk.CTkEntry(frame, width=380, placeholder_text="例: BW0100D")
        self.item_entry.pack(fill="x", padx=16, pady=(0, 10))
        today = datetime.date.today()
        ctk.CTkLabel(frame, text="Start date (YYYY/MM/DD):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.start_cal = self._date_input(frame, today - relativedelta(months=6))
        ctk.CTkLabel(frame, text="End date (YYYY/MM/DD):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.end_cal = self._date_input(frame, today)
        ctk.CTkLabel(frame, text="Cheese lot / Nlot (空白可):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.lot_entry = ctk.CTkEntry(frame, width=380, placeholder_text="空白可")
        self.lot_entry.pack(fill="x", padx=16, pady=(0, 12))
        self.status_label = ctk.CTkLabel(frame, text="", text_color="#D97706", wraplength=380,
                                         font=ctk.CTkFont(family=self.font_family, size=12, weight="bold"))
        self.status_label.pack(fill="x", padx=16, pady=(0, 8))
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 6))
        btn_frame.grid_columnconfigure((0, 1), weight=1)
        self.cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8",
                                        hover_color="#64748B", command=self.close)
        self.cancel_btn.grid(row=0, column=0, padx=6, sticky="ew")
        self.submit_btn = ctk.CTkButton(btn_frame, text="OK (抽出＆GAS転送)", fg_color="#4F46E5",
                                        hover_color="#4338CA", font=ctk.CTkFont(weight="bold"),
                                        command=self.on_submit)
        self.submit_btn.grid(row=0, column=1, padx=6, sticky="ew")
        self.item_entry.focus_set()

    def _format_date_var(self, var):
        val = var.get()
        if not val or re.match(r"^\d{4}[/-]\d{2}[/-]\d{2}$", val):
            return
        try:
            new_val = date_parser.parse(val).strftime("%Y/%m/%d")
        except (ValueError, OverflowError):
            return
        if new_val != val:
            var.set(new_val)

    def set_status(self, text, color="#D97706"):
        if self.winfo_exists():
            self.status_label.configure(text=text, text_color=color)

    def set_running(self, running):
        self.running = running
        if self.winfo_exists():
            state = "disabled" if running else "normal"
            self.submit_btn.configure(state=state)
            self.cancel_btn.configure(state=state)

    def close(self):
        if not self.running:
            self.destroy()

    def on_submit(self):
        try:
            values = validate_complaint_input(self.item_entry.get(), self.start_cal.get_text(),
                                              self.end_cal.get_text(), self.lot_entry.get())
        except ValueError as exc:
            self.set_status(f"❌ {exc}", "#DC2626")
            return
        self.on_submit_callback(self, *values)


def register(api, shell_factory=ReportShell, sender=send_to_gas_via_browser, clock=time.monotonic):
    def submit(dialog, item_num, start_day, end_day, item_lot):
        login = get_login(api, dialog)
        if login is None or not begin_transmission(api, dialog):
            return
        dialog.set_running(True)
        api.set_status(f"🚀 Complaint 抽出＆GAS送信を開始します (Item: {item_num})...", "working")
        api.log_info(f"Complaint送信開始: item={item_num}, start={start_day}, end={end_day}, lot={item_lot}")

        def progress(text, color="#D97706"):
            api.set_status(text, "working")
            api.call_in_ui(lambda: dialog.set_status(text, color))

        def worker():
            try:
                progress("🔌 [1/6] サーバーに接続中...")
                with shell_factory(*login) as shell:
                    extract(shell, progress, item_num, start_day, end_day, item_lot)
                    rows, elapsed, size = receive_rows(shell, progress, "[4/6]")
                count = len(rows) - 1
                progress(f"📤 [6/6] GASへ {count:,}件 を送信中 ({size / 1024:.0f} KB / {elapsed:.1f}秒)...")
                sender(rows, GAS_URL, title="Google Sheets 自動転送 (Complaint)")
                api.set_status(f"✅ ComplaintデータをGASへ転送完了 ({count:,}件)", "success", clear_delay=8)
                api.log_info(f"ComplaintデータGAS送信完了: {count:,}件")
                api.call_in_ui(lambda: (dialog.set_running(False), dialog.close()) if dialog.winfo_exists() else None)
            except Exception as exc:
                api.log_error(f"Complaint送信エラー: {exc}", exc_info=True)
                api.set_status(f"❌ Complaint送信エラー: {exc}", "error", clear_delay=10)
                api.call_in_ui(lambda: (dialog.set_running(False), dialog.set_status("❌ エラーが発生しました", "#DC2626"))
                               if dialog.winfo_exists() else None)
                api.show_error("エラー", f"Complaint送信の処理中にエラーが発生しました:\n\n{exc}")

        run_transmission(api, "complaint", worker)

    def start():
        if api.is_busy(GAS_BUSY):
            api.show_warning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。")
            return
        ComplaintDialog(api.parent, api.font_family, submit)

    api.add_button("run", "📑 Complaint送信 (99.3.21.4)", start, bar="data", color="#4F46E5",
                   hover_color="#4338CA", busy_group=GAS_BUSY, legacy_label=(LEGACY_NAMES, "complaint"))
    api.register_action("complaint_transmission.run", start)
