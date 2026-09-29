import datetime
from pathlib import Path
import sys
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from terminal_core import key_sequence, KEY_SEQUENCES
import order_entry
from order_entry import OrderEntryPanel

COLORS = {
    "panel": "#F8FAFC",
    "text": "#1E293B",
    "border": "#CBD5E1",
    "button": "#E2E8F0",
    "hover": "#CBD5E1",
    "accent": "#2563EB",
    "on_accent": "#FFFFFF",
    "accent_hover": "#1D4ED8",
    "error": "#EF4444",
}

class TestTerminalAndOrderEntry(unittest.TestCase):
    def test_ctrl_d_and_delete_sequence(self):
        # 1. key_sequence("Delete") returns KEY_SEQUENCES["Delete"]
        del_seq = key_sequence("Delete")
        self.assertEqual(del_seq, KEY_SEQUENCES["Delete"])
        
        # 2. Ctrl+D (state=4, keysym="d" or "D") returns exact same sequence as Delete
        ctrl_d_seq = key_sequence("d", state=4)
        ctrl_D_seq = key_sequence("D", state=4)
        self.assertEqual(ctrl_d_seq, del_seq)
        self.assertEqual(ctrl_D_seq, del_seq)

    def test_order_entry_reset_button_and_fields(self):
        root = tk.Tk()
        root.withdraw()

        submitted_payloads = []
        def on_sub(p):
            submitted_payloads.append(p)

        panel = OrderEntryPanel(
            root, COLORS, "Meiryo",
            on_submit=on_sub, on_close=lambda: None,
            customers=["テスト顧客A", "テスト顧客B"],
            destinations=["納品先1", "納品先2"],
        )

        # 1. リセットボタンの存在と配置確認
        self.assertTrue(hasattr(panel, "reset_button"))
        self.assertEqual(panel.reset_button.cget("text"), "リセット")
        grid_info = panel.reset_button.grid_info()
        self.assertEqual(grid_info.get("sticky"), "w")
        self.assertEqual(grid_info.get("row"), 2)

        # 2. 送信ボタンの配置確認 (sticky="e", row=2)
        self.assertTrue(hasattr(panel, "send_button"))
        self.assertEqual(panel.send_button.cget("text"), "送信")
        send_grid_info = panel.send_button.grid_info()
        self.assertEqual(send_grid_info.get("sticky"), "e")
        self.assertEqual(send_grid_info.get("row"), 2)

        # 3. 入力欄にテスト値をセット
        panel.fields["customer_name"].set("テスト顧客A")
        panel.fields["ship_to"].set("納品先1")
        panel.fields["purchase_order"].insert(0, "PO12345")
        panel.fields["remarks"].insert("1.0", "特記事項備考")
        panel.fields["so_comment"].insert("1.0", "SOコメントテスト")
        panel._display_address("東京都テスト区1-2-3")

        # Required Date と due date の初期値（または任意設定値）
        init_req_date = panel.fields["required_date"].value
        init_due_date = panel.fields["due_date"].value
        self.assertIsNotNone(init_req_date)
        self.assertIsNotNone(init_due_date)

        # 明細テーブルに値をセット
        panel.item_entries[0]["product_name"].set("BW0100D")
        panel.item_entries[0]["width"].insert(0, "250")
        panel.item_entries[0]["length"].insert(0, "600")
        panel.item_entries[0]["quantity"].insert(0, "2")
        panel.item_entries[0]["price"].insert(0, "130")

        # 4. リセット実行
        panel.reset_fields()

        # 5. Required Date と due date は保持されていることを検証
        self.assertEqual(panel.fields["required_date"].value, init_req_date)
        self.assertEqual(panel.fields["due_date"].value, init_due_date)

        # 6. それ以外の全フィールドがクリアされていることを検証
        self.assertEqual(panel.fields["customer_name"].get(), "")
        self.assertEqual(panel.fields["ship_to"].get(), "")
        self.assertEqual(panel.customer_code_entry.get(), "")
        self.assertEqual(panel.ship_to_code_entry.get(), "")
        self.assertEqual(panel.address_box.get("1.0", "end-1c"), "")
        self.assertEqual(panel.fields["purchase_order"].get(), "")
        self.assertEqual(panel.fields["remarks"].get("1.0", "end-1c"), "")
        self.assertEqual(panel.fields["so_comment"].get("1.0", "end-1c"), "")

        # 明細全行クリア検証
        for r_idx, row in enumerate(panel.item_entries):
            self.assertEqual(row["product_name"].get(), "", f"Row {r_idx} product_name not cleared")
            self.assertEqual(row["width"].get(), "", f"Row {r_idx} width not cleared")
            self.assertEqual(row["length"].get(), "", f"Row {r_idx} length not cleared")
            self.assertEqual(row["quantity"].get(), "", f"Row {r_idx} quantity not cleared")
            self.assertEqual(row["price"].get(), "", f"Row {r_idx} price not cleared")

        for d_idx, desc in enumerate(panel.item_desc_entries):
            self.assertEqual(desc.get(), "", f"Desc {d_idx} not cleared")

        root.destroy()
        print("\nAll unit tests passed successfully!")

if __name__ == "__main__":
    unittest.main()
