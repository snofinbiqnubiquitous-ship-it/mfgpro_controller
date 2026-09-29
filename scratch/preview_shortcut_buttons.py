import sys, os
import tkinter as tk
import customtkinter as ctk

ctk.set_appearance_mode("Light")
root = ctk.CTk()
root.geometry("700x300")
root.title("Shortcut Buttons Width Comparison")

# サンプルショートカット
samples = ["7.1.1", "PO照会", "受注登録", "SO", "売上分析マクロ"]

lbl1 = ctk.CTkLabel(root, text="【現在: デフォルト幅 (width=140)】", font=("Segoe UI", 13, "bold"))
lbl1.pack(anchor="w", padx=15, pady=(15, 5))

frame1 = ctk.CTkScrollableFrame(root, orientation="horizontal", height=40, fg_color="#F1F5F9")
frame1.pack(fill="x", padx=15, pady=5)
for s in samples:
    btn = ctk.CTkButton(
        frame1, text=s, height=28,
        fg_color="#E2E8F0", hover_color="#CBD5E1", text_color="#0F172A",
        font=("Segoe UI", 12), corner_radius=6
    )
    btn.pack(side="left", padx=3, pady=2)

lbl2 = ctk.CTkLabel(root, text="【改善後: 表示名サイズに自動フィット (width=0)】", font=("Segoe UI", 13, "bold"))
lbl2.pack(anchor="w", padx=15, pady=(20, 5))

frame2 = ctk.CTkScrollableFrame(root, orientation="horizontal", height=40, fg_color="#F1F5F9")
frame2.pack(fill="x", padx=15, pady=5)
for s in samples:
    btn = ctk.CTkButton(
        frame2, text=s, height=28, width=0,
        fg_color="#E2E8F0", hover_color="#CBD5E1", text_color="#0F172A",
        font=("Segoe UI", 12), corner_radius=6
    )
    btn.pack(side="left", padx=3, pady=2)

root.update()

# Save image
from PIL import ImageGrab
x = root.winfo_rootx()
y = root.winfo_rooty()
w = root.winfo_width()
h = root.winfo_height()
img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
artifact_dir = r"C:\Users\0138018\.gemini\antigravity\brain\5c10a7ef-9503-4839-a5af-f8479758e34e"
img_path = os.path.join(artifact_dir, "shortcut_buttons_width_comparison.png")
img.save(img_path)
print("Saved comparison image to:", img_path)

root.destroy()
