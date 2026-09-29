import tkinter as tk
import customtkinter as ctk

root = ctk.CTk()
tb = ctk.CTkTextbox(root)
tb.pack()
root.update()

events_fired = []

def on_key(e):
    events_fired.append(f"on_key: keysym={e.keysym}, char={repr(e.char)}, state={e.state}")
    return "break"

def on_ctrl_d(e):
    events_fired.append(f"on_ctrl_d: keysym={e.keysym}, char={repr(e.char)}, state={e.state}")
    return "break"

tb.bind("<Key>", on_key)
tb.bind("<Control-d>", on_ctrl_d)
tb.bind("<Control-D>", on_ctrl_d)
tb._textbox.bind("<Control-d>", on_ctrl_d)
tb._textbox.bind("<Control-D>", on_ctrl_d)

tb._textbox.focus_force()
root.update()

# 1. Simulate <Control-KeyPress-d>
tb._textbox.event_generate("<KeyPress>", state=4, keysym="d")
root.update()
print("Simulation 1 (KeyPress state=4 keysym='d'):", events_fired)

events_fired.clear()
# 2. Simulate with NumLock (state=36)
tb._textbox.event_generate("<KeyPress>", state=36, keysym="d")
root.update()
print("Simulation 2 (NumLock state=36):", events_fired)

events_fired.clear()
# 3. Simulate with char=\x04
tb._textbox.event_generate("<KeyPress>", state=4, keysym="d")
root.update()
print("Simulation 3 (char=\\x04):", events_fired)

root.destroy()
