import sys, os
repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import tkinter as tk
import customtkinter as ctk
from order_entry import OrderEntryPanel, read_customer_info_file

root = ctk.CTk()
root.geometry("600x600")
root.update()

info = read_customer_info_file()
panel = OrderEntryPanel(
    root,
    colors={"panel": "#FFF", "text": "#000", "border": "#CCC", "button": "#EEE", "hover": "#DDD", "accent": "#00F", "on_accent": "#FFF", "accent_hover": "#00A", "error": "#F00", "accent_light": "#E0F"},
    font_family="Segoe UI",
    on_submit=lambda p: None,
    on_close=lambda: None,
    customer_info=info,
    item_list_data={"PROD1": "Description 1"}
)
panel.pack(fill="both", expand=True)
root.update()

# Test 1: customer_name
cn = panel.fields["customer_name"]
cn._entry.focus_set()
cn.set("TEST")
root.update()
print("CN initial:", repr(cn.get()), repr(panel.customer_code_entry.get()))

# Select all in cn._entry and press Delete
cn._entry.selection_range(0, "end")
root.update()
cn._entry.event_generate("<KeyPress>", keysym="Delete", keycode=46)
cn._entry.event_generate("<KeyRelease>", keysym="Delete", keycode=46)
root.update()
print("CN after Delete on all-selection:", repr(cn.get()), repr(panel.customer_code_entry.get()))

# Test 2: product_name
pn = panel.item_entries[0]["product_name"]
pn._entry.focus_set()
pn.set("PROD1")
panel._on_product_selected(0, "PROD1")
root.update()
print("PN initial:", repr(pn.get()), repr(panel.item_desc_entries[0].get()))

pn._entry.selection_range(0, "end")
root.update()
pn._entry.event_generate("<KeyPress>", keysym="Delete", keycode=46)
pn._entry.event_generate("<KeyRelease>", keysym="Delete", keycode=46)
root.update()
print("PN after Delete on all-selection:", repr(pn.get()), repr(panel.item_desc_entries[0].get()))

root.destroy()
