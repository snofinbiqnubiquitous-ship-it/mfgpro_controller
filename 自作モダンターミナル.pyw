import base64
import json
import os
from pathlib import Path
import queue
import re
import sys

# Explorerの関連付けは通常、ライブラリ未導入の標準Pythonを使用する。
# このプロジェクトの仮想環境があれば、GUIのimportより先に切り替える（pythonwを優先）。
if __name__ == "__main__":
    app_path = Path(__file__).resolve()
    local_env = app_path.parent / ".venv"
    local_python = local_env / "Scripts" / "pythonw.exe"
    if not local_python.is_file():
        local_python = local_env / "Scripts" / "python.exe"
    if local_python.is_file() and Path(sys.prefix).resolve() != local_env.resolve():
        os.execv(str(local_python), [str(local_python), str(app_path), *sys.argv[1:]])

import tkinter as tk
from tkinter import colorchooser, messagebox

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


# --- 設定管理 (terminal_config.json) ---
CONFIG_FILE = Path(__file__).resolve().parent / "terminal_config.json"

DEFAULT_CONFIG = {
    "host": "mfg03",
    "port": 22,
    "user": "takehik",
    "pass_b64": base64.b64encode(b"nhy7mju8").decode("ascii"),
    "theme": "light",
    "custom_terminal_bg": None,
    "custom_terminal_fg": None,
    "enable_windows_shortcuts": True,
    "shortcuts": [
        {"name": "在庫スナップショット", "code": "99.3.6.1"},
        {"name": "在庫移動明細", "code": "99.3.21.4"},
    ],
}


def load_config():
    """設定ファイルを読み込み、存在しない場合はデフォルト値を返す"""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    if "shortcuts" not in cfg or not isinstance(cfg["shortcuts"], list):
        cfg["shortcuts"] = list(DEFAULT_CONFIG["shortcuts"])
    if "enable_windows_shortcuts" not in cfg:
        cfg["enable_windows_shortcuts"] = True
    return cfg


def save_config(cfg):
    """設定ファイルに書き込む"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"設定保存エラー: {exc}", file=sys.stderr)


# --- カラーテーマ定義 ---
COLOR_THEMES = {
    "light": {
        "name": "ライト（標準グレー）",
        "appearance_mode": "light",
        "background": "#F1F5F9",
        "panel": "#F8FAFC",
        "terminal": "#E2E8F0",
        "button": "#E2E8F0",
        "hover": "#CBD5E1",
        "accent": "#356BC4",
        "accent_hover": "#285BAF",
        "focus": "#6187C7",
        "text": "#0F172A",
        "muted": "#64748B",
        "success": "#16A34A",
        "warning": "#D97706",
        "error": "#DC2626",
        "border": "#CBD5E1",
        "cursor": "#3B82F6",
        "on_accent": "#FFFFFF",
        "disabled": "#94A3B8",
        "disabled_bg": "#E2E8F0",
        "scrollbar": "#CBD5E1",
        "scrollbar_hover": "#94A3B8",
        "reverse_bg": "#0F172A",
        "reverse_fg": "#F8FAFC",
        "menu_highlight_bg": "#0F172A",
        "menu_highlight_fg": "#F8FAFC",
    },
    "dark": {
        "name": "ダークスレート",
        "appearance_mode": "dark",
        "background": "#0F172A",
        "panel": "#1E293B",
        "terminal": "#1E293B",
        "button": "#334155",
        "hover": "#475569",
        "accent": "#38BDF8",
        "accent_hover": "#0EA5E9",
        "focus": "#38BDF8",
        "text": "#F8FAFC",
        "muted": "#94A3B8",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "border": "#334155",
        "cursor": "#38BDF8",
        "on_accent": "#0F172A",
        "disabled": "#64748B",
        "disabled_bg": "#1E293B",
        "scrollbar": "#334155",
        "scrollbar_hover": "#475569",
        "reverse_bg": "#F8FAFC",
        "reverse_fg": "#0F172A",
        "menu_highlight_bg": "#38BDF8",
        "menu_highlight_fg": "#0F172A",
    },
    "classic_green": {
        "name": "クラシックグリーン (VT100)",
        "appearance_mode": "dark",
        "background": "#050806",
        "panel": "#0D1310",
        "terminal": "#0A0F0D",
        "button": "#1A2E22",
        "hover": "#254232",
        "accent": "#00FF66",
        "accent_hover": "#00DD55",
        "focus": "#00FF66",
        "text": "#00FF66",
        "muted": "#4B7A5E",
        "success": "#00FF66",
        "warning": "#FFD700",
        "error": "#FF4444",
        "border": "#1A2E22",
        "cursor": "#00FF66",
        "on_accent": "#050806",
        "disabled": "#2E4D3B",
        "disabled_bg": "#0D1310",
        "scrollbar": "#1A2E22",
        "scrollbar_hover": "#254232",
        "reverse_bg": "#00FF66",
        "reverse_fg": "#050806",
        "menu_highlight_bg": "#00FF66",
        "menu_highlight_fg": "#050806",
    },
    "amber": {
        "name": "アンバー（琥珀色）",
        "appearance_mode": "dark",
        "background": "#0D0A05",
        "panel": "#1A140A",
        "terminal": "#120E07",
        "button": "#2E200F",
        "hover": "#422E16",
        "accent": "#FFB000",
        "accent_hover": "#E69E00",
        "focus": "#FFB000",
        "text": "#FFB000",
        "muted": "#8C6A38",
        "success": "#FFB000",
        "warning": "#FFD700",
        "error": "#FF4444",
        "border": "#2E200F",
        "cursor": "#FFB000",
        "on_accent": "#0D0A05",
        "disabled": "#422E16",
        "disabled_bg": "#1A140A",
        "scrollbar": "#2E200F",
        "scrollbar_hover": "#422E16",
        "reverse_bg": "#FFB000",
        "reverse_fg": "#0D0A05",
        "menu_highlight_bg": "#FFB000",
        "menu_highlight_fg": "#0D0A05",
    },
}

# パレット用の代表的なプリセットカラー（タイル選択用）
PALETTE_BG_PRESETS = [
    ("#E2E8F0", "薄グレー"),
    ("#F8FAFC", "オフホワイト"),
    ("#FFFFFF", "ピュアホワイト"),
    ("#1E293B", "スレートダーク"),
    ("#0F172A", "ミッドナイト"),
    ("#0A0F0D", "漆黒 (グリーン用)"),
    ("#120E07", "ダークアンバー"),
    ("#18181B", "チャコール"),
]

PALETTE_FG_PRESETS = [
    ("#0F172A", "ダークネイビー"),
    ("#1E293B", "スレート"),
    ("#000000", "ブラック"),
    ("#F8FAFC", "オフホワイト"),
    ("#00FF66", "蛍光グリーン"),
    ("#38BDF8", "シアン"),
    ("#FFB000", "アンバー"),
    ("#FBBF24", "ゴールド"),
]


# --- フォント設定 ---
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
    "Consolas",       # Windows標準 等幅（罫線の上下隙間ゼロ・完全シームレス結合）
    "Cascadia Mono",  # Windows 11/10標準 等幅
    "Cascadia Code",
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
    """角丸サーフェスとネイティブボタントラバーサルを備えたアクションボタン"""

    def __init__(self, parent, text, command, primary=False, font_family="Yu Gothic UI", colors=None):
        self.primary = primary
        self.colors = colors or COLOR_THEMES["light"]
        self.surface = self.colors["accent"] if primary else self.colors["button"]
        super().__init__(parent, fg_color=self.surface, corner_radius=11,
                         border_width=2, border_color=self.surface)
        self.grid_columnconfigure(0, weight=1)
        self._control = tk.Button(
            self, text=text, command=command, font=(font_family, 10),
            bg=self.surface, fg=self.colors["on_accent"] if primary else self.colors["text"],
            activebackground=self.colors["accent_hover"] if primary else self.colors["hover"],
            activeforeground=self.colors["on_accent"] if primary else self.colors["text"],
            disabledforeground=self.colors["disabled"], relief="flat", bd=0,
            highlightthickness=0, cursor="hand2", takefocus=True, padx=4, pady=6,
        )
        self._control.grid(row=0, column=0, padx=9, pady=4, sticky="ew")
        self._control.bind("<FocusIn>", lambda event: super(ActionButton, self).configure(border_color=self.colors["focus"]))
        self._control.bind("<FocusOut>", lambda event: super(ActionButton, self).configure(border_color=self.surface))
        self._control.bind("<Enter>", lambda event: self._hover(True))
        self._control.bind("<Leave>", lambda event: self._hover(False))

    def update_colors(self, colors):
        self.colors = colors
        self.surface = self.colors["accent"] if self.primary else self.colors["button"]
        self.configure(fg_color=self.surface, border_color=self.surface)
        self._control.configure(
            bg=self.surface,
            fg=self.colors["on_accent"] if self.primary else self.colors["text"],
            activebackground=self.colors["accent_hover"] if self.primary else self.colors["hover"],
            activeforeground=self.colors["on_accent"] if self.primary else self.colors["text"],
            disabledforeground=self.colors["disabled"],
        )

    def _hover(self, entered):
        if self._control.cget("state") == "disabled":
            return
        color = self.colors["accent_hover" if self.primary else "hover"] if entered else self.surface
        super().configure(fg_color=color)
        self._control.configure(bg=color)

    def configure(self, require_redraw=False, **kwargs):
        state = kwargs.pop("state", None)
        super().configure(require_redraw=require_redraw, **kwargs)
        if state is not None:
            enabled = state != "disabled"
            self.surface = self.colors["accent" if self.primary else "button"] if enabled else self.colors["disabled_bg"]
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


class ColorPaletteDialog(ctk.CTkToplevel):
    """グラフィカルなカラーパレット設定ウィンドウ"""

    def __init__(self, parent, terminal_app):
        super().__init__(parent)
        self.app = terminal_app

        self.title("カラーパレット設定")
        self.geometry("540x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 540) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(main_frame, text="🎨 カラーパレット & テーマ設定", font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(10, 12))

        # 1. プリセットテーマ
        theme_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        theme_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(theme_frame, text="標準テーマテンプレート:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 6))

        t_grid = ctk.CTkFrame(theme_frame, fg_color="transparent")
        t_grid.pack(fill="x")
        t_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        themes = [
            ("ライト (標準)", "light", "#E2E8F0", "#0F172A"),
            ("ダークスレート", "dark", "#1E293B", "#F8FAFC"),
            ("グリーン (VT100)", "classic_green", "#0A0F0D", "#00FF66"),
            ("アンバー (琥珀)", "amber", "#120E07", "#FFB000"),
        ]
        for idx, (label, key, bg, fg) in enumerate(themes):
            btn = ctk.CTkButton(
                t_grid, text=label, fg_color=bg, text_color=fg,
                border_width=1, border_color="#64748B", hover_color=bg,
                command=lambda k=key: self._select_theme(k), height=32, font=ctk.CTkFont(size=11, weight="bold")
            )
            btn.grid(row=0, column=idx, padx=4, sticky="ew")

        # 2. ターミナル背景色パレット
        bg_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bg_frame.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(bg_frame, text="ターミナル背景色:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        bg_grid = ctk.CTkFrame(bg_frame, fg_color="transparent")
        bg_grid.pack(fill="x")
        bg_grid.grid_columnconfigure(list(range(len(PALETTE_BG_PRESETS))), weight=1)

        for idx, (color, name) in enumerate(PALETTE_BG_PRESETS):
            btn = ctk.CTkButton(
                bg_grid, text="", fg_color=color, hover_color=color,
                border_width=1, border_color="#64748B", width=34, height=28,
                command=lambda c=color: self._set_bg(c)
            )
            btn.grid(row=0, column=idx, padx=2, sticky="ew")

        # 3. ターミナル文字色パレット
        fg_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        fg_frame.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(fg_frame, text="ターミナル文字色:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        fg_grid = ctk.CTkFrame(fg_frame, fg_color="transparent")
        fg_grid.pack(fill="x")
        fg_grid.grid_columnconfigure(list(range(len(PALETTE_FG_PRESETS))), weight=1)

        for idx, (color, name) in enumerate(PALETTE_FG_PRESETS):
            btn = ctk.CTkButton(
                fg_grid, text="Aa", fg_color="#1E293B", text_color=color, hover_color="#334155",
                border_width=1, border_color="#64748B", width=34, height=28,
                command=lambda c=color: self._set_fg(c), font=ctk.CTkFont(size=11, weight="bold")
            )
            btn.grid(row=0, column=idx, padx=2, sticky="ew")

        # 4. 自由なカラーピッカー
        custom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        custom_frame.pack(fill="x", padx=16, pady=(14, 4))
        custom_frame.grid_columnconfigure((0, 1), weight=1)

        custom_bg_btn = ctk.CTkButton(
            custom_frame, text="🎨 背景色を自由に選ぶ...", fg_color="#356BC4", hover_color="#285BAF",
            command=self._pick_custom_bg, height=34
        )
        custom_bg_btn.grid(row=0, column=0, padx=6, sticky="ew")

        custom_fg_btn = ctk.CTkButton(
            custom_frame, text="✏️ 文字色を自由に選ぶ...", fg_color="#356BC4", hover_color="#285BAF",
            command=self._pick_custom_fg, height=34
        )
        custom_fg_btn.grid(row=0, column=1, padx=6, sticky="ew")

        # 5. 下部操作ボタン
        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=16, pady=(20, 8))
        bottom_frame.grid_columnconfigure((0, 1), weight=1)

        reset_btn = ctk.CTkButton(
            bottom_frame, text="標準の配色に戻す", fg_color="#64748B", hover_color="#475569",
            command=self._reset_colors, height=32
        )
        reset_btn.grid(row=0, column=0, padx=6, sticky="ew")

        close_btn = ctk.CTkButton(
            bottom_frame, text="閉じる", fg_color="#16A34A", hover_color="#15803D",
            command=self.destroy, height=32
        )
        close_btn.grid(row=0, column=1, padx=6, sticky="ew")

    def _select_theme(self, theme_key):
        self.app.switch_theme(theme_key)

    def _set_bg(self, color):
        self.app.set_terminal_custom_color(bg=color)

    def _set_fg(self, color):
        self.app.set_terminal_custom_color(fg=color)

    def _pick_custom_bg(self):
        cur_bg = self.app.terminal_colors.get("terminal", "#E2E8F0")
        color = colorchooser.askcolor(initialcolor=cur_bg, title="ターミナル背景色を選択", parent=self)
        if color and color[1]:
            self.app.set_terminal_custom_color(bg=color[1])

    def _pick_custom_fg(self):
        cur_fg = self.app.terminal_colors.get("text", "#0F172A")
        color = colorchooser.askcolor(initialcolor=cur_fg, title="ターミナル文字色を選択", parent=self)
        if color and color[1]:
            self.app.set_terminal_custom_color(fg=color[1])

    def _reset_colors(self):
        self.app.reset_custom_colors()


class LoginConfigDialog(ctk.CTkToplevel):
    """ログイン情報（ホスト・ポート・ユーザー・パスワード）の編集・保存ダイアログ"""

    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_save_callback = on_save_callback

        self.title("ログイン情報の設定")
        self.geometry("440x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 440) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 380) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="QAD 接続設定", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(12, 16))

        # ホスト名
        row_host = ctk.CTkFrame(frame, fg_color="transparent")
        row_host.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_host, text="ホスト名:", width=90, anchor="w").pack(side="left")
        self.host_entry = ctk.CTkEntry(row_host, width=220)
        self.host_entry.pack(side="left", fill="x", expand=True)
        self.host_entry.insert(0, self.config.get("host", "mfg03"))

        # ポート番号
        row_port = ctk.CTkFrame(frame, fg_color="transparent")
        row_port.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_port, text="ポート番号:", width=90, anchor="w").pack(side="left")
        self.port_entry = ctk.CTkEntry(row_port, width=220)
        self.port_entry.pack(side="left", fill="x", expand=True)
        self.port_entry.insert(0, str(self.config.get("port", 22)))

        # ユーザー名
        row_user = ctk.CTkFrame(frame, fg_color="transparent")
        row_user.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_user, text="ユーザー名:", width=90, anchor="w").pack(side="left")
        self.user_entry = ctk.CTkEntry(row_user, width=220)
        self.user_entry.pack(side="left", fill="x", expand=True)
        self.user_entry.insert(0, self.config.get("user", "takehik"))

        # パスワード
        row_pass = ctk.CTkFrame(frame, fg_color="transparent")
        row_pass.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_pass, text="パスワード:", width=90, anchor="w").pack(side="left")
        self.pass_entry = ctk.CTkEntry(row_pass, width=220, show="*")
        self.pass_entry.pack(side="left", fill="x", expand=True)

        saved_pass = ""
        b64 = self.config.get("pass_b64", "")
        if b64:
            try:
                saved_pass = base64.b64decode(b64.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                pass
        self.pass_entry.insert(0, saved_pass)

        # パスワード表示トグル
        self.show_pass_var = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(
            frame, text="パスワードを表示する", variable=self.show_pass_var,
            command=lambda: self.pass_entry.configure(show="" if self.show_pass_var.get() else "*"),
            checkbox_width=18, checkbox_height=18, font=ctk.CTkFont(size=12)
        )
        chk.pack(anchor="w", padx=110, pady=(2, 14))

        # ボタン
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(10, 10))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
                                   command=self.destroy)
        cancel_btn.grid(row=0, column=0, padx=8, sticky="ew")

        save_btn = ctk.CTkButton(btn_frame, text="保存して適用", fg_color="#356BC4", hover_color="#285BAF",
                                 command=self._on_save)
        save_btn.grid(row=0, column=1, padx=8, sticky="ew")

    def _on_save(self):
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        pwd = self.pass_entry.get()

        if not host or not user:
            messagebox.showwarning("入力エラー", "ホスト名とユーザー名は必須です。", parent=self)
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("入力エラー", "ポート番号は半角数字で入力してください。", parent=self)
            return

        self.config["host"] = host
        self.config["port"] = port
        self.config["user"] = user
        self.config["pass_b64"] = base64.b64encode(pwd.encode("utf-8")).decode("ascii")

        save_config(self.config)
        if self.on_save_callback:
            self.on_save_callback(self.config)
        self.destroy()
        messagebox.showinfo("設定完了", "ログイン情報を保存しました。\n次回の接続から適用されます。", parent=self.parent)


class AddShortcutDialog(ctk.CTkToplevel):
    """メニュー番号へ直接移動するショートカットを追加するダイアログ"""

    def __init__(self, parent, on_add_callback):
        super().__init__(parent)
        self.parent = parent
        self.on_add_callback = on_add_callback
        self.title("ショートカットの追加")
        self.geometry("380x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 380) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 240) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(frame, text="⚡ ショートカットの追加", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(6, 12))

        # 表示名
        row_name = ctk.CTkFrame(frame, fg_color="transparent")
        row_name.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_name, text="表示名:", width=85, anchor="w").pack(side="left")
        self.name_entry = ctk.CTkEntry(row_name, width=210, placeholder_text="例: 在庫スナップショット")
        self.name_entry.pack(side="left", fill="x", expand=True)

        # メニュー番号
        row_code = ctk.CTkFrame(frame, fg_color="transparent")
        row_code.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_code, text="メニュー番号:", width=85, anchor="w").pack(side="left")
        self.code_entry = ctk.CTkEntry(row_code, width=210, placeholder_text="例: 99.3.6.1")
        self.code_entry.pack(side="left", fill="x", expand=True)

        # ボタン
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(16, 6))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
                                   command=self.destroy)
        cancel_btn.grid(row=0, column=0, padx=6, sticky="ew")

        add_btn = ctk.CTkButton(btn_frame, text="追加する", fg_color="#356BC4", hover_color="#285BAF",
                                command=self._on_add)
        add_btn.grid(row=0, column=1, padx=6, sticky="ew")

        self.name_entry.focus_set()

    def _on_add(self):
        name = self.name_entry.get().strip()
        code = self.code_entry.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "表示名を入力してください。", parent=self)
            return
        if not code:
            messagebox.showwarning("入力エラー", "メニュー番号を入力してください。", parent=self)
            return
        if self.on_add_callback:
            self.on_add_callback(name, code)
        self.destroy()


class TerminalApp(ctk.CTk):
    def __init__(self):
        self.config = load_config()
        self.theme_name = self.config.get("theme", "light")
        # 外枠UI（右カラム・メニューバー・ヘッダー・ボタン）は初期ライト配色で常に固定
        self.ui_colors = dict(COLOR_THEMES["light"])
        # ターミナル表示部分（画面内）のみ、選択テーマ・カスタム色を適用
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.ui_font_family = find_first_available_font(PREFERRED_UI_FONTS, fallback="Yu Gothic UI")
        self.terminal_font_family = find_first_available_font(PREFERRED_TERMINAL_FONTS, fallback="Consolas")

        self.title("QAD / MFG:PRO")
        self.geometry("1460x780")
        self.minsize(1020, 660)
        self.configure(fg_color=self.ui_colors["background"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self.session = None
        self.events = queue.Queue()
        self.is_connected = False
        self.closing = False
        self.rendered_lines = [None] * ROWS
        self.raw_lines = {}
        self.font_size = 18
        self.active_cols = 80
        self.auto_fit = True
        self._resize_job = None
        self.shortcut_buttons = []

        self._build_menu()
        self._build_header()
        self._build_terminal()
        self._build_shortcut_bar()
        self._set_state("未接続")
        self._show_message("")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_job = self.after(33, self._poll)
        self.after(100, self._apply_auto_fit)

    def _get_terminal_colors(self):
        """現在のテーマおよびカスタム色を適用したターミナル表示用カラー辞書を取得"""
        theme_key = self.config.get("theme", "light")
        colors = dict(COLOR_THEMES.get(theme_key, COLOR_THEMES["light"]))
        if self.config.get("custom_terminal_bg"):
            colors["terminal"] = self.config["custom_terminal_bg"]
        if self.config.get("custom_terminal_fg"):
            colors["text"] = self.config["custom_terminal_fg"]
        return colors

    def _get_active_colors(self):
        return self._get_terminal_colors()

    def _button(self, parent, text, command, primary=False):
        return ActionButton(parent, text, command, primary, font_family=self.ui_font_family, colors=self.ui_colors)

    def _build_menu(self):
        menubar = tk.Menu(self)

        # 1. 接続メニュー
        self.connection_menu = tk.Menu(menubar, tearoff=False)
        self.connection_menu.add_command(label="ログイン / 接続", command=self.connect_to_server)
        self.connection_menu.add_command(label="切断", command=self.disconnect_server)
        self.connection_menu.add_separator()
        self.connection_menu.add_command(label="終了", command=self.on_close)
        menubar.add_cascade(label="接続", menu=self.connection_menu)

        # 2. 編集メニュー
        self.edit_menu = tk.Menu(menubar, tearoff=False)
        self.edit_menu.add_command(label="コピー (選択範囲または画面)", accelerator="Ctrl+C", command=self.copy_selection_or_screen)
        self.edit_menu.add_command(label="貼り付け", accelerator="Ctrl+V", command=self.paste_from_clipboard)
        self.edit_menu.add_command(label="すべて選択", accelerator="Ctrl+A", command=self.select_all_text)
        self.edit_menu.add_separator()
        self.windows_shortcuts_var = tk.BooleanVar(value=bool(self.config.get("enable_windows_shortcuts", True)))
        self.edit_menu.add_checkbutton(
            label="Windows標準ショートカットを有効化 (Ctrl+C / Ctrl+V / Ctrl+A)",
            variable=self.windows_shortcuts_var,
            command=self.toggle_windows_shortcuts,
        )
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="📋 画面全体をコピー", accelerator="Ctrl+Shift+C", command=self.copy_screen_text)
        menubar.add_cascade(label="編集", menu=self.edit_menu)

        # 3. キー送信メニュー
        self.key_menu = tk.Menu(menubar, tearoff=False)
        for index, (_, buttons) in enumerate(TOOLBAR_GROUPS):
            if index:
                self.key_menu.add_separator()
            for label, key in buttons:
                self.key_menu.add_command(label=label, command=lambda k=key: self.send_key(k))
        menubar.add_cascade(label="キー送信", menu=self.key_menu)

        # 4. 表示メニュー
        view = tk.Menu(menubar, tearoff=False)
        view.add_command(label="文字を大きく", command=lambda: self.change_font_size(1))
        view.add_command(label="文字を小さく", command=lambda: self.change_font_size(-1))
        view.add_command(label="標準サイズ", command=lambda: self.change_font_size(reset=True))
        view.add_separator()
        view.add_command(label="📋 画面の文字をコピー", accelerator="Ctrl+Shift+C", command=self.copy_screen_text)
        view.add_separator()
        self.auto_fit_var = tk.BooleanVar(value=True)
        view.add_checkbutton(label="画面サイズに自動調整 (Auto Fit)", variable=self.auto_fit_var, command=self.toggle_auto_fit)
        view.add_separator()
        view.add_command(label="ターミナルにフォーカス", command=self.focus_terminal)
        menubar.add_cascade(label="表示", menu=view)

        # 5. カラーパレットメニュー（独立メニュー）
        self.palette_menu = tk.Menu(menubar, tearoff=False)
        self.palette_menu.add_command(label="🎨 カラーパレットを開く...", command=self.open_color_palette)
        self.palette_menu.add_separator()
        self.palette_menu.add_command(label="ライト（標準グレー）", command=lambda: self.switch_theme("light"))
        self.palette_menu.add_command(label="ダークスレート", command=lambda: self.switch_theme("dark"))
        self.palette_menu.add_command(label="クラシックグリーン (VT100)", command=lambda: self.switch_theme("classic_green"))
        self.palette_menu.add_command(label="アンバー（琥珀色）", command=lambda: self.switch_theme("amber"))
        self.palette_menu.add_separator()
        self.palette_menu.add_command(label="配色を標準に戻す", command=self.reset_custom_colors)
        menubar.add_cascade(label="カラーパレット", menu=self.palette_menu)

        # 6. ログイン情報メニュー
        login_menu = tk.Menu(menubar, tearoff=False)
        login_menu.add_command(label="ログイン情報の編集...", command=self.open_login_dialog)
        menubar.add_cascade(label="ログイン情報", menu=login_menu)

        # 7. ヘルプメニュー
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作ガイド", command=self.show_help)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)

        self.configure(menu=menubar)

    def _build_header(self):
        self.header = ctk.CTkFrame(self, fg_color=self.ui_colors["background"], corner_radius=0)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self.header, text="未接続", text_color=self.ui_colors["muted"],
                                         font=ctk.CTkFont(family=self.ui_font_family, size=14))
        self.status_label.grid(row=0, column=0, sticky="w", padx=24, pady=(10, 0))

        # 画面コピーボタン
        self.copy_btn = self._button(self.header, "📋 画面コピー", self.copy_screen_text)
        self.copy_btn.grid(row=0, column=1, padx=(0, 8), pady=(10, 0))

        self.connect_btn = self._button(self.header, "ログイン", self.connect_to_server, True)
        self.connect_btn.grid(row=0, column=2, padx=(0, 8), pady=(10, 0))
        self.disconnect_btn = self._button(self.header, "切断", self.disconnect_server)
        self.disconnect_btn.grid(row=0, column=3, padx=(0, 20), pady=(10, 0))

    def _build_terminal(self):
        # ターミナルパネル（外枠）: 右カラム廃止により画面横幅100%をフル活用
        self.terminal_panel = ctk.CTkFrame(self, fg_color=self.ui_colors["background"], corner_radius=0)
        self.terminal_panel.grid(row=1, column=0, padx=8, pady=(4, 4), sticky="nsew")
        self.terminal_panel.grid_columnconfigure(0, weight=1)
        self.terminal_panel.grid_rowconfigure(0, weight=1)

        self.font_size = 18
        self.active_cols = 80
        self.terminal_font = ctk.CTkFont(family=self.terminal_font_family, size=self.font_size)

        # ターミナル本体：パネルいっぱいに最大表示（スクロールバーを完全排除）
        self.textbox = ctk.CTkTextbox(
            self.terminal_panel, font=self.terminal_font, fg_color=self.terminal_colors["terminal"],
            text_color=self.terminal_colors["text"], wrap="none", corner_radius=10,
            border_width=1, border_color=self.terminal_colors["border"],
            activate_scrollbars=False,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")
        # 罫線の縦線が上下で隙間なく完全に繋がり、かつ下端が切れないようパディングを初期化
        self.textbox._textbox.configure(spacing1=0, spacing2=0, spacing3=0, padx=0, pady=0)
        self._apply_text_tags()

        self.textbox.bind("<Key>", self.on_key_press)
        self.textbox.bind("<FocusIn>", lambda event: self.textbox.configure(border_color=self.terminal_colors["focus"]))
        self.textbox.bind("<FocusOut>", lambda event: self.textbox.configure(border_color=self.terminal_colors["border"]))
        self.textbox.bind("<Control-Shift-C>", self.copy_screen_text)
        self.textbox.bind("<Control-Shift-c>", self.copy_screen_text)
        self.textbox.bind("<<Paste>>", self._on_paste_event)
        self.textbox.bind("<<Cut>>", lambda event: "break")

        self.footer = ctk.CTkLabel(self.terminal_panel, text="", text_color=self.ui_colors["error"],
                                   font=ctk.CTkFont(family=self.ui_font_family, size=12))
        self.footer.grid(row=1, column=0, padx=8, pady=(2, 0), sticky="s")
        self.footer.grid_remove()

        self.terminal_panel.bind("<Configure>", self._on_panel_resize)

    def _apply_text_tags(self):
        """テキストボックスのタグ設定（反転・下線・太字等）を現在のターミナルカラーで更新"""
        self.textbox.tag_config("remote_cursor", background=self.terminal_colors["cursor"])
        self.textbox.tag_config("reverse", background=self.terminal_colors["reverse_bg"], foreground=self.terminal_colors["reverse_fg"])
        self.textbox.tag_config("menu_highlight", background=self.terminal_colors["menu_highlight_bg"], foreground=self.terminal_colors["menu_highlight_fg"])
        self.textbox.tag_config("underline", underline=True)
        try:
            self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
        except Exception:
            self.textbox.tag_config("bold", foreground=self.terminal_colors["accent"])

    def _build_shortcut_bar(self):
        """最下段のショートカット（直接移動）バーを構築"""
        self.shortcut_bar = ctk.CTkFrame(
            self, height=44, fg_color=self.ui_colors["panel"],
            corner_radius=10, border_width=1, border_color=self.ui_colors["border"]
        )
        self.shortcut_bar.grid(row=2, column=0, padx=8, pady=(0, 6), sticky="ew")
        self.shortcut_bar.grid_columnconfigure(1, weight=1)

        # 左端ラベル
        lbl = ctk.CTkLabel(
            self.shortcut_bar, text="📌 クイックメニュー:",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            text_color=self.ui_colors["muted"]
        )
        lbl.grid(row=0, column=0, padx=(12, 6), pady=4)

        # スクロール対応ボタン配置領域（多数登録時も横スクロールで綺麗に収まる）
        self.shortcut_scroll_frame = ctk.CTkScrollableFrame(
            self.shortcut_bar, orientation="horizontal", height=32,
            fg_color="transparent"
        )
        self.shortcut_scroll_frame.grid(row=0, column=1, sticky="ew", padx=4, pady=2)

        # 右端「＋ 追加」ボタン
        self.add_shortcut_btn = ctk.CTkButton(
            self.shortcut_bar, text="＋ 追加", width=72, height=28,
            fg_color="#356BC4", hover_color="#285BAF", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.open_add_shortcut_dialog
        )
        self.add_shortcut_btn.grid(row=0, column=2, padx=(4, 10), pady=4)

        self._refresh_shortcut_buttons()

    def _refresh_shortcut_buttons(self):
        """登録されたショートカットボタン一覧を再描画"""
        for w in self.shortcut_scroll_frame.winfo_children():
            w.destroy()
        self.shortcut_buttons = []

        shortcuts = self.config.get("shortcuts", [])
        state = "normal" if self.is_connected else "disabled"
        for idx, sc in enumerate(shortcuts):
            name = sc.get("name", "")
            code = sc.get("code", "")
            btn = ctk.CTkButton(
                self.shortcut_scroll_frame, text=f"{name} ({code})", height=28,
                fg_color=self.ui_colors["button"], hover_color=self.ui_colors["hover"],
                text_color=self.ui_colors["text"],
                font=ctk.CTkFont(family=self.ui_font_family, size=12),
                corner_radius=6, state=state,
                command=lambda c=code: self.jump_to_menu(c)
            )
            btn.pack(side="left", padx=4, pady=2)
            # 右クリックで削除メニュー表示
            btn.bind("<Button-3>", lambda event, i=idx, n=name: self._show_shortcut_context_menu(event, i, n))
            self.shortcut_buttons.append(btn)

    def _show_shortcut_context_menu(self, event, idx, name):
        """ショートカットボタンの右クリックコンテキストメニュー"""
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=f"「{name}」を削除", command=lambda: self._delete_shortcut(idx))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_shortcut(self, idx):
        """ショートカットを削除"""
        shortcuts = self.config.get("shortcuts", [])
        if 0 <= idx < len(shortcuts):
            deleted = shortcuts.pop(idx)
            self.config["shortcuts"] = shortcuts
            save_config(self.config)
            self._refresh_shortcut_buttons()
            self._show_input_error(f"ショートカット「{deleted['name']}」を削除しました")

    def open_add_shortcut_dialog(self):
        """「＋」追加ダイアログを開く"""
        AddShortcutDialog(self, self._on_shortcut_added)

    def _on_shortcut_added(self, name, code):
        """ショートカット追加コールバック"""
        shortcuts = self.config.get("shortcuts", [])
        shortcuts.append({"name": name, "code": code})
        self.config["shortcuts"] = shortcuts
        save_config(self.config)
        self._refresh_shortcut_buttons()
        self._show_input_error(f"ショートカット「{name} ({code})」を追加しました")

    def is_menu_screen(self):
        """現在の画面がメインメニューまたはメニュー選択画面かどうかを精密判定"""
        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                content = self.textbox.get("1.0", "end")
                lines = content.splitlines()
            except Exception:
                lines = []

        full_text = "\n".join(lines)
        if not full_text.strip():
            return False

        # 1. 上部タイトル判定 (メインメニュー / Main Menu)
    def is_main_menu(self):
        """現在の画面がQADメインメニュー（mfmenu / Main Menu）かどうかを判定（右肩日付は変数として無視）"""
        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                content = self.textbox.get("1.0", "end")
                lines = content.splitlines()
            except Exception:
                lines = []

        full_text = "\n".join(lines)
        if not full_text.strip():
            return False

        full_lower = full_text.lower()

        # 1. 2行目ヘッダーの「mfmenu」と「Main Menu」の完全合致（右肩日付は変数として無視）
        # 例: │mfmenu                             Main Menu                          09/18/26│
        for line in lines[:5]:
            l_lower = line.lower()
            if "mfmenu" in l_lower and "main menu" in l_lower:
                return True

        # 2. プロンプト判定: "F4 or blank to EXIT"（メインメニュー特有の終了メッセージ）
        if "f4 or blank to exit" in full_lower:
            return True

        # 3. 単独の mfmenu コマンド名判定
        if re.search(r'\bmfmenu\b', full_lower):
            return True

        return False

    def is_menu_screen(self):
        """現在の画面がメインメニューまたはサブメニュー選択画面かどうかを判定"""
        if self.is_main_menu():
            return True

        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                content = self.textbox.get("1.0", "end")
                lines = content.splitlines()
            except Exception:
                lines = []

        full_text = "\n".join(lines)
        if not full_text.strip():
            return False

        menu_prompts = [
            "Please select a function",
            "select a function",
            "Selection:",
            "選択:",
            "選んでください",
            "メニュー選択",
            "Go to:",
        ]
        full_lower = full_text.lower()
        for p in menu_prompts:
            if p.lower() in full_lower:
                return True

        menu_item_matches = re.findall(r'(?<!\d)\b\d{1,2}\.\s+[^\s│]{2,}', full_text)
        if len(menu_item_matches) >= 3:
            return True

        return False

    def jump_to_menu(self, code):
        """指定されたメニュー番号へ直接ジャンプ（メイン画面ならF4を押さず直接入力、業務画面ならF4で戻って入力）"""
        if not self.is_connected or not self.session:
            self._show_input_error("サーバーに接続されていません")
            return

        # 現在の画面がメインメニュー（mfmenu）かどうかを判定
        is_main = self.is_main_menu()

        # メインスレッド側で即座に状況を表示
        if is_main:
            self._show_input_error(f"メイン画面から直接ジャンプ: {code}")
        else:
            self._show_input_error(f"メニューに戻ってジャンプ: {code}")

        def _do_jump():
            try:
                import time
                if is_main:
                    # メイン画面にいる場合: F4を押すとEXITエラーになるため、F4を押さずに直接送信
                    self.session.send(f"{code}\r")
                else:
                    # 業務画面・入力フィールドにいる場合: F4でメニューに戻ってから番号を送信
                    self.session.send(KEY_SEQUENCES["F4"])

                    # メイン画面（またはメニュー画面）に切り替わるのをスマート待機（最大1.2秒）
                    waited = 0.0
                    while waited < 1.2:
                        time.sleep(0.1)
                        waited += 0.1
                        if self.is_main_menu() or self.is_menu_screen():
                            break

                    time.sleep(0.15)
                    self.session.send(f"{code}\r")
            except Exception as e:
                print(f"メニュー直接ジャンプエラー: {e}", file=sys.stderr)
            finally:
                try:
                    self.after(100, self.focus_terminal)
                except Exception:
                    pass

        import threading
        threading.Thread(target=_do_jump, daemon=True, name="menu-jump").start()

    def copy_screen_text(self, event=None):
        """画面に表示されているテキスト全体をクリップボードにコピー"""
        lines = []
        if getattr(self, "raw_lines", None):
            for r in range(ROWS):
                if r in self.raw_lines and self.raw_lines[r]:
                    lines.append(self.raw_lines[r][0].rstrip())
                else:
                    lines.append("")
            while lines and not lines[-1]:
                lines.pop()
            text = "\n".join(lines)
        else:
            try:
                text = self.textbox.get("1.0", "end-1c").rstrip()
            except Exception:
                text = ""

        if text:
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update()
                self._show_input_error("画面の文字をクリップボードにコピーしました 📋")
            except Exception as e:
                self._show_input_error(f"コピー失敗: {e}")
        else:
            self._show_input_error("コピーする画面テキストがありません")
        return "break"

    def copy_selection_or_screen(self, event=None):
        """テキスト選択範囲があれば選択部分を、なければ画面全体をコピー"""
        selected_text = ""
        try:
            if self.textbox.tag_ranges("sel"):
                selected_text = self.textbox.get("sel.first", "sel.last")
        except Exception:
            selected_text = ""

        if selected_text:
            try:
                self.clipboard_clear()
                self.clipboard_append(selected_text)
                self.update()
                self._show_input_error(f"選択範囲をコピーしました 📋 ({len(selected_text)}文字)")
            except Exception as e:
                self._show_input_error(f"コピー失敗: {e}")
            return "break"
        else:
            return self.copy_screen_text(event)

    def paste_from_clipboard(self, event=None):
        """クリップボードから文字列を取得し、サーバーへキー入力として安全に送信"""
        if not self.is_connected or self.session is None:
            self._show_input_error("未接続のため貼り付けできません")
            return "break"
        try:
            text = self.clipboard_get()
        except Exception:
            self._show_input_error("クリップボードが空か、取得できませんでした")
            return "break"
        if not text:
            return "break"

        # 改行コードの正規化: Windows (\r\n) や Unix (\n) を VT100 / QAD 形式 (\r) に変換
        text = text.replace("\r\n", "\r").replace("\n", "\r")

        # CP932 エンコード事前チェック
        try:
            text.encode("cp932")
        except UnicodeEncodeError:
            self.bell()
            self._show_input_error("貼り付けできません：CP932（日本語）で表現できない文字が含まれています。")
            return "break"

        self._send(text)
        self._show_input_error(f"クリップボードの内容を貼り付けました 📋 ({len(text)}文字)")
        return "break"

    def select_all_text(self, event=None):
        """ターミナル画面のテキスト全体を選択状態にする"""
        try:
            self.textbox.tag_add("sel", "1.0", "end-1c")
            self.textbox.focus_set()
            self._show_input_error("画面全体のテキストを選択しました")
        except Exception:
            pass
        return "break"

    def _on_paste_event(self, event=None):
        """Tkinterネイティブのペーストイベントハンドラ（画面崩れを防ぎサーバーへ送信）"""
        if self.config.get("enable_windows_shortcuts", True):
            self.paste_from_clipboard()
        return "break"

    def toggle_windows_shortcuts(self):
        """Windows標準ショートカット（Ctrl+C / Ctrl+V / Ctrl+A）の有効/無効切り替え"""
        val = bool(self.windows_shortcuts_var.get())
        self.config["enable_windows_shortcuts"] = val
        save_config(self.config)
        if val:
            self._show_input_error("Windows標準ショートカット（Ctrl+C/V/A）を有効化しました")
        else:
            self._show_input_error("Windows標準ショートカットを無効化しました（端末標準キー送信）")

    # --- カラーパレット・テーマ切替処理 ---
    def open_color_palette(self):
        ColorPaletteDialog(self, self)

    def switch_theme(self, theme_key):
        """プリセットテーマへの切り替え（ターミナル表示部のみ変更）"""
        if theme_key not in COLOR_THEMES:
            return
        self.config["theme"] = theme_key
        self.config["custom_terminal_bg"] = None
        self.config["custom_terminal_fg"] = None
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def set_terminal_custom_color(self, bg=None, fg=None):
        """ターミナルの背景色・文字色をカスタム指定（ターミナル表示部のみ変更）"""
        if bg:
            self.config["custom_terminal_bg"] = bg
        if fg:
            self.config["custom_terminal_fg"] = fg
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def reset_custom_colors(self):
        """カスタム色をリセットしテーマ標準に戻す（ターミナル表示部のみ変更）"""
        self.config["custom_terminal_bg"] = None
        self.config["custom_terminal_fg"] = None
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def _refresh_theme_ui(self):
        """ターミナル表示部分（画面内）の配色を再描画（右カラム・メニューバー・ヘッダーは初期色固定）"""
        self.textbox.configure(
            fg_color=self.terminal_colors["terminal"],
            text_color=self.terminal_colors["text"],
            border_color=self.terminal_colors["border"],
        )
        self._apply_text_tags()
        self._rerender_all()

    # --- ログイン情報ダイアログ ---
    def open_login_dialog(self):
        LoginConfigDialog(self, self.config, self._on_login_config_saved)

    def _on_login_config_saved(self, new_config):
        self.config = new_config

    # --- 状態更新・描画ロジック ---
    def _set_state(self, text, color="muted"):
        self.status_label.configure(text=text, text_color=self.ui_colors.get(color, self.ui_colors["muted"]))
        idle = self.session is None
        self.connect_btn.configure(state="normal" if idle else "disabled")
        self.disconnect_btn.configure(state="disabled" if idle else "normal")
        self.connection_menu.entryconfigure(0, state="normal" if idle else "disabled")
        self.connection_menu.entryconfigure(1, state="disabled" if idle else "normal")
        state = "normal" if self.is_connected else "disabled"
        for button in getattr(self, "shortcut_buttons", []):
            button.configure(state=state)
        for index in range(self.key_menu.index("end") + 1):
            if self.key_menu.type(index) == "command":
                self.key_menu.entryconfigure(index, state=state)

    def _show_message(self, message):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        if message:
            self.textbox.insert("1.0", message)
        else:
            self.textbox.insert("1.0", "\n" * (ROWS - 1))
        for tag in ("reverse", "menu_highlight", "underline", "bold", "remote_cursor"):
            self.textbox.tag_remove(tag, "1.0", "end")
        self.textbox.configure(state="disabled")
        self.rendered_lines = [None] * ROWS
        self.raw_lines = {}
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def connect_to_server(self):
        if self.session is not None or self.closing:
            return

        host = self.config.get("host", "mfg03")
        port = int(self.config.get("port", 22))
        user = self.config.get("user", "takehik")
        pwd = ""
        b64 = self.config.get("pass_b64", "")
        if b64:
            try:
                pwd = base64.b64decode(b64.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                pass

        self.session = TerminalSession(host, port, user, pwd, self.events)
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
                continue
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

        changed = {row: data for row, data in changed.items() if self.raw_lines.get(row) != data}
        if changed:
            self.textbox.configure(state="normal")
            for row, (raw_line, spans) in changed.items():
                line, pad_spans = self._align_border_line(raw_line)
                start_idx = f"{row + 1}.0"
                end_idx = f"{row + 1}.end"
                self.textbox.delete(start_idx, end_idx)
                self.textbox.insert(start_idx, line)
                for tag in ("reverse", "underline", "bold"):
                    self.textbox.tag_remove(tag, start_idx, end_idx)
                for s_idx, e_idx, tags in spans:
                    for tag in tags:
                        self.textbox.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
                for s_idx, e_idx, p_tag in pad_spans:
                    self.textbox.tag_add(p_tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
                self.rendered_lines[row] = (line, spans)
                self.raw_lines[row] = (raw_line, spans)

            self._apply_menu_highlight()
            self._auto_align_header_border()
            self.textbox.configure(state="disabled")

        self.textbox.tag_remove("remote_cursor", "1.0", "end")
        if cursor is not None:
            row, column = cursor
            self.textbox.tag_add("remote_cursor", f"{row + 1}.{column}", f"{row + 1}.{column + 1}")
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def _align_border_line(self, line):
        """半角カナ・漢字を含む罫線行のピクセル幅を純ASCII罫線行と揃える"""
        border_right = {"┐", "┘", "│"}
        if not line or line[-1] not in border_right:
            return line, []
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(font=self.textbox._textbox.cget("font"))
        except Exception:
            return line, []
        ref_width = f.measure("M") * self.active_cols
        line_width = f.measure(line)
        needed = ref_width - line_width
        if needed <= 0:
            return line, []

        is_box_line = line and line[0] in {"┌", "└"}
        cw = f.measure("M")
        if cw <= 0:
            return line, []

        cur_font_size = self.font_size

        if is_box_line:
            # 上部・下部枠線行:
            # ─ のフォントサイズを変えるとアセントの違いで横線が凹んでしまうため、
            # ─ は必ず通常フォントサイズ(cur_font_size)で均一に描画する。
            pad_char = "─"
            spaces = [i for i, c in enumerate(line) if c == " "]
            if spaces:
                import math
                pad_count = max(1, math.ceil(needed / cw))
                overhang = (pad_count * cw) - needed  # 縮めるべきピクセル数
                new_line = line[:-1] + (pad_char * pad_count) + line[-1]

                tag_spans = []
                if overhang > 0:
                    # 行内の空白文字(スペース)を縮めてオーバー分を吸収する
                    # 空白は透明なため、アセントによる凹み等の視覚的副作用は一切発生しない
                    use_spaces = spaces[:min(len(spaces), 4)]
                    shrink_per_space = overhang / len(use_spaces)
                    target_w = max(1, cw - shrink_per_space)

                    best_sz = cur_font_size
                    best_diff = 999
                    for sz in range(max(4, cur_font_size - 14), cur_font_size):
                        w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(" ")
                        if abs(w - target_w) < best_diff:
                            best_diff = abs(w - target_w)
                            best_sz = sz

                    tag_name = f"space_shrink_{cur_font_size}_{best_sz}"
                    try:
                        self.textbox._textbox.tag_config(tag_name, font=(self.terminal_font_family, best_sz))
                    except Exception:
                        pass
                    for sp_idx in use_spaces:
                        tag_spans.append((sp_idx, sp_idx + 1, tag_name))
                return new_line, tag_spans
            else:
                # 空白がない場合は通常サイズの ─ を挿入（横線を絶対に凹ませず平坦に保つ）
                pad_count = max(1, round(needed / cw))
                new_line = line[:-1] + (pad_char * pad_count) + line[-1]
                return new_line, []
        else:
            # 中間データ行 (│ ... │):
            # パディング文字は空白 (" ") なので、フォントサイズ微調整を行っても
            # 透明のため横線の凹み等の視覚的副作用は一切生じない。
            pad_char = " "
            pad_count = max(1, round(needed / cw))
            base_w = needed // pad_count
            rem = needed % pad_count
            widths = [base_w + 1 if i < rem else base_w for i in range(pad_count)]

            pad_tags = []
            for idx, tw in enumerate(widths):
                best_sz = cur_font_size
                best_diff = 999
                for sz in range(max(6, cur_font_size - 10), cur_font_size + 10):
                    w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(pad_char)
                    if abs(w - tw) < best_diff:
                        best_diff = abs(w - tw)
                        best_sz = sz
                tag_name = f"pad_tag_sp_{cur_font_size}_{idx}_{best_sz}"
                try:
                    self.textbox._textbox.tag_config(tag_name, font=(self.terminal_font_family, best_sz))
                except Exception:
                    pass
                pad_tags.append(tag_name)

            start_char_idx = len(line) - 1
            new_line = line[:-1] + (pad_char * pad_count) + line[-1]
            tag_spans = [(start_char_idx + i, start_char_idx + i + 1, pad_tags[i]) for i in range(pad_count)]
            return new_line, tag_spans

    def _auto_align_header_border(self):
        """Textウィジェットの実測描画座標(bbox)に基づき、ヘッダー行(Row 0)の右端角(┐)を純罫線行と1px単位で完全一致させる"""
        try:
            tb = self.textbox._textbox
            b1 = tb.bbox("2.end-1c")
            b2 = tb.bbox("3.end-1c")
            target_x = None
            if b1 and b2:
                target_x = max(b1[0], b2[0])
            elif b1:
                target_x = b1[0]
            elif b2:
                target_x = b2[0]
            if not target_x:
                return

            b0 = tb.bbox("1.end-1c")
            if not b0:
                return
            diff_x = target_x - b0[0]
            if diff_x == 0:
                return  # 完全に一致している

            # 1〜3px の微差がある場合、行内の空白文字のタグフォントサイズを微調整して一致させる
            # （※ ─ 文字のフォントサイズを絶対に変更してはいけない！横線が凹む原因になるため）
            line0 = tb.get("1.0", "1.end")
            if len(line0) < 3 or line0[-1] != "┐":
                return

            # 行内の空白文字を探す
            spaces = [i for i, c in enumerate(line0) if c == " "]
            if not spaces:
                return

            import tkinter.font as tkfont
            sp_idx = spaces[0]
            char_idx_str = f"1.{sp_idx}"
            cur_tags = tb.tag_names(char_idx_str)
            existing_tag = next((t for t in cur_tags if t.startswith("space_shrink_") or t.startswith("space_auto_adj_")), None)
            cur_sz = self.font_size
            if existing_tag:
                parts = existing_tag.split("_")
                if len(parts) >= 4:
                    try:
                        cur_sz = int(parts[-1])
                    except Exception:
                        pass
                tb.tag_remove(existing_tag, char_idx_str, f"1.{sp_idx + 1}")

            cur_w = tkfont.Font(family=self.terminal_font_family, size=cur_sz).measure(" ")
            target_space_w = cur_w + diff_x
            best_sz = cur_sz
            best_d = 999
            for sz in range(max(4, self.font_size - 14), self.font_size + 10):
                w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(" ")
                if abs(w - target_space_w) < best_d:
                    best_d = abs(w - target_space_w)
                    best_sz = sz

            new_tag = f"space_auto_adj_{best_sz}"
            tb.tag_config(new_tag, font=(self.terminal_font_family, best_sz))
            tb.tag_add(new_tag, char_idx_str, f"1.{sp_idx + 1}")
        except Exception:
            pass

    def _rerender_all(self):
        """フォントサイズ変更時・テーマ変更時に全行を新しいフォントメトリクスで再描画"""
        if not getattr(self, "raw_lines", None):
            return
        self.textbox.configure(state="normal")
        for row, (raw_line, spans) in self.raw_lines.items():
            line, pad_spans = self._align_border_line(raw_line)
            start_idx = f"{row + 1}.0"
            end_idx = f"{row + 1}.end"
            self.textbox.delete(start_idx, end_idx)
            self.textbox.insert(start_idx, line)
            for tag in ("reverse", "underline", "bold"):
                self.textbox.tag_remove(tag, start_idx, end_idx)
            for s_idx, e_idx, tags in spans:
                for tag in tags:
                    self.textbox.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
            for s_idx, e_idx, p_tag in pad_spans:
                self.textbox.tag_add(p_tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
            self.rendered_lines[row] = (line, spans)
        self._apply_menu_highlight()
        self._auto_align_header_border()
        self.textbox.configure(state="disabled")
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def _apply_menu_highlight(self):
        """メニュー選択プロンプトの入力番号に対応するメニュー項目を検知して暗転（ハイライト）する"""
        self.textbox.tag_remove("menu_highlight", "1.0", "end")
        input_num = None
        for row in range(ROWS):
            line_data = self.rendered_lines[row]
            if not line_data:
                continue
            line = line_data[0]
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
        if event.state & 0x5 == 0x5 and event.keysym in ("Tab", "ISO_Left_Tab"):
            self.connect_btn.focus_set() if self.session is None else self.disconnect_btn.focus_set()
            return "break"

        # Windows標準ショートカット（Ctrl+C / Ctrl+V / Ctrl+A）のクライアント側処理
        if self.config.get("enable_windows_shortcuts", True):
            is_ctrl = bool(event.state & 0x4)
            is_shift = bool(event.state & 0x1)
            keysym_lower = event.keysym.lower()

            # Ctrl+Shift+C: 画面全体の文字をコピー
            if is_ctrl and is_shift and keysym_lower == "c":
                return self.copy_screen_text(event)

            # Ctrl+C: 選択範囲（なければ画面全体）をコピー
            if is_ctrl and not is_shift and keysym_lower == "c":
                return self.copy_selection_or_screen(event)

            # Ctrl+V または Shift+Insert: クリップボードから貼り付け（サーバーへ送信）
            if (is_ctrl and not is_shift and keysym_lower == "v") or (is_shift and event.keysym in ("Insert", "KP_Insert")):
                return self.paste_from_clipboard(event)

            # Ctrl+A: 画面全体のテキストを選択
            if is_ctrl and not is_shift and keysym_lower == "a":
                return self.select_all_text(event)

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

        # 実際の描画テキストウィジェット (_textbox) の実寸を取得
        inner_w = self.textbox._textbox.winfo_width()
        inner_h = self.textbox._textbox.winfo_height()
        if inner_w <= 100 or inner_h <= 100:
            pw = self.terminal_panel.winfo_width()
            ph = self.terminal_panel.winfo_height()
            if pw <= 100 or ph <= 100:
                return
            inner_w = pw - 12
            inner_h = ph - 12

        import tkinter.font as tkfont
        target_cols = getattr(self, "active_cols", 80)
        target_rows = ROWS

        best_size = 12
        best_cw = 9
        best_ch = 18

        # 24行が絶対に1ピクセルも切れることなくスクロールバー不要で収まる最大フォントを探索
        for size in range(36, 11, -1):
            f = tkfont.Font(family=self.terminal_font_family, size=-size)
            cw = f.measure("M")
            ch = f.metrics("linespace")
            if cw * target_cols <= inner_w - 6 and ch * target_rows <= inner_h - 4:
                best_size = size
                best_cw = cw
                best_ch = ch
                break

        # 左右を自動中央揃え（右端文字のクリッピングを防ぐため8pxの安全マージンを確保）
        pad_x = max(2, (inner_w - best_cw * target_cols) // 2 - 8)
        # padyは必ず0に設定（padyを設定するとTkinter仕様により最下行がはみ出して切れるため）
        try:
            self.textbox._textbox.configure(padx=pad_x, pady=0)
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

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
        self.font_size = 18 if reset else max(10, min(36, self.font_size + delta))
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
            "【ログイン・接続】\n"
            "・「ログイン」ボタンまたはメニュー「接続」→「ログイン / 接続」から開始します。\n"
            "・メニューバーの「ログイン情報」からホストやユーザー・パスワードを安全に登録・保存できます。\n\n"
            "【カラーパレット・テーマ】\n"
            "・メニューバーの「カラーパレット」から、専用パレットウィンドウを開いてワンクリックで配色を変更できます。\n"
            "・ライト、ダーク、クラシックグリーン、アンバーの標準テンプレートや、カラーピッカーでの自由な色指定が可能です。\n\n"
            "【画面サイズ・余白調整】\n"
            "・画面サイズに合わせて文字が自動的に最大化され、上下左右中央に綺麗にフィットします（文字切れ防止対応済み）。\n"
            "・「表示」メニューから手動での文字拡大・縮小も行えます。\n\n"
            "【キー操作】\n"
            "・右側ツールバーおよび「キー送信」メニューから各ファンクションキー（F1〜F4）やEnter等を送信できます。\n"
            "・ターミナル内のTabキーはQADに送信され、Ctrl+Shift+Tabで上部ボタンへフォーカス移動できます。",
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
