"""Shared font policy for the application UI and terminal."""
import tkinter.font as tkfont
import customtkinter as ctk

FONT_FAMILY = "Yu Gothic"
ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY


def configure_font_defaults(root):
    ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY
    for name in tkfont.names(root):
        tkfont.nametofont(name, root=root).configure(family=FONT_FAMILY)
    root.option_add("*Font", "TkDefaultFont")
