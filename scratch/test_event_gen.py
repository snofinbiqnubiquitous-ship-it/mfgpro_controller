import sys, os
repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import tkinter as tk
import customtkinter as ctk
from order_entry import OrderEntryPanel, read_customer_info_file

root = ctk.CTk()
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

po = panel.fields["purchase_order"]
po._entry.focus_set()
po.delete(0, "end")
po.insert(0, "ABCD")
po._entry.icursor(1)
root.update()

print("Before event_generate:")
print("  po.get():", repr(po.get()))
print("  insert pos:", po._entry.index("insert"))

po._entry.bind("<Delete>", lambda e: print("PO Delete handler fired! Widget:", e.widget), add="+")

po._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()

print("After event_generate:")
print("  po.get():", repr(po.get()))
print("  insert pos:", po._entry.index("insert"))

root.destroy()
