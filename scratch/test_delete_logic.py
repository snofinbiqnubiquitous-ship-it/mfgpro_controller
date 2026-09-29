import sys, os
repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import tkinter as tk

root = tk.Tk()
e = tk.Entry(root)
e.pack()

def handle_entry_delete(entry, on_change=None):
    try:
        if entry.selection_present():
            first = entry.index("sel.first")
            last = entry.index("sel.last")
            entry.delete(first, last)
        else:
            ins = entry.index("insert")
            text_len = len(entry.get())
            if ins < text_len:
                entry.delete(ins)
            elif ins > 0:
                entry.delete(ins - 1)
        if callable(on_change):
            on_change()
        return "break"
    except Exception:
        return None

e.bind("<Delete>", lambda evt: handle_entry_delete(e))
e.bind("<KP_Delete>", lambda evt: handle_entry_delete(e))

# Test 1: Typing 'ABC' and cursor at end (index 3). Press Delete.
e.insert(0, "ABC")
e.icursor("end")
root.update()
print("Before Delete at end:", repr(e.get()), "insert at:", e.index("insert"))
handle_entry_delete(e)
print("After Delete at end:", repr(e.get()), "insert at:", e.index("insert"))
assert e.get() == "AB"

# Test 2: Cursor at beginning (index 0). Press Delete.
e.icursor(0)
print("Before Delete at start:", repr(e.get()), "insert at:", e.index("insert"))
handle_entry_delete(e)
print("After Delete at start:", repr(e.get()), "insert at:", e.index("insert"))
assert e.get() == "B"

# Test 3: Selection present. Press Delete.
e.delete(0, "end")
e.insert(0, "HELLO")
e.selection_range(0, "end")
print("Before Delete on selection:", repr(e.get()))
handle_entry_delete(e)
print("After Delete on selection:", repr(e.get()))
assert e.get() == ""

root.destroy()
print("ALL HELPER LOGIC TESTS PASSED!")
