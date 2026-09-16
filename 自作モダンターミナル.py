import os
from pathlib import Path
import queue
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


# 業務画面の可読性を優先した青系のダークテーマ。
COLORS = {
    "background": "#101522", "panel": "#192234", "terminal": "#0B101A",
    "button": "#293751", "hover": "#394D70", "accent": "#536BCC",
    "accent_hover": "#627CDE", "focus": "#A9BCFF", "text": "#EDF2FF",
    "muted": "#B4C0D6", "success": "#80DDB6", "warning": "#FFD38A",
    "error": "#FFAAA8", "border": "#435473", "cursor": "#405186",
}


class TerminalApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("QAD / MFG:PRO — Modern Terminal")
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
        self.font_size = 14
        self.key_buttons = []
        self._build_menu()
        self._build_header()
        self._build_terminal()
        self._build_toolbar()
        self._set_state("未接続")
        self._show_message("QAD / MFG:PRO\n\n上部の「ログイン / 接続」から開始してください。\n"
                           "右のツールバー、またはキーボードから操作できます。")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_job = self.after(33, self._poll)

    def _button(self, parent, text, command, primary=False):
        # Native buttons support Tab traversal, Space activation and focus rings.
        color = COLORS["accent"] if primary else COLORS["button"]
        return tk.Button(
            parent, text=text, command=command, font=("Yu Gothic UI", 10, "bold"),
            bg=color, fg=COLORS["text"], activebackground=COLORS["accent_hover"]
            if primary else COLORS["hover"], activeforeground=COLORS["text"],
            disabledforeground=COLORS["muted"], relief="flat", bd=0,
            highlightthickness=2, highlightbackground=COLORS["panel"],
            highlightcolor=COLORS["focus"], cursor="hand2", takefocus=True,
            padx=10, pady=8,
        )

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
        view.add_command(label="ターミナルにフォーカス", command=self.focus_terminal)
        menubar.add_cascade(label="表示", menu=view)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作ガイド", command=self.show_help)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        self.configure(menu=menubar)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="QAD / MFG:PRO", text_color=COLORS["text"],
                     font=ctk.CTkFont(family="Yu Gothic UI", size=22, weight="bold")).grid(
                         row=0, column=0, padx=(20, 16), pady=(14, 0), sticky="w")
        ctk.CTkLabel(header, text=f"{HOST}  /  {USER}", text_color=COLORS["muted"],
                     font=ctk.CTkFont(family="Yu Gothic UI", size=13)).grid(
                         row=1, column=0, padx=20, pady=(0, 14), sticky="w")
        self.status_label = ctk.CTkLabel(header, text="未接続", font=ctk.CTkFont(family="Yu Gothic UI", size=14))
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=16)
        self.connect_btn = self._button(header, "ログイン / 接続", self.connect_to_server, True)
        self.connect_btn.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=16)
        self.disconnect_btn = self._button(header, "切断", self.disconnect_server)
        self.disconnect_btn.grid(row=0, column=3, rowspan=2, padx=(0, 20), pady=16)

    def _build_terminal(self):
        panel = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=12)
        panel.grid(row=1, column=0, padx=(16, 8), pady=16, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(panel, text="TERMINAL", text_color=COLORS["muted"],
                     font=ctk.CTkFont(family="Yu Gothic UI", size=12, weight="bold")).grid(
                         row=0, column=0, padx=16, pady=(8, 4), sticky="w")
        self.terminal_font = ctk.CTkFont(family="ＭＳ ゴシック", size=self.font_size)
        self.textbox = ctk.CTkTextbox(
            panel, font=self.terminal_font, fg_color=COLORS["terminal"],
            text_color=COLORS["text"], wrap="none", corner_radius=8,
            border_width=2, border_color=COLORS["border"],
        )
        self.textbox.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.textbox.tag_config("remote_cursor", background=COLORS["cursor"])
        self.textbox.bind("<Key>", self.on_key_press)
        self.textbox.bind("<FocusIn>", lambda event: self.textbox.configure(border_color=COLORS["focus"]))
        self.textbox.bind("<FocusOut>", lambda event: self.textbox.configure(border_color=COLORS["border"]))
        # Local widget edits must never masquerade as received server output.
        self.textbox.bind("<<Paste>>", lambda event: "break")
        self.textbox.bind("<<Cut>>", lambda event: "break")
        self.footer = ctk.CTkLabel(panel, text="VT100  ·  132 × 24  ·  CP932",
                                 text_color=COLORS["muted"], font=ctk.CTkFont(family="Yu Gothic UI", size=12))
        self.footer.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="w")

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, width=244, fg_color=COLORS["panel"], corner_radius=12)
        toolbar.grid(row=1, column=1, padx=(0, 16), pady=16, sticky="nsew")
        toolbar.grid_columnconfigure((0, 1), weight=1, uniform="keys")
        ctk.CTkLabel(toolbar, text="キーツールバー", height=24, text_color=COLORS["text"],
                     font=ctk.CTkFont(family="Yu Gothic UI", size=17, weight="bold")).grid(
                         row=0, column=0, columnspan=2, padx=16, pady=(12, 0), sticky="w")
        ctk.CTkLabel(toolbar, text="クリックでキーを送信", height=20, text_color=COLORS["muted"],
                     font=ctk.CTkFont(family="Yu Gothic UI", size=12)).grid(
                         row=1, column=0, columnspan=2, padx=16, sticky="w")
        row = 2
        for title, buttons in TOOLBAR_GROUPS:
            ctk.CTkLabel(toolbar, text=title, height=18, text_color=COLORS["muted"],
                         font=ctk.CTkFont(family="Yu Gothic UI", size=12)).grid(
                             row=row, column=0, columnspan=2, padx=16, pady=(10, 2), sticky="w")
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
        self.textbox.configure(state="disabled")
        self.rendered_lines = [None] * ROWS

    def connect_to_server(self):
        if self.session is not None or self.closing:
            return
        self.session = TerminalSession(HOST, PORT, USER, PASS, self.events)
        self._set_state("接続中…", "warning")
        self._show_message(f"{HOST} に接続しています…")
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
        changed, cursor = snapshot
        # Ignore dirty marks whose visible text is unchanged (e.g. SGR changes).
        changed = {row: line for row, line in changed.items() if self.rendered_lines[row] != line}
        if changed:
            self.textbox.configure(state="normal")
            for row, line in changed.items():
                index = f"{row + 1}.0"
                self.textbox.delete(index, f"{row + 1}.end")
                self.textbox.insert(index, line)
                self.rendered_lines[row] = line
            self.textbox.configure(state="disabled")
        self.textbox.tag_remove("remote_cursor", "1.0", "end")
        if cursor is not None:
            row, column = cursor
            self.textbox.tag_add("remote_cursor", f"{row + 1}.{column}", f"{row + 1}.{column + 1}")

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
            self.footer.configure(text="送信できません：CP932で表現できない文字です。")
        except queue.Full:
            self.bell()
            self.footer.configure(text="送信待ちが多いため、キー入力を一度止めてください。")
        else:
            self.footer.configure(text="VT100  ·  132 × 24  ·  CP932")

    def send_key(self, key):
        self._send(KEY_SEQUENCES[key])
        self.focus_terminal()

    def focus_terminal(self):
        self.textbox.focus_set()

    def change_font_size(self, delta=0, reset=False):
        self.font_size = 14 if reset else max(10, min(24, self.font_size + delta))
        self.terminal_font.configure(size=self.font_size)

    def disconnect_server(self):
        if self.session is None:
            return
        self.session.stop()
        self.session = None
        self.is_connected = False
        self.textbox.tag_remove("remote_cursor", "1.0", "end")
        self._set_state("切断済み")

    def show_help(self):
        messagebox.showinfo(
            "操作ガイド",
            "上部または「接続」メニューからログインします。\n"
            "右ツールバーと「キー送信」メニューは同じキーを送信します。\n"
            "F1〜F4 / Enter / Space / Esc / Ctrl+F / Tab / 矢印キーに対応。\n\n"
            "ターミナル内のTabはQADへ送信されます。\n"
            "Ctrl+Shift+Tabで上部のボタンへフォーカスを移せます。\n"
            "文字サイズは「表示」メニューで変更できます。\n"
            "画面が狭い場合は下部の横スクロールを使用してください。",
            parent=self,
        )

    def on_close(self):
        self.closing = True
        if self.update_job is not None:
            self.after_cancel(self.update_job)
            self.update_job = None
        if self.session is not None:
            self.session.stop()
        self.destroy()


if __name__ == "__main__":
    app = TerminalApp()
    app.mainloop()
