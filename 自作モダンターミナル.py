import os
from pathlib import Path
import queue
import re
import sys

# Explorerの関連付けは通常、ライブラリ未導入の標準Pythonを使用する。
# このプロジェクトの仮想環境があれば、GUIのimportより先に切り替える。
if __name__ == "__main__":
    app_path = Path(__file__).resolve()
    local_env = app_path.parent / ".venv"
    local_python = local_env / "Scripts" / "pythonw.exe"
    if local_python.is_file() and Path(sys.prefix).resolve() != local_env.resolve():
        os.execv(str(local_python), [str(local_python), str(app_path), *sys.argv[1:]])

import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
    from terminal_core import COLS, ROWS, KEY_SEQUENCES, TOOLBAR_GROUPS, TerminalSession, key_sequence
except ImportError as exc:
    if __name__ != "__main__":
        raise
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "起動に必要なファイル・ライブラリがありません",
        f"{exc}\n\nREADME.mdの導入手順を確認してください。\n"
        "terminal_core.pyはこのファイルと同じフォルダに置いてください。\n\n"
        f"使用中のPython: {sys.executable}",
        parent=root,
    )
    root.destroy()
    raise SystemExit(1)


# サーバー情報
HOST = "mfg03"
PORT = 22
USER = "takehik"
PASS = "nhy7mju8"


# 薄いグレーを基調とした落ち着いたモダンターミナル配色
COLORS = {
    "background": "#F1F5F9", "panel": "#F8FAFC", "terminal": "#E2E8F0",
    "button": "#E2E8F0", "hover": "#CBD5E1", "accent": "#356BC4",
    "accent_hover": "#285BAF", "focus": "#6187C7", "text": "#0F172A",
    "muted": "#64748B", "success": "#16A34A", "warning": "#D97706",
    "error": "#DC2626", "border": "#CBD5E1", "cursor": "#3B82F6",
    "on_accent": "#FFFFFF", "disabled": "#94A3B8", "disabled_bg": "#E2E8F0",
    "scrollbar": "#CBD5E1", "scrollbar_hover": "#94A3B8",
}


# --- フォント設定 ---
# システムにインストールされているフォントから優先順に自動選択します。
# （ヒラギノ角ゴシックを優先。Windows標準ではモダンなYu Gothic UI / BIZ UDゴシック等にフォールバック）
PREFERRED_UI_FONTS = (
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "ヒラギノ角ゴシック",
    "Hiragino Kaku Gothic Pro",
    "Yu Gothic UI",
    "游ゴシック",
    "Segoe UI",
    "sans-serif",
)

PREFERRED_TERMINAL_FONTS = (
    "Cascadia Mono",  # Windows 11/10標準 ターミナル等幅（罫線・英数・半角カナの幅が完全一致）
    "Cascadia Code",
    "Consolas",       # Windows標準 等幅（罫線と英数の幅が完全一致）
    "Courier New",
    "Source Code Pro",
    "BIZ UDゴシック",
    "MS Gothic",
    "ＭＳ ゴシック",
    "monospace",
)


def find_first_available_font(candidates, fallback="sans-serif"):
    """利用可能なフォントファミリから最初に見つかったものを返す"""
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families())
        for f in candidates:
            if f in available:
                return f
    except Exception:
        pass
    return candidates[0] if candidates else fallback


class ActionButton(ctk.CTkFrame):
    """Rounded surface with native button activation and keyboard traversal."""

    def __init__(self, parent, text, command, primary=False, font_family="Yu Gothic UI"):
        self.primary = primary
        self.surface = COLORS["accent"] if primary else COLORS["button"]
        super().__init__(parent, fg_color=self.surface, corner_radius=11,
                         border_width=2, border_color=self.surface)
        self.grid_columnconfigure(0, weight=1)
        self._control = tk.Button(
            self, text=text, command=command, font=(font_family, 10),
            bg=self.surface, fg=COLORS["on_accent"] if primary else COLORS["text"],
            activebackground=COLORS["accent_hover"] if primary else COLORS["hover"],
            activeforeground=COLORS["on_accent"] if primary else COLORS["text"],
            disabledforeground=COLORS["disabled"], relief="flat", bd=0,
            highlightthickness=0, cursor="hand2", takefocus=True, padx=4, pady=6,
        )
        self._control.grid(row=0, column=0, padx=9, pady=4, sticky="ew")
        self._control.bind("<FocusIn>", lambda event: super(ActionButton, self).configure(border_color=COLORS["focus"]))
        self._control.bind("<FocusOut>", lambda event: super(ActionButton, self).configure(border_color=self.surface))
        self._control.bind("<Enter>", lambda event: self._hover(True))
        self._control.bind("<Leave>", lambda event: self._hover(False))

    def _hover(self, entered):
        if self._control.cget("state") == "disabled":
            return
        color = COLORS["accent_hover" if self.primary else "hover"] if entered else self.surface
        super().configure(fg_color=color)
        self._control.configure(bg=color)

    def configure(self, require_redraw=False, **kwargs):
        state = kwargs.pop("state", None)
        super().configure(require_redraw=require_redraw, **kwargs)
        if state is not None:
            enabled = state != "disabled"
            self.surface = COLORS["accent" if self.primary else "button"] if enabled else COLORS["disabled_bg"]
            self._control.configure(state=state, bg=self.surface, takefocus=enabled,
                                    cursor="hand2" if enabled else "arrow")
            super().configure(fg_color=self.surface, border_color=self.surface)

    def cget(self, name):
        if name in ("state", "text"):
            return self._control.cget(name)
        return super().cget(name)

    def focus_set(self):
        self._control.focus_set()

    def invoke(self):
        return self._control.invoke()


class TerminalApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.ui_font_family = find_first_available_font(PREFERRED_UI_FONTS, fallback="Yu Gothic UI")
        self.terminal_font_family = find_first_available_font(PREFERRED_TERMINAL_FONTS, fallback="BIZ UDゴシック")

        self.title("QAD / MFG:PRO")
        self.geometry("1460x780")
        self.minsize(1020, 660)
        self.configure(fg_color=COLORS["background"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.session = None
        self.events = queue.Queue()
        self.is_connected = False
        self.closing = False
        self.rendered_lines = [None] * ROWS
        self.raw_lines = {}
        self.font_size = 14
        self.auto_fit = True
        self._resize_job = None
        self.key_buttons = []
        self._build_menu()
        self._build_header()
        self._build_terminal()
        self._build_toolbar()
        self._set_state("未接続")
        self._show_message("")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_job = self.after(33, self._poll)
        self.after(100, self._apply_auto_fit)

    def _button(self, parent, text, command, primary=False):
        return ActionButton(parent, text, command, primary, font_family=self.ui_font_family)

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.connection_menu = tk.Menu(menubar, tearoff=False)
        self.connection_menu.add_command(label="ログイン / 接続", command=self.connect_to_server)
        self.connection_menu.add_command(label="切断", command=self.disconnect_server)
        self.connection_menu.add_separator()
        self.connection_menu.add_command(label="終了", command=self.on_close)
        menubar.add_cascade(label="接続", menu=self.connection_menu)

        self.key_menu = tk.Menu(menubar, tearoff=False)
        for index, (_, buttons) in enumerate(TOOLBAR_GROUPS):
            if index:
                self.key_menu.add_separator()
            for label, key in buttons:
                self.key_menu.add_command(label=label, command=lambda k=key: self.send_key(k))
        menubar.add_cascade(label="キー送信", menu=self.key_menu)
        view = tk.Menu(menubar, tearoff=False)
        view.add_command(label="文字を大きく", command=lambda: self.change_font_size(1))
        view.add_command(label="文字を小さく", command=lambda: self.change_font_size(-1))
        view.add_command(label="標準サイズ", command=lambda: self.change_font_size(reset=True))
        view.add_separator()
        self.auto_fit_var = tk.BooleanVar(value=True)
        view.add_checkbutton(label="画面サイズに自動調整 (Auto Fit)", variable=self.auto_fit_var, command=self.toggle_auto_fit)
        view.add_separator()
        view.add_command(label="ターミナルにフォーカス", command=self.focus_terminal)
        menubar.add_cascade(label="表示", menu=view)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作ガイド", command=self.show_help)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        self.configure(menu=menubar)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["background"], corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(header, text="未接続", font=ctk.CTkFont(family=self.ui_font_family, size=14))
        self.status_label.grid(row=0, column=0, sticky="w", padx=24, pady=(14, 0))
        self.connect_btn = self._button(header, "ログイン", self.connect_to_server, True)
        self.connect_btn.grid(row=0, column=1, padx=(0, 8), pady=(14, 0))
        self.disconnect_btn = self._button(header, "切断", self.disconnect_server)
        self.disconnect_btn.grid(row=0, column=2, padx=(0, 20), pady=(14, 0))

    def _build_terminal(self):
        panel = ctk.CTkFrame(self, fg_color=COLORS["background"], corner_radius=0)
        panel.grid(row=1, column=0, padx=(8, 4), pady=(4, 4), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        self.font_size = 17
        self.active_cols = 80
        self.terminal_font = ctk.CTkFont(family=self.terminal_font_family, size=self.font_size)
        self.textbox = ctk.CTkTextbox(
            panel, font=self.terminal_font, fg_color=COLORS["terminal"],
            text_color=COLORS["text"], wrap="none", corner_radius=12,
            border_width=1, border_color=COLORS["border"],
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")
        # 罫線の縦線が上下で隙間なく完全に繋がるよう行間パディングを0に設定
        self.textbox._textbox.configure(spacing1=0, spacing2=0, spacing3=0)
        self.textbox.tag_config("remote_cursor", background=COLORS["cursor"])
        # 暗転（反転表示）: 薄いグレー背景の中で黒く引き締まる完全な暗転表示
        self.textbox.tag_config("reverse", background="#0F172A", foreground="#F8FAFC")
        # メニュー入力連動ハイライト: 入力番号に対応する項目を即時暗転
        self.textbox.tag_config("menu_highlight", background="#0F172A", foreground="#F8FAFC")
        # 下線 (SGR 4)
        self.textbox.tag_config("underline", underline=True)
        # 太字 (SGR 1)
        try:
            self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
        except Exception:
            self.textbox.tag_config("bold", foreground=COLORS["accent"])
        self.textbox.bind("<Key>", self.on_key_press)
        self.textbox.bind("<FocusIn>", lambda event: self.textbox.configure(border_color=COLORS["focus"]))
        self.textbox.bind("<FocusOut>", lambda event: self.textbox.configure(border_color=COLORS["border"]))
        # Local widget edits must never masquerade as received server output.
        self.textbox.bind("<<Paste>>", lambda event: "break")
        self.textbox.bind("<<Cut>>", lambda event: "break")
        self.footer = ctk.CTkLabel(panel, text="", text_color=COLORS["error"],
                                 font=ctk.CTkFont(family=self.ui_font_family, size=12))
        self.footer.grid(row=1, column=0, padx=8, pady=(6, 0), sticky="w")
        self.footer.grid_remove()
        panel.bind("<Configure>", self._on_panel_resize)

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, width=210, fg_color=COLORS["panel"], corner_radius=14,
                              border_width=1, border_color=COLORS["border"])
        toolbar.grid(row=1, column=1, padx=(0, 8), pady=(4, 4), sticky="new")
        toolbar.grid_columnconfigure((0, 1), weight=1, uniform="keys")
        row = 0
        for _, buttons in TOOLBAR_GROUPS:
            toolbar.grid_rowconfigure(row, minsize=16)
            row += 1
            for index, (label, key) in enumerate(buttons):
                button = self._button(toolbar, label, lambda k=key: self.send_key(k), key == "F1")
                button.grid(row=row + index // 2, column=index % 2,
                            padx=(12, 4) if index % 2 == 0 else (4, 12), pady=4, sticky="ew")
                self.key_buttons.append(button)
            row += (len(buttons) + 1) // 2
        toolbar.grid_rowconfigure(row, weight=1, minsize=12)

    def _set_state(self, text, color="muted"):
        self.status_label.configure(text=text, text_color=COLORS[color])
        idle = self.session is None
        self.connect_btn.configure(state="normal" if idle else "disabled")
        self.disconnect_btn.configure(state="disabled" if idle else "normal")
        self.connection_menu.entryconfigure(0, state="normal" if idle else "disabled")
        self.connection_menu.entryconfigure(1, state="disabled" if idle else "normal")
        state = "normal" if self.is_connected else "disabled"
        for button in self.key_buttons:
            button.configure(state=state)
        for index in range(self.key_menu.index("end") + 1):
            if self.key_menu.type(index) == "command":
                self.key_menu.entryconfigure(index, state=state)

    def _show_message(self, message):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", message)
        for tag in ("reverse", "menu_highlight", "underline", "bold", "remote_cursor"):
            self.textbox.tag_remove(tag, "1.0", "end")
        self.textbox.configure(state="disabled")
        self.rendered_lines = [None] * ROWS
        self.raw_lines = {}

    def connect_to_server(self):
        if self.session is not None or self.closing:
            return
        self.session = TerminalSession(HOST, PORT, USER, PASS, self.events)
        self._set_state("接続中…", "warning")
        self._show_message("")
        self._show_input_error("")
        self.session.start()

    def _poll(self):
        if self.closing:
            return
        while True:
            try:
                session, event, error = self.events.get_nowait()
            except queue.Empty:
                break
            if session is not self.session:
                continue  # Ignore an old connection completing after reconnect.
            if event == "connected":
                self.is_connected = True
                self._show_message("\n".join([" " * COLS] * ROWS))
                self._set_state("接続済み", "success")
                self.focus_terminal()
            elif event == "closed":
                if self.is_connected:
                    self._update_screen()
                self.session = None
                self.is_connected = False
                self._set_state("接続エラー" if error else "切断済み", "error" if error else "muted")
                if error:
                    messagebox.showerror("SSH接続エラー", error, parent=self)
        if self.is_connected:
            self._update_screen()
        self.update_job = self.after(33, self._poll)

    def _update_screen(self):
        snapshot = self.session.snapshot()
        if snapshot is None:
            return
        changed, cursor, active_cols = snapshot
        if getattr(self, "active_cols", 80) != active_cols:
            self.active_cols = active_cols
            if self.auto_fit:
                self._apply_auto_fit()
        # テキストまたはスタイル属性に変更がある行を抽出
        changed = {row: data for row, data in changed.items() if self.raw_lines.get(row) != data}
        if changed:
            self.textbox.configure(state="normal")
            for row, (raw_line, spans) in changed.items():
                # 罫線を含む行のピクセル幅アライメント
                line = self._align_border_line(raw_line)
                start_idx = f"{row + 1}.0"
                end_idx = f"{row + 1}.end"
                self.textbox.delete(start_idx, end_idx)
                self.textbox.insert(start_idx, line)
                # 既存の行スタイルタグをクリア
                for tag in ("reverse", "underline", "bold"):
                    self.textbox.tag_remove(tag, start_idx, end_idx)
                # スタイル属性を適用
                for s_idx, e_idx, tags in spans:
                    for tag in tags:
                        self.textbox.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
                self.rendered_lines[row] = (line, spans)
                self.raw_lines[row] = (raw_line, spans)

            # メニュー入力連動ハイライト（入力欄の番号に対応するメニュー項目を自動暗転）
            self._apply_menu_highlight()
            self.textbox.configure(state="disabled")

        self.textbox.tag_remove("remote_cursor", "1.0", "end")
        if cursor is not None:
            row, column = cursor
            self.textbox.tag_add("remote_cursor", f"{row + 1}.{column}", f"{row + 1}.{column + 1}")

    def _align_border_line(self, line):
        """半角カナ・漢字を含む罫線行のピクセル幅を、純ASCII罫線行と揃える。

        QADはVT100の80桁画面で罫線を描画するが、Cascadia Mono等のフォントでは
        半角カナ(ｱ=13px)や漢字(株=21px)がASCII(A=12px)と1:1/1:2にならないため、
        同じ「表示幅80列」の行でもピクセル幅にズレが生じる。
        右端の罫線文字(┐/┘/│)の直前にパディング文字を動的に挿入して幅を一致させる。
        """
        # 罫線の右端文字を含む行のみ対象
        border_right = {"┐", "┘", "│"}
        if not line or line[-1] not in border_right:
            return line
        # 基準幅: 全てASCII + 罫線文字のみの80列行（例: ┌─...─┐）
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(font=self.textbox._textbox.cget("font"))
        except Exception:
            return line
        ref_width = f.measure("M") * self.active_cols
        line_width = f.measure(line)
        if line_width >= ref_width:
            return line
        # 水平枠線（┌/└で始まる行）は「─」、縦枠線（│で始まる行）は空白で補間
        pad_char = "─" if line and line[0] in {"┌", "└"} else " "
        pad_w = f.measure(pad_char)
        if pad_w <= 0:
            return line
        pad_count = round((ref_width - line_width) / pad_w)
        if pad_count <= 0:
            return line
        # 右端の罫線文字の直前に挿入
        return line[:-1] + (pad_char * pad_count) + line[-1]

    def _rerender_all(self):
        """フォントサイズ変更時等に全行を新しいフォントメトリクスで再アライメント・再描画する"""
        if not getattr(self, "raw_lines", None):
            return
        self.textbox.configure(state="normal")
        for row, (raw_line, spans) in self.raw_lines.items():
            line = self._align_border_line(raw_line)
            start_idx = f"{row + 1}.0"
            end_idx = f"{row + 1}.end"
            self.textbox.delete(start_idx, end_idx)
            self.textbox.insert(start_idx, line)
            for tag in ("reverse", "underline", "bold"):
                self.textbox.tag_remove(tag, start_idx, end_idx)
            for s_idx, e_idx, tags in spans:
                for tag in tags:
                    self.textbox.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
            self.rendered_lines[row] = (line, spans)
        self._apply_menu_highlight()
        self.textbox.configure(state="disabled")

    def _apply_menu_highlight(self):
        """メニュー選択プロンプトの入力番号に対応するメニュー項目を検知して暗転（ハイライト）する"""
        self.textbox.tag_remove("menu_highlight", "1.0", "end")
        input_num = None
        for row in range(ROWS):
            line_data = self.rendered_lines[row]
            if not line_data:
                continue
            line = line_data[0]
            # 'Please select a function' または 'Selection:' 行の入力値を検出
            m = re.search(r'(?:Please select a function.*?(?:EXIT|\b)|Selection:)\s+([0-9]+)', line)
            if m:
                input_num = m.group(1)
                break

        if not input_num:
            return

        pattern = re.compile(rf'(?<!\d){input_num}\.\s*([^│]+?)(?=\s{{2,}}\d+\.|\s*│|\Z)')
        for row in range(ROWS):
            line_data = self.rendered_lines[row]
            if not line_data:
                continue
            line = line_data[0]
            for m in pattern.finditer(line):
                self.textbox.tag_add("menu_highlight", f"{row + 1}.{m.start()}", f"{row + 1}.{m.end()}")

    def on_key_press(self, event):
        # Ctrl+Shift+Tab releases terminal focus; plain Tab is sent to QAD.
        if event.state & 0x5 == 0x5 and event.keysym in ("Tab", "ISO_Left_Tab"):
            self.connect_btn.focus_set() if self.session is None else self.disconnect_btn.focus_set()
            return "break"
        if self.is_connected:
            self._send(key_sequence(event.keysym, event.char, event.state))
        return "break"

    def _send(self, data):
        if not data or not self.is_connected or self.session is None:
            return
        try:
            self.session.send(data)
        except UnicodeEncodeError:
            self.bell()
            self._show_input_error("送信できません：CP932で表現できない文字です。")
        except queue.Full:
            self.bell()
            self._show_input_error("送信待ちが多いため、キー入力を一度止めてください。")
        else:
            self._show_input_error("")

    def _show_input_error(self, message):
        self.footer.configure(text=message)
        if message:
            self.footer.grid()
        else:
            self.footer.grid_remove()

    def send_key(self, key):
        self._send(KEY_SEQUENCES[key])
        self.focus_terminal()

    def focus_terminal(self):
        self.textbox.focus_set()

    def _on_panel_resize(self, event):
        if not self.auto_fit or self.closing:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._apply_auto_fit)

    def _apply_auto_fit(self):
        self._resize_job = None
        if not self.auto_fit or self.closing:
            return
        w = self.textbox._textbox.winfo_width()
        h = self.textbox._textbox.winfo_height()
        if w <= 100 or h <= 100:
            w = self.textbox.winfo_width()
            h = self.textbox.winfo_height()
            if w <= 100 or h <= 100:
                return

        import tkinter.font as tkfont
        target_cols = getattr(self, "active_cols", 80)
        target_rows = ROWS

        best_size = 12
        # CTkFont は内部で size=-N（ピクセル指定）に変換するため、
        # 測定もピクセル指定（負の数）で行い、実際の描画サイズと一致させる
        for size in range(36, 11, -1):
            f = tkfont.Font(family=self.terminal_font_family, size=-size)
            char_w = f.measure("M")
            char_h = f.metrics("linespace")
            needed_w = char_w * target_cols + 4
            needed_h = char_h * target_rows + 4
            if needed_w <= w and needed_h <= h:
                best_size = size
                break

        if best_size != self.font_size:
            self.font_size = best_size
            self.terminal_font.configure(size=self.font_size)
            try:
                self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
            except Exception:
                pass
            self._rerender_all()

    def toggle_auto_fit(self):
        self.auto_fit = self.auto_fit_var.get()
        if self.auto_fit:
            self._apply_auto_fit()

    def change_font_size(self, delta=0, reset=False):
        if self.auto_fit:
            self.auto_fit = False
            self.auto_fit_var.set(False)
        self.font_size = 14 if reset else max(10, min(36, self.font_size + delta))
        self.terminal_font.configure(size=self.font_size)
        try:
            self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
        except Exception:
            pass
        self._rerender_all()

    def disconnect_server(self):
        if self.session is None:
            return
        self.session.stop()
        self.session = None
        self.is_connected = False
        for tag in ("remote_cursor", "reverse", "menu_highlight", "underline", "bold"):
            self.textbox.tag_remove(tag, "1.0", "end")
        self._set_state("切断済み")

    def show_help(self):
        messagebox.showinfo(
            "操作ガイド",
            "上部または「接続」メニューからログインします。\n"
            "右ツールバーと「キー送信」メニューは同じキーを送信します。\n"
            "F1〜F4 / Enter / Space / Esc / Ctrl+F / Tab / 矢印キーに対応。\n\n"
            "ターミナル内のTabはQADへ送信されます。\n"
            "Ctrl+Shift+Tabで上部のボタンへフォーカスを移せます。\n"
            "文字サイズはウィンドウに合わせて自動調整されます（「表示」メニューで切替可能）。\n"
            "画面が狭い場合は下部の横スクロールを使用してください。",
            parent=self,
        )

    def on_close(self):
        self.closing = True
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        if self.update_job is not None:
            self.after_cancel(self.update_job)
            self.update_job = None
        if self.session is not None:
            self.session.stop()
        self.destroy()


if __name__ == "__main__":
    app = TerminalApp()
    app.mainloop()
