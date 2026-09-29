import sys, os
repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import tkinter as tk
import customtkinter as ctk
from order_entry import OrderEntryPanel, read_customer_info_file
from terminal_core import key_sequence, KEY_SEQUENCES

# --- 1. Terminal Core Tests ---
print("--- 1. Testing terminal_core.py KEY_SEQUENCES ---")
assert key_sequence("Delete") == "\b", f"Expected '\\b', got {repr(key_sequence('Delete'))}"
assert key_sequence("KP_Delete") == "\b", f"Expected '\\b', got {repr(key_sequence('KP_Delete'))}"
assert key_sequence("BackSpace") == "\b", f"Expected '\\b', got {repr(key_sequence('BackSpace'))}"
print("terminal_core KEY_SEQUENCES PASS!")

# --- 2. Sidebar UI Tests ---
print("--- 2. Testing order_entry.py Delete logic ---")
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

# 2-1. Purchase Order (CTkEntry) - end delete
po = panel.fields["purchase_order"]
po._entry.focus_set()
po.delete(0, "end")
po.insert(0, "PO12345")
po._entry.icursor("end")
root.update()
po._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert po.get() == "PO1234", f"Expected PO1234, got {po.get()}"
print("2-1. PO end delete PASS")

# 2-2. Product Name (HighlightComboBox) & Value line
pn = panel.item_entries[0]["product_name"]
pn._entry.focus_set()
pn.set("PROD1")
panel._on_product_selected(0, "PROD1")
root.update()
assert panel.item_desc_entries[0].get() == "Description 1"
# Delete at end
pn._entry.icursor("end")
pn._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert pn.get() == "PROD", f"Expected PROD, got {pn.get()}"
assert panel.item_desc_entries[0].get() == "", f"Expected empty desc, got {panel.item_desc_entries[0].get()}"
print("2-2. Product name & value update PASS")

# 2-3. Delete on quantity (CTkEntry)
qty = panel.item_entries[0]["quantity"]
qty._entry.focus_set()
qty.delete(0, "end")
qty.insert(0, "999")
qty._entry.icursor("end")
root.update()
qty._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert qty.get() == "99", f"Expected 99, got {qty.get()}"
print("2-3. Delete quantity PASS")

# 2-4. Remarks (CTkTextbox)
rem = panel.fields["remarks"]
rem._textbox.focus_set()
rem.delete("1.0", "end")
rem.insert("1.0", "NOTE")
rem._textbox.mark_set("insert", "end-1c")
root.update()
rem._textbox.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert rem.get("1.0", "end").strip() == "NOT", f"Expected NOT, got {rem.get('1.0', 'end').strip()}"
print("2-4. Remarks textbox delete PASS")

# 2-5. Middle cursor Delete in PO
po._entry.focus_set()
po.delete(0, "end")
po.insert(0, "ABCD")
po._entry.icursor(1)  # between A and B
root.update()
po._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert po.get() == "ACD", f"Expected ACD, got {po.get()}"
print("2-5. Middle cursor delete PASS")

# 2-6. Selection Delete in PO
po.delete(0, "end")
po.insert(0, "ABCD")
po._entry.selection_range(0, "end")
root.update()
po._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert po.get() == "", f"Expected empty, got {po.get()}"
print("2-6. Full selection delete PASS")

# 2-7. Customer Name & Code update
cn = panel.fields["customer_name"]
cn._entry.focus_set()
cn.set("CUST_TEST")
root.update()
cn._entry.icursor("end")
cn._entry.event_generate("<KeyPress>", keysym="Delete")
root.update()
assert cn.get() == "CUST_TES", f"Expected CUST_TES, got {cn.get()}"
print("2-7. Customer name delete PASS")

root.destroy()
print("========================================")
print("ALL TESTS PASSED WITH 100% SUCCESS!")
print("========================================")
