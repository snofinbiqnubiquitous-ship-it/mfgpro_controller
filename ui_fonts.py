"""Shared font policy for the application UI and terminal."""
import tkinter.font as tkfont
import customtkinter as ctk

FONT_FAMILY = "Yu Gothic"
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

ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY


def find_terminal_font():
    """ターミナル画面用の等幅フォントを検出して返す"""
    try:
        available = set(tkfont.families())
        for f in PREFERRED_TERMINAL_FONTS:
            if f in available:
                return f
    except Exception:
        pass
    return "Consolas"


TERMINAL_FONT_FAMILY = find_terminal_font()


def configure_font_defaults(root):
    ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY
    term_font = find_terminal_font()
    for name in tkfont.names(root):
        if name == "TkFixedFont":
            tkfont.nametofont(name, root=root).configure(family=term_font)
            continue
        tkfont.nametofont(name, root=root).configure(family=FONT_FAMILY)
    root.option_add("*Font", "TkDefaultFont")
