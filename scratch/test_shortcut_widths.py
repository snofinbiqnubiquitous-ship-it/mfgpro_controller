import json
import customtkinter as ctk

with open("terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

root = ctk.CTk()
font = ctk.CTkFont(family="Segoe UI", size=12, weight="normal")

results = []
for sc in cfg.get("shortcuts", []):
    name = sc["name"]
    btn_old = ctk.CTkButton(root, text=name, height=28, font=font)
    btn_new = ctk.CTkButton(root, text=name, width=0, height=28, font=font)
    btn_old.pack()
    btn_new.pack()
    root.update_idletasks()
    results.append((name, btn_old.winfo_reqwidth(), btn_new.winfo_reqwidth()))

root.destroy()

print(f"{'Shortcut Name':<20} | {'Before Width':<15} | {'After Width':<15}")
print("-" * 55)
for name, w_old, w_new in results:
    print(f"{name:<20} | {w_old:<15} | {w_new:<15}")

