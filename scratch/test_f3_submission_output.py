import sys, os
repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import tkinter as tk
import customtkinter as ctk
from order_entry import OrderOutputTerminalWindow

root = ctk.CTk()
root.geometry("200x200")

term = OrderOutputTerminalWindow(root, colors={
    "panel": "#1E293B",
    "text": "#F8FAFC",
    "border": "#334155",
    "accent": "#0284C7",
    "hover": "#0369A1",
    "dim": "#64748B",
    "card": "#0F172A",
})

# テスト用注文ペイロード（指標B・C・Step5を満たすサンプルデータ）
sample_payload = {
    "customer_name": "ダイニック株式会社",
    "customer_code": "20019500",
    "ship_to": "那須塩原工場",
    "ship_to_code": "20019583",
    "address": "栃木県那須塩原市...",
    "required_date": "2026-10-09",
    "due_date": "2026-10-07",
    "purchase_order": "YPW284",
    "remarks": "10/9 DC",
    "so_comment": "【請求書】郵送不要（念のためEmail送信）\n【納品書】原本送付（荷物に添付）\n【受領書】不要\n【荷姿】指定パレットで出荷",
    "items": [
        {
            "product_name": "15666",
            "width": "105",
            "length": "500",
            "quantity": "2",
            "price": "16800"
        }
    ]
}

term.append_submission(sample_payload, item_list_data={"15666": "DISSOLVABLE PPR SC"})
root.update()

# テキストボックスの内容を取り出してコンソールに出力
rendered_text = term.textbox._textbox.get("1.0", "end")
print("=================== RENDERED TERMINAL OUTPUT ===================")
print(rendered_text)
print("================================================================")

root.destroy()
print("TEST SUCCESSFUL!")
