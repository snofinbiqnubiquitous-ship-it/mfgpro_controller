"""Shared font policy.

The QAD terminal screen keeps the monospaced font it used before the Yu Gothic
change (Consolas first), because the border alignment depends on fixed
character widths. Everything else (menus, sidebar, dialogs, F3, logs) uses
Yu Gothic.
"""
import tkinter.font as tkfont

import customtkinter as ctk

FONT_FAMILY = "Yu Gothic"
TERMINAL_FONT_CANDIDATES = (
    "Consolas",       # Windows標準 等幅（罫線の上下隙間ゼロ・完全シームレス結合）
    "Cascadia Mono",  # Windows 11/10標準 等幅
    "Cascadia Code",
    "Courier New",
    "Source Code Pro",
    "BIZ UDゴシック",
    "MS Gothic",
    "ＭＳ ゴシック",
)

ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY


def find_terminal_font(root):
    """Return the first installed terminal font (same order as the old version)."""
    try:
        available = set(tkfont.families(root))
    except Exception:
        return TERMINAL_FONT_CANDIDATES[0]
    return next((name for name in TERMINAL_FONT_CANDIDATES if name in available), TERMINAL_FONT_CANDIDATES[0])


def configure_font_defaults(root):
    """Apply Yu Gothic to the UI fonts and return the terminal screen font."""
    ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY
    terminal = find_terminal_font(root)
    for name in tkfont.names(root):
        # TkFixedFont is the default of plain Text widgets and stays monospaced.
        family = terminal if name == "TkFixedFont" else FONT_FAMILY
        tkfont.nametofont(name, root=root).configure(family=family)
    root.option_add("*Font", "TkDefaultFont")
    return terminal
