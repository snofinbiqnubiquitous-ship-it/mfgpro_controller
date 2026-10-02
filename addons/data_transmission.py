"""Data transmission: extract QAD reports with 32prn and forward them to GAS.

Each report opens its own SSH login and does not touch the terminal tabs. The
key sequences and waits are unchanged from the versions recorded as working.
"""
import datetime
import re
import time
import tkinter as tk

import customtkinter as ctk
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from qad_report import KEY_CTRL_F, KEY_F1, ReportShell, send_to_gas_via_browser

try:
    from ctkdateentry import CTkDateEntry
    HAS_CTK_DATE_ENTRY = True
except ImportError:
    HAS_CTK_DATE_ENTRY = False

ADDON = {"id": "data_transmission", "name": "データ送信 (GAS)"}

INVENTORY_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbwS6dZ9umUKP71NGieiW_tDffygGtAFHKOAxyAo7cWDe3T_xMxlISSdmXoNlK6TaENfkA/exec"
COMPLAINT_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbyEwl3D8kjtbkk34V_9aJGrlgt39B480O_W3zCI6JiSC4glpS4XNj6JSC4ZiyMNKA/exec"
PARALLEL_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbxkUsNnoE0mPLRt-6XNwEP4ns9hqSzeWKsu4i_BXSrfcPvdye2rRDp_RBvOLeTvKje-/exec"

NAMES_KEY = "data_transmission_names"
DEFAULT_NAMES = {
    "inventory": "📦 在庫レポートGAS送信 (99.3.6.1)",
    "complaint": "📑 Complaint送信 (99.3.21.4)",
    "parallel": "⚡ 受注残＆売上 並行送信 (99.7.6.20 & 99.7.5.11)",
}
BUTTONS = (
    ("inventory", "在庫レポート (99.3.6.1)", "#059669", "#047857"),
    ("complaint", "Complaint (99.3.21.4)", "#4F46E5", "#4338CA"),
    ("parallel", "受注残＆売上 並行 (99.7.6.20 & 11)", "#D97706", "#B45309"),
)
BUSY = "gas_transmission"
CODE_RE = re.compile(r"^[\x21-\x7e]{1,40}$")


# ---------------------------------------------------------------------------
# Report procedures (unchanged key sequences)
# ---------------------------------------------------------------------------

def extract_inventory(shell, progress):
    shell.open(width=256, height=60)
    progress("📋 [2/5] QADメニュー(99.3.6.1)へ移動中...")
    shell.login("Selection:", 10)
    shell.clear()
    shell.send("99.3.6.1\r")
    shell.pause(1.5)
    shell.clear()
    progress("⚡ [3/5] 条件 '1fgi' を一括貼り付け入力中...")
    shell.send("\r" * 8 + "1fgi\r" + "1fgi\r")
    shell.pause(0.3)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.8)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def extract_complaint(shell, progress, item_num, start_day, end_day, item_lot):
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


def extract_order_backlog(shell, progress):
    shell.open(width=256, height=60)
    shell.login("Selection:", 10)
    shell.clear()
    shell.pause(0.5)
    shell.send("99.7.6.20\r")
    shell.wait_text("Sales Order", timeout=15)
    shell.pause(0.8)
    shell.clear()
    for _ in range(6):
        shell.send("\r")
        shell.pause(0.15)
    shell.send("1fgi\r")
    shell.pause(0.2)
    shell.send("1fgi\r")
    shell.pause(0.2)
    for _ in range(8):
        shell.send("\r")
        shell.pause(0.15)
    shell.send(datetime.date.today().strftime("%m/%d/%y") + "\r")
    shell.pause(0.3)
    shell.send(KEY_F1)
    shell.pause(1.0)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def extract_sales(shell, progress, start_day, end_day):
    shell.open(width=256, height=60)
    shell.login("Selection:", 10)
    shell.clear()
    shell.pause(0.5)
    shell.send("99.7.5.11\r")
    shell.wait_text("Invoice", timeout=15)
    shell.pause(0.8)
    shell.clear()
    for _ in range(4):                   # Invoice(2) + Sales Order(2)
        shell.send("\r")
        shell.pause(0.15)
    shell.send(start_day + "\r")
    shell.pause(0.2)
    shell.send(end_day + "\r")
    shell.pause(0.2)
    for _ in range(10):                  # Customer, Bill-To, Salespsn, Item, Group
        shell.send("\r")
        shell.pause(0.15)
    shell.send("1FGI\r")
    shell.pause(0.2)
    shell.send("1FGI\r")
    shell.pause(0.2)
    for _ in range(3):                   # Site(2) + Include Sample(1)
        shell.send("\r")
        shell.pause(0.15)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def receive_rows(shell, progress, step, menu=""):
    def on_progress(stage, elapsed):
        if stage == "capturing":
            progress(f"📥 {step} 圧縮データを受信中...")
        else:
            progress(f"⏳ {step} サーバーでクエリ実行中... ({elapsed}秒経過)")

    progress(f"⏳ {step} 32prn 圧縮ストリームを受信中...")
    rows, elapsed, size = shell.receive_rows(300, on_progress)
    if len(rows) <= 1:
        prefix = f"{menu}: " if menu else ""
        raise ValueError(f"{prefix}抽出結果が0件でした。条件に一致するデータが存在しないか、レポート解析に失敗しました。")
    return rows, elapsed, size


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


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

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


class NameSettingDialog(ctk.CTkToplevel):
    """データ送信ボタン名のカスタマイズ設定ダイアログ"""

    def __init__(self, parent, colors, font_family, names, focus_key, on_save):
        super().__init__(parent)
        self.on_save_callback = on_save
        self.title("データ送信ボタン名の設定")
        self.geometry("560x400")
        self.minsize(500, 350)
        self.configure(fg_color=colors["background"])
        self.transient(parent)
        self.grab_set()
        font = lambda size, bold=False: ctk.CTkFont(family=font_family, size=size, weight="bold" if bold else "normal")
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(header, text="📤 データ送信ボタン名の編集", font=font(15, True),
                     text_color=colors["text"]).pack(anchor="w")
        ctk.CTkLabel(header, text="ツールバーに表示されるデータ送信ボタンの表示名を自由に変更できます。\n空欄のまま保存した項目は自動的に初期名に戻ります。",
                     font=font(11), text_color=colors["muted"], justify="left").pack(anchor="w", pady=(4, 0))
        form = ctk.CTkFrame(self, fg_color=colors["panel"], corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=8)
        self.entries = {}
        for index, (key, label, badge_color, _) in enumerate(BUTTONS):
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(12 if index == 0 else 8, 2))
            ctk.CTkLabel(row, text="●", text_color=badge_color, font=font(10)).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(row, text=label, font=font(12, True), text_color=colors["text"]).pack(side="left")
            input_row = ctk.CTkFrame(form, fg_color="transparent")
            input_row.pack(fill="x", padx=16, pady=(0, 6))
            entry = ctk.CTkEntry(input_row, font=font(12), height=30)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entry.insert(0, names.get(key, DEFAULT_NAMES[key]))
            self.entries[key] = entry
            ctk.CTkButton(input_row, text="初期名", width=60, height=28, fg_color="transparent",
                          hover_color=colors["hover"], border_width=1, border_color=colors["border"],
                          text_color=colors["text"], font=font(11),
                          command=lambda e=entry, d=DEFAULT_NAMES[key]: (e.delete(0, tk.END), e.insert(0, d))).pack(side="right")
            if key == focus_key:
                entry.focus_set()
                entry.select_range(0, tk.END)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(bar, text="全項目を初期名に戻す", width=140, fg_color="transparent",
                      hover_color=colors["hover"], border_width=1, border_color=colors["border"],
                      text_color=colors["text"], font=font(12), command=self._reset_all).pack(side="left")
        ctk.CTkButton(bar, text="保存", width=90, fg_color="#2563EB", hover_color="#1D4ED8",
                      text_color="#FFFFFF", font=font(12, True), command=self._save).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bar, text="キャンセル", width=90, fg_color=colors["button"], hover_color=colors["hover"],
                      text_color=colors["text"], font=font(12), command=self.destroy).pack(side="right")

    def _reset_all(self):
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, DEFAULT_NAMES[key])

    def _save(self):
        self.on_save_callback({key: entry.get().strip() or DEFAULT_NAMES[key] for key, entry in self.entries.items()})
        self.destroy()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(api, shell_factory=ReportShell, sender=send_to_gas_via_browser, clock=time.monotonic):
    handles = {}

    def names():
        stored = api.config_get(NAMES_KEY, {})
        return {key: (stored.get(key) if isinstance(stored, dict) else None) or DEFAULT_NAMES[key] for key in DEFAULT_NAMES}

    def save_names(new_names):
        api.config_set(NAMES_KEY, new_names)
        for key, handle in handles.items():
            handle.set_text(new_names[key])
        api.set_status("データ送信ボタン名を更新しました", "info", clear_delay=3)

    def open_names(focus_key="inventory"):
        NameSettingDialog(api.parent, api.colors, api.font_family, names(), focus_key, save_names)

    def reset_name(key):
        current = names()
        current[key] = DEFAULT_NAMES[key]
        save_names(current)

    def context_menu(event, key):
        menu = tk.Menu(api.parent, tearoff=False)
        menu.add_command(label="ボタン名を変更...", command=lambda: open_names(key))
        menu.add_command(label="初期の名前に戻す", command=lambda: reset_name(key))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def credentials(parent=None):
        host, port, user, pwd = api.qad_credentials()
        if not user or not pwd:
            api.show_error("ログイン情報未設定",
                           "QADのログイン情報が設定されていません。\nメニューの「ログイン情報」からユーザーIDとパスワードを設定してください。",
                           parent)
            return None
        return host, port, user, pwd

    def set_buttons_enabled(enabled):
        for handle in handles.values():
            handle.set_enabled(enabled)

    def begin(parent=None):
        if not api.try_acquire(BUSY):
            api.show_warning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。", parent)
            return False
        set_buttons_enabled(False)
        return True

    def finish():
        api.release(BUSY)
        set_buttons_enabled(True)

    def run_inventory():
        login = credentials()
        if login is None or not begin():
            return
        api.set_status("🚀 在庫レポート抽出＆GAS送信を開始します...", "working")
        api.log_info(f"在庫レポートGAS送信開始: ユーザー={login[2]}, ホスト={login[0]}")
        progress = lambda text: api.set_status(text, "working")

        def worker():
            try:
                progress("🔌 [1/5] QADサーバーに接続中...")
                with shell_factory(*login) as shell:
                    extract_inventory(shell, progress)
                    rows, elapsed, size = receive_rows(shell, progress, "[4/5]")
                count = len(rows) - 1
                progress(f"🚀 [5/5] ブラウザを起動しGASへ送信中 ({count:,}件 / {size / 1024:.0f} KB / {elapsed:.1f}秒)...")
                sender(rows, INVENTORY_GAS_URL, title="Google Sheets 自動転送 (在庫レポート 1FGI)")
                api.set_status(f"✅ 在庫レポートをGASへ転送完了 ({count:,}件)", "success", clear_delay=8)
                api.log_info(f"在庫レポートGAS送信完了: {count:,}件")
            except Exception as exc:
                api.log_error(f"在庫レポートGAS送信エラー: {exc}", exc_info=True)
                api.set_status(f"❌ 在庫レポートGAS送信エラー: {exc}", "error", clear_delay=10)
                api.show_error("エラー", f"在庫レポートの処理中にエラーが発生しました:\n\n{exc}")
            finally:
                finish()

        api.run_in_background(worker, "inventory")

    def submit_complaint(dialog, item_num, start_day, end_day, item_lot):
        login = credentials(dialog)
        if login is None or not begin(dialog):
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
                    extract_complaint(shell, progress, item_num, start_day, end_day, item_lot)
                    rows, elapsed, size = receive_rows(shell, progress, "[4/6]")
                count = len(rows) - 1
                progress(f"📤 [6/6] GASへ {count:,}件 を送信中 ({size / 1024:.0f} KB / {elapsed:.1f}秒)...")
                sender(rows, COMPLAINT_GAS_URL, title="Google Sheets 自動転送 (Complaint)")
                api.set_status(f"✅ ComplaintデータをGASへ転送完了 ({count:,}件)", "success", clear_delay=8)
                api.log_info(f"ComplaintデータGAS送信完了: {count:,}件")
                api.call_in_ui(lambda: (dialog.set_running(False), dialog.close()) if dialog.winfo_exists() else None)
            except Exception as exc:
                api.log_error(f"Complaint送信エラー: {exc}", exc_info=True)
                api.set_status(f"❌ Complaint送信エラー: {exc}", "error", clear_delay=10)
                api.call_in_ui(lambda: (dialog.set_running(False), dialog.set_status("❌ エラーが発生しました", "#DC2626"))
                               if dialog.winfo_exists() else None)
                api.show_error("エラー", f"Complaint送信の処理中にエラーが発生しました:\n\n{exc}")
            finally:
                finish()

        api.run_in_background(worker, "complaint")

    def open_complaint():
        if api.is_busy(BUSY):
            api.show_warning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。")
            return
        ComplaintDialog(api.parent, api.font_family, submit_complaint)

    def run_parallel():
        login = credentials()
        if login is None or not begin():
            return
        api.set_status("🚀 [並行送信] 受注残(99.7.6.20)＆売上(99.7.5.11)の32prn抽出を開始します...", "working")
        api.log_info(f"並行GAS送信開始 (99.7.6.20 & 99.7.5.11): ユーザー={login[2]}, ホスト={login[0]}")

        def worker():
            # Run the two menus one after another: concurrent 32prn spools collide on the server.
            today = datetime.date.today()
            sales_range = (today.replace(day=1).strftime("%m/%d/%y"), today.strftime("%m/%d/%y"))
            tasks = (
                ("99.7.6.20", "受注残", "OrderBooking", lambda shell, p: extract_order_backlog(shell, p)),
                ("99.7.5.11", "売上", "Sales", lambda shell, p: extract_sales(shell, p, *sales_range)),
            )
            results = {}
            overall = clock()
            try:
                for index, (menu, label, title, procedure) in enumerate(tasks, 1):
                    started = clock()
                    progress = lambda text, label=label, index=index: api.set_status(f"[{index}/2 {label}] {text}", "working")
                    try:
                        progress("🔌 QADサーバーに接続中...")
                        with shell_factory(*login) as shell:
                            procedure(shell, progress)
                            rows, _, _ = receive_rows(shell, progress, "", menu)
                        count = len(rows) - 1
                        elapsed = clock() - started
                        api.log_info(f"並行ワーカー [{menu} {label}]: 抽出完了 {count:,}件 ({elapsed:.1f}秒) ➔ 即時GAS送信")
                        payload = {"menu": menu, "title": title, "sender": login[2],
                                   "exportedAt": datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"), "data": rows}
                        sender(payload, PARALLEL_GAS_URL, title=f"Google Sheets 転送 ({menu} {title})")
                        results[menu] = (label, count, None)
                        api.set_status(f"⚡ [完了速報] {label}({menu}) をGASへ転送完了 ({count:,}件 / {elapsed:.1f}秒)", "working")
                    except Exception as exc:
                        api.log_error(f"データ送信 [{menu}] エラー: {exc}", exc_info=True)
                        results[menu] = (label, 0, str(exc))
                        api.set_status(f"⚠️ [{label} {menu}] エラー: {exc}", "error", clear_delay=8)
                total = clock() - overall
                summary = " & ".join(f"{label}: {'失敗' if error else f'{count:,}件'}" for label, count, error in results.values())
                if any(error for _, _, error in results.values()):
                    api.set_status(f"⚠️ 並行送信完了 (一部エラー): {summary} ({total:.1f}秒)", "error", clear_delay=10)
                else:
                    total_count = sum(count for _, count, _ in results.values())
                    api.set_status(f"🎉 受注残＆売上の送信が完了しました ({summary} / 計{total_count:,}件 / {total:.1f}秒)", "success", clear_delay=8)
                api.log_info(f"並行送信全完了: {summary} (総所要時間: {total:.1f}秒)")
            finally:
                finish()

        api.run_in_background(worker, "parallel")

    commands = {"inventory": run_inventory, "complaint": open_complaint, "parallel": run_parallel}
    current = names()
    for key, _, color, hover in BUTTONS:
        handles[key] = api.add_button(key, current[key], commands[key], bar="data", color=color,
                                      hover_color=hover, on_right_click=lambda event, k=key: context_menu(event, k))
        api.register_action(f"data_transmission.{key}", commands[key])
    api.add_view_menu_command("📤 データ送信ボタン名の設定...", open_names)
