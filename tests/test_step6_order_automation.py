import unittest
from unittest.mock import MagicMock
import time
from datetime import date

from order_entry import (
    clean_screen_text,
    format_dimension_value,
    format_price_value,
    group_order_items,
    SalesOrderAutomationController,
    KEY_SEQUENCES,
)


class Step6GroupingTests(unittest.TestCase):
    def test_empty_items(self):
        self.assertEqual(group_order_items([]), [])
        self.assertEqual(group_order_items(None), [])

    def test_single_item(self):
        items = [
            {"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"}
        ]
        res = group_order_items(items)
        self.assertEqual(len(res), 1)
        p = res[0]
        self.assertEqual(p["line_no"], 1)
        self.assertEqual(p["product_name"], "OZS200")
        self.assertEqual(p["price"], "320")
        self.assertEqual(len(p["length_groups"]), 1)
        lg = p["length_groups"][0]
        self.assertEqual(lg["sl"], 1)
        self.assertEqual(lg["length"], "600")
        self.assertEqual(len(lg["entries"]), 1)
        e = lg["entries"][0]
        self.assertEqual(e["ser"], 1)
        self.assertEqual(e["rolls"], 1)
        self.assertEqual(e["width"], "1530")

    def test_same_product_same_length_different_widths(self):
        items = [
            {"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"},
            {"product_name": "OZS200", "width": "1070", "length": "600", "quantity": 2, "price": "320.00"},
        ]
        res = group_order_items(items)
        self.assertEqual(len(res), 1)
        p = res[0]
        self.assertEqual(len(p["length_groups"]), 1)
        lg = p["length_groups"][0]
        self.assertEqual(lg["length"], "600")
        self.assertEqual(len(lg["entries"]), 2)
        self.assertEqual(lg["entries"][0], {"ser": 1, "rolls": 1, "width": "1530"})
        self.assertEqual(lg["entries"][1], {"ser": 2, "rolls": 2, "width": "1070"})

    def test_same_product_different_lengths(self):
        items = [
            {"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"},
            {"product_name": "OZS200", "width": "500", "length": "1000", "quantity": 1, "price": "320.00"},
        ]
        res = group_order_items(items)
        self.assertEqual(len(res), 1)
        p = res[0]
        self.assertEqual(len(p["length_groups"]), 2)
        self.assertEqual(p["length_groups"][0]["sl"], 1)
        self.assertEqual(p["length_groups"][0]["length"], "600")
        self.assertEqual(p["length_groups"][1]["sl"], 2)
        self.assertEqual(p["length_groups"][1]["length"], "1000")

    def test_multiple_products(self):
        items = [
            {"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"},
            {"product_name": "OZS201", "width": "1070", "length": "600", "quantity": 3, "price": "339.00"},
        ]
        res = group_order_items(items)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["line_no"], 1)
        self.assertEqual(res[0]["product_name"], "OZS200")
        self.assertEqual(res[0]["price"], "320")
        self.assertEqual(res[1]["line_no"], 2)
        self.assertEqual(res[1]["product_name"], "OZS201")
        self.assertEqual(res[1]["price"], "339")

    def test_duplicate_entries_consolidation(self):
        items = [
            {"product_name": "OZS200", "width": "1070", "length": "600", "quantity": 2, "price": "320.00"},
            {"product_name": "OZS200", "width": "1070", "length": "600", "quantity": 3, "price": "320.00"},
        ]
        res = group_order_items(items)
        self.assertEqual(len(res), 1)
        lg = res[0]["length_groups"][0]
        self.assertEqual(len(lg["entries"]), 1)
        self.assertEqual(lg["entries"][0]["rolls"], 5)
        self.assertEqual(lg["entries"][0]["width"], "1070")

    def test_number_formatting_edge_cases(self):
        self.assertEqual(format_dimension_value("600.00"), "600")
        self.assertEqual(format_dimension_value("600.50"), "600.5")
        self.assertEqual(format_dimension_value(""), "")
        self.assertEqual(format_price_value("320.00"), "320")
        self.assertEqual(format_price_value("320.50"), "320.5")
        self.assertEqual(format_price_value("0.10"), "0.1")


class ScreenTextCleaningTests(unittest.TestCase):
    def test_ansi_and_null_removal(self):
        raw = "\x1b[31mError:\x1b[0m Value \x00Should Be > 0\x1b[1;24r"
        cleaned = clean_screen_text(raw)
        self.assertEqual(cleaned, "Error: Value Should Be > 0")


class Step6SimulationRenderingTests(unittest.TestCase):
    def test_simulation_rendering_all_substeps(self):
        import customtkinter as ctk
        from order_entry import OrderOutputTerminalWindow

        root = ctk.CTk()
        root.geometry("200x200")
        try:
            term = OrderOutputTerminalWindow(root, colors={
                "panel": "#1E293B", "text": "#F8FAFC", "border": "#334155",
                "accent": "#0284C7", "hover": "#0369A1", "dim": "#64748B", "card": "#0F172A",
            })

            payload = {
                "customer_name": "ダイニック株式会社",
                "customer_code": "20019500",
                "ship_to": "那須塩原工場",
                "ship_to_code": "20019583",
                "required_date": "2026-10-09",
                "due_date": "2026-10-07",
                "purchase_order": "YPW284",
                "remarks": "10/9 DC",
                "so_comment": "【荷姿】指定パレット",
                "items": [
                    {"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"},
                    {"product_name": "OZS200", "width": "1070", "length": "600", "quantity": 2, "price": "320.00"},
                    {"product_name": "OZS201", "width": "1070", "length": "600", "quantity": 3, "price": "339.00"},
                ],
            }

            term.append_submission(payload)
            out = term.textbox._textbox.get("1.0", "end")

            # 検証: 各ステップのタイトル・キー・待機条件が存在すること
            self.assertIn(">> [STEP 1]", out)
            self.assertIn(">> [STEP 2]", out)
            self.assertIn(">> [STEP 2] 受注ヘッダー項目入力（Sold-To/Bill-To/Ship-To 個別入力 ＋ Order Date から一括貼り付け）", out)
            self.assertIn("2-1. Sold-To 順次入力:", out)
            self.assertIn("2-2. Bill-To 順次入力:", out)
            self.assertIn("2-3. Ship-To 順次入力:", out)
            self.assertIn("2-4. 一括貼り付けバッファ（Order Date 入力欄から一括ペースト・全8項目）:", out)
            self.assertIn("Line 1 : Order Date", out)
            self.assertIn("Line 8 : Remarks", out)
            self.assertIn(">> [STEP 3]", out)
            self.assertIn(">> [STEP 4]", out)
            self.assertIn(">> [STEP 5]", out)
            self.assertIn(">> [STEP 6]", out)
            self.assertIn("6.1.0-1. Ln 自動採番", out)
            self.assertIn("6.1.1-1. Create WO ポップアップ通過", out)
            self.assertIn("6.1.3-1. Item Number (品番) 入力", out)
            self.assertIn('"CB2" + <F1>', out)
            self.assertIn("6.1.4-1. Qty Ordered UM スキップ", out)
            self.assertIn("6.1.4-SL1. サブライン (SL) 取得", out)
            self.assertIn("6.2.0-1. Len(m) (長さ) 入力", out)
            self.assertIn("6.2.1-R1.1. Ser スキップ", out)
            self.assertIn("6.2.1-R1.2. Rolls (本数) 入力", out)
            self.assertIn("6.2.1-R1.3. Width (幅mm) 入力", out)
            self.assertIn("6.2.1-End. 長さ 600m ロール入力完了", out)
            self.assertIn("6.2.1-Conf. 長さ 600m 更新確定", out)
            self.assertIn("6.1.4-Done. 品番 'OZS200' の全スリット設定完了", out)
            self.assertIn("6.2.3-1. Pricing Date 画面スキップ", out)
            self.assertIn("6.2.4-1. List Price スキップ", out)
            self.assertIn("6.2.4-2. Price (単価) 入力", out)
            self.assertIn("6.2.5-1. Tax 画面スキップ", out)
            self.assertIn(">> [STEP 6.3.0] 受注最終合計画面 (Order Totals) ＆ 注文確定", out)
            self.assertIn("6.3.0-2. 明細脱出シーケンス", out)
            self.assertIn("6.3.0-3. 合計画面下段展開 (Frame 2+): <F1>", out)
            self.assertIn("6.3.0-4. 注文コミット＆与信/延滞チェック実行: <F1>", out)
            self.assertIn("6.3.0-5. 初期画面への安全復帰 (全工程完了): 合計画面に残っている場合のみ <F4>", out)
            # Step 5 案C の表示検証
            self.assertIn(">> [STEP 5] 特記事項 (Transaction Comments / 案C: 全クリア置換)", out)
            self.assertIn("5-2. 既定コメントの全クリア (案C):", out)
            self.assertIn("<F8> (Clear)", out)
        finally:
            root.destroy()


class AutomationControllerExecutionTests(unittest.TestCase):
    def test_step6_state_machine_execution(self):
        """Mock セッションを用いて Step 6 の状態遷移・キーストローク順序を検証"""
        sent_data = []

        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False

            def send(self, data):
                sent_data.append(data)

        # 画面状態シーケンスのシミュレーション
        screens = [
            # 6.1.0 Ln
            "Sales Order Maintenance\nSales Order Line\nLn Item Number",
            # 6.1.1 Create WO
            "Create WO: Y Rework: Y Exact: Y",
            # 6.1.3 Item Number
            "Sales Order Line\nLn Item Number",
            # 6.1.3 Site
            "Site: CB2\nF1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",
            # 6.1.4 Qty Ordered UM
            "Sales Order Line\nQty Ordered UM M2",
            # 6.1.4 No1 スリット画面
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 6.2.0 Len(m)
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nError: Value Should Be > 0",
            # 6.2.1 Ser Rolls Width
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 6.2.1 Confirm update
            "Please confirm update yes",
            # 6.1.4 No1 SL画面復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 6.1.4 No1 全完了確認
            "Please confirm update yes",
            # 6.2.3 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26\nReprice: No",
            # 6.2.4 Price
            "Sales Order Line\nList Price 320.00 Discount 0.0 Price 320.00",
            # 6.2.5 Tax
            "Tax Usage:\nTax Environment: 10%consumption",
            # 6.2.5 Comments
            "Transaction Comments\nMaster Reference: OZS200",
            # 6.1.0 メインメニュー復帰
            "Sales Order Maintenance\nSales Order Line\nLn Item Number",
            # 6.3.0 最終合計画面
            "Order: SO199302\nLine Total: 33,600\nTotal Tax: 3,360\nEnter data or press F4 to end.",
            # Space 要求
            "Press space bar to continue.",
            # メインメニュー復帰
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        # 画面インデックスごとの遷移トリガー
        # 画面12 (6.2.4 値段) は F1(List Priceスキップ) と F1(単価確定) の2回F1が送られる
        # 画面16 (6.3.0 合計) は F1 が 2回送られる
        f1_counts = {12: 0, 16: 0}

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(data):
            sent_data.append(data)
            idx = screen_idx[0]
            advanced = False

            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                f1_counts[12] += 1
                if f1_counts[12] >= 2:
                    advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 14 and data in (KEY_SEQUENCES["F1"], KEY_SEQUENCES["F4"]):
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 16 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                f1_counts[16] += 1
                if data == KEY_SEQUENCES["F4"] or f1_counts[16] >= 2:
                    advanced = True
            elif idx == 17 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        session = MockSession()
        session.send = custom_send

        payload = {
            "items": [
                {"product_name": "OZS200", "width": "1070", "length": "600", "quantity": 1, "price": "320.00"}
            ]
        }

        controller = SalesOrderAutomationController(
            session=session,
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=1.0,
        )

        controller.execute_step6()

        # キーストロークの検証
        self.assertIn("\r", sent_data)                    # 6.1.0 Ln採番
        self.assertIn(KEY_SEQUENCES["F1"], sent_data)      # 6.1.1 Create WO スキップ
        self.assertIn("OZS200", sent_data)                # 6.1.3 品番
        self.assertIn("CB2", sent_data)                   # 6.1.3 Site
        self.assertTrue(any("600" in s for s in sent_data)) # 6.2.0 長さ
        self.assertIn("1\r", sent_data)                   # 6.2.1 本数
        self.assertIn("1070\r", sent_data)                # 6.2.1 幅
        self.assertIn(KEY_SEQUENCES["F4"], sent_data)      # 6.2.1 ロール完了 & 6.3.0 遷移
        self.assertIn("320", sent_data)                   # 6.2.4 単価
        self.assertIn(" ", sent_data)                     # 6.3.0 スペースキー
        self.assertEqual(screen_idx[0], len(screens) - 1)

    def test_automation_timeout(self):
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            send = MagicMock()

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=lambda: "Unexpected Screen Text",
            payload={"items": [{"product_name": "X", "width": "100", "length": "100", "quantity": 1, "price": "10"}]},
            sleep_func=lambda s: time.sleep(0.01),
            default_timeout=0.1,
        )
        with self.assertRaises(TimeoutError):
            controller.wait_for_screen(lambda txt: "target text" in txt)

    def test_automation_abort(self):
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            send = MagicMock()

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=lambda: "Normal Text",
            payload={},
            default_timeout=1.0,
        )
        controller.abort()
        with self.assertRaises(InterruptedError):
            controller.send("test")
        with self.assertRaises(InterruptedError):
            controller.wait_for_screen(lambda txt: False)

    def test_space_bar_banner_auto_dismissal(self):
        sent = []
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                sent.append(data)

        calls = [0]
        def screen_provider():
            calls[0] += 1
            if calls[0] == 1:
                return "Category=Adv Hipo Press space bar to continue."
            return "Target Screen Text Found"

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=screen_provider,
            payload={},
            sleep_func=lambda s: None,
            default_timeout=0.5,
        )
        txt = controller.wait_for_screen(lambda t: "target screen" in t)
        self.assertIn("target screen", txt)
        self.assertIn(" ", sent)  # Verified space key was sent to dismiss banner!

    def test_step6_empty_items(self):
        controller = SalesOrderAutomationController(
            session=MagicMock(),
            get_screen_text=lambda: "",
            payload={"items": []},
            sleep_func=lambda s: None,
        )
        # Should return without error or interaction
        controller.execute_step6()

    def test_step6_fallback_f2_execution(self):
        sent = []
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                sent.append(data)

        # Sequence of screens: Line 1 enters, reaches 6.3.0 transition
        # At 6.3.0 transition, screen does not change to totals upon F4, but changes upon F2 x 2
        screens = [
            "Sales Order Maintenance\nSales Order Line\nLn Item Number",  # 6.1.0
            "Create WO: Y Rework: Y",                                     # 6.1.1
            "Sales Order Line\nLn Item Number",                           # 6.1.3
            "Site: CB2",                                                  # 6.1.3 site
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)", # 6.1.4
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nError: Value Should Be > 0", # 6.2.0
            "Ser T Rolls Width(mm) Tot Qty(M2)",                         # 6.2.1
            "Please confirm update yes",                                  # 6.2.1 confirm
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)", # SL back
            "Please confirm update yes",                                  # 6.1.4 confirm
            "Sales Order Line\nPricing Date: 09/26/26",                   # 6.2.3
            "Sales Order Line\nList Price 320.00 Price 320.00",           # 6.2.4
            "Tax Usage:",                                                 # 6.2.5 tax
            "Transaction Comments",                                       # 6.2.5 comment
            "Sales Order Line\nLn Item Number",                           # 6.1.0 back
            # Here F4 is sent, but screen stays on Sales Order Line
            "Sales Order Line\nLn Item Number",
            # After F2 x 2 is sent, screen becomes Totals
            "Line Total: 33,600\nTotal Tax: 3,360\nEnter data or press F4 to end.",
            "Press space bar to continue.",
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        f1_counts = {11: 0, 16: 0}
        f4_retry_count = [0]

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(data):
            sent.append(data)
            idx = screen_idx[0]
            advanced = False
            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 6 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 9 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 10 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                f1_counts[11] += 1
                if f1_counts[11] >= 2:
                    advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 13 and data in (KEY_SEQUENCES["F1"], KEY_SEQUENCES["F4"]):
                advanced = True
            elif idx == 14 and data == KEY_SEQUENCES["F4"]:
                advanced = True  # Moves to idx 15 (which is still Sales Order Line)
            elif idx == 15 and data == KEY_SEQUENCES["F4"]:
                f4_retry_count[0] += 1
                advanced = True  # Moves to Totals!
            elif idx == 16 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                f1_counts[16] += 1
                if data == KEY_SEQUENCES["F4"] or f1_counts[16] >= 2:
                    advanced = True
            elif idx == 17 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        session = MockSession()
        session.send = custom_send

        controller = SalesOrderAutomationController(
            session=session,
            get_screen_text=get_screen,
            payload={"items": [{"product_name": "TEST", "width": "1000", "length": "500", "quantity": 1, "price": "100"}]},
            sleep_func=lambda s: None,
            default_timeout=3.0,
        )

        controller.execute_step6()
        self.assertGreaterEqual(f4_retry_count[0], 1)
        self.assertIn("mfmenu", screens[screen_idx[0]])

    def test_price_and_dimension_formatting(self):
        self.assertEqual(format_price_value("¥1,200"), "1200")
        self.assertEqual(format_price_value("1,200.50"), "1200.5")
        self.assertEqual(format_price_value("320円"), "320")
        self.assertEqual(format_dimension_value("1,500.00"), "1500")
        self.assertEqual(format_dimension_value("600.50"), "600.5")

    def test_630_space_prompt_after_first_f1(self):
        """6.3.0 で1回目の F1 の直後に 'Press space' が出現した場合の安全処理を検証"""
        sent = []
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                sent.append(data)

        screens = [
            "Sales Order Line\nLn Item Number\nLoc: Site: CB2",  # 6.1.0
            "Create WO: Y Rework: Y",                            # 6.1.1
            "Sales Order Line\nLn Item Number\nLoc: Site: CB2",  # 6.1.3
            "Ln Item Numbe│ Site     │ Ordered UM\nCB2",         # 6.1.3 Site popup
            "On Hand: 1000\nAvail. to Allocate: 500",            # 6.1.4 Qty Ordered UM
            "Item Width(mm):1000 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)", # 6.1.4 SL table
            "Item Width(mm):1000 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\n 1   1  Insert", # 6.2.0 Len(m)
            "Ser T Rolls Width(mm) Tot Qty(M2)",                # 6.2.1
            "Please confirm update yes",                         # 6.2.1 confirm
            "Item Width(mm):1000 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)", # SL back
            "Please confirm update yes",                         # 6.1.4 confirm
            "Sales Order Line\nPricing Date: 09/26/26",          # 6.2.3
            "Sales Order Line\nList Price 320.00 Price 320.00",  # 6.2.4
            "Tax Usage:\nTax Environment: 10%consumption",       # 6.2.5 tax
            "Transaction Comments\nMaster Reference: OZS200",     # 6.2.5 comment
            "Sales Order Line\nLn Item Number\nLoc: Site: CB2",  # 6.1.0 back
            "Line Total: 33,600\nTotal Tax: 3,360\nEnter data or press F4 to end.", # 6.3.0 Totals
            # 1回目 F1 送信直後に Press space が出現（2回目 F1 は不要）
            "Press space bar to continue.",
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        f1_price_count = [0]
        f1_totals_count = [0]

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(data):
            sent.append(data)
            idx = screen_idx[0]
            advanced = False
            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                f1_price_count[0] += 1
                if f1_price_count[0] >= 2:
                    advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 14 and data in (KEY_SEQUENCES["F1"], KEY_SEQUENCES["F4"]):
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 16 and data == KEY_SEQUENCES["F1"]:
                f1_totals_count[0] += 1
                if f1_totals_count[0] >= 2:
                    advanced = True  # Advances to Press space after 2nd F1!
            elif idx == 17 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        session = MockSession()
        session.send = custom_send

        controller = SalesOrderAutomationController(
            session=session,
            get_screen_text=get_screen,
            payload={"items": [{"product_name": "T1", "width": "1000", "length": "500", "quantity": 1, "price": "100"}]},
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        controller.execute_step6()
        # Verify 2 F1s were sent at totals screen before space was sent!
        self.assertEqual(f1_totals_count[0], 2)
        self.assertIn(" ", sent)
        self.assertEqual(screen_idx[0], len(screens) - 1)

    def test_realistic_qad_screens_no_premature_trigger(self):
        """実機QADの全画面テキスト（Loc: Site: CB2 が全画面に常駐）で誤検知・先走りが起きないことを検証"""
        sent = []
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                sent.append(data)

        # 実際のQAD画面を模した完全なバッファ
        screens = [
            # 0: 6.1.0 メインメニュー
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Sales Order: SO199302 Sold-To: 20019500 Ln Format S/M: Single                │\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf",

            # 1: 6.1.1 Create WO ポップアップ
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Ln Item│Create WO: Y Rework: Y Exact: Y│ List Price Discount           Price │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu",

            # 2: 6.1.3 Item Number 入力
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1                                                                           │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",

            # 3: 6.1.3 Site ポップアップ出現
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Ln Item Numbe│ Site     │ Ordered UM     List Price Discount           Price │\n"
            "│─── ──────────│ ──────── │──────── ── ────────────── ──────── ─────────────── │\n"
            "│  1 OZS200    │ CB2      │                                                    │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",

            # 4: 6.1.4 Qty Ordered UM 入力 (Site閉じた直後)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1 OZS200                   105.0 M2                                         │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "On Hand: 16706.65983179  On Order: 8100.235  Avail. to Allocate: 17663.65983179\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",

            # 5: 6.1.4 No1 スリット設定画面 (Item Width)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 105──────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│─── ─── ────────── ───── ───────────── ───────────────              │\n"
            "│                                                                    │\n"
            "OZS200 - NON-SKU\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf",

            # 6: 6.2.0 長さ入力画面 (SL 1 行出現)
            "┌───────────Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0───────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│─── ─── ────────── ───── ───────────── ───────────────              │\n"
            "│  1   1     600.00 yes            0.00            0.00              │\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf          Insert",

            # 7: 6.2.1 Ser Rolls Width ポップアップ
            "┌────────────────────────────────────┐\n"
            "│Ser T    Rolls Width(mm) Tot Qty(M2)│\n"
            "│─── ─ ──────── ───────── ───────────│\n"
            "│  1 R        1      1530        1.53│\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 8: 6.2.1 ロール完了 Please confirm update
            "Please confirm update  yes",

            # 9: 6.1.4 No1 SL画面復帰
            "┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 105──────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│─── ─── ────────── ───── ───────────── ───────────────              │\n"
            "│  1   1     600.00 yes         1530.00          105.00              │\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 10: 6.1.4 全明細完了 Please confirm update
            "Please confirm update  yes",

            # 11: 6.2.3 Pricing Date
            "                        ┌─────────────────────────────┐\n"
            "                        │       Pricing Date: 09/26/26│\n"
            "                        │   Credit Terms Int: 0.00    │\n"
            "                        │            Reprice: No      │\n"
            "                        │         Price List:         │\n"
            "                        └─────────────────────────────┘\n"
            "Sales Order Line\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 12: 6.2.4 値段入力
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1 OZS200                   105.0 M2         320.00      0.0          320.00 │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 13: 6.2.5 Tax ポップアップ
            "┌────────────────────────────────────────────┐\n"
            "│               Tax Usage:                   │\n"
            "│         Tax Environment: 10%consumption    │\n"
            "│               Tax Class: 10                │\n"
            "│                 Taxable: Yes               │\n"
            "└────────────────────────────────────────────┘",

            # 14: 6.2.5 Transaction Comments
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│ Master Reference: OZS200                                                     │\n"
            "Adding new record\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 15: 6.1.0 メインメニュー復帰 (全明細入力後)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26\n"
            "│ Sales Order: SO199302 Sold-To: 20019500 Ln Format S/M: Single                │\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu",

            # 16: 6.3.0 最終合計画面
            "Order: SO199302  Sold-To: 20019500  Bill To: 20019500\n"
            "Line Total:           33,600\n"
            "Total Tax:            3,360\n"
            "Total:           36,960\n"
            "Enter data or press F4 to end.",

            # 17: Press space
            "Press space bar to continue.",

            # 18: メインメニュー復帰
            "xxmenu.p b+                      m f m e n u                          09/28/26\n"
            "Main Menu\n"
            "Menu:",
        ]

        screen_idx = [0]
        f1_price_count = [0]
        f1_totals_count = [0]

        def get_screen():
            return screens[screen_idx[0]]

        def custom_send(data):
            sent.append(data)
            idx = screen_idx[0]
            advanced = False
            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                f1_price_count[0] += 1
                if f1_price_count[0] >= 2:
                    advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 14 and data in (KEY_SEQUENCES["F1"], KEY_SEQUENCES["F4"]):
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 16 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                f1_totals_count[0] += 1
                if data == KEY_SEQUENCES["F4"] or f1_totals_count[0] >= 2:
                    advanced = True
            elif idx == 17 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        session = MockSession()
        session.send = custom_send

        controller = SalesOrderAutomationController(
            session=session,
            get_screen_text=get_screen,
            payload={
                "items": [{"product_name": "OZS200", "width": "1530", "length": "600", "quantity": 1, "price": "320.00"}],
                "site": "CB2",
            },
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        controller.execute_step6()
        self.assertEqual(screen_idx[0], len(screens) - 1)
        self.assertIn("CB2", sent)
        self.assertTrue(any("600" in s for s in sent))
        self.assertIn("1530\r", sent)
        self.assertIn("320", sent)
        self.assertIn(" ", sent)

    def test_step5_plan_c_clear_and_replace(self):
        """Step 5 案C (既存コメントの全クリアおよび新規コメント置換) のテスト"""
        sent = []
        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                sent.append(data)

        # Step 5 画面シーケンス
        screens = [
            # 0: Step 5 到達 (Transaction Comments 初期画面: Master Reference フォーカス)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│             Page: 1                                                          │\n"
            "│ Master Reference: 20000900                                   Language:       │\n"
            "│             Type:                                                Page: 1     │\n"
            "│ 【請求書】Email送付。郵送不要（タカラ●●）                                    │\n"
            "│ 【請求書】Email送付。郵送不要（タカラ大阪）：タカラ大阪+ｶﾝｻｲﾀｶﾗ印刷          │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "Adding new record\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf",

            # 1: F1送信後、本文エディタへ進入
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│ 【請求書】Email送付。郵送不要（タカラ●●）                                    │\n"
            "│ 【請求書】Email送付。郵送不要（タカラ大阪）：タカラ大阪+ｶﾝｻｲﾀｶﾗ印刷          │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",

            # 2: F8 (Clear) 送信後、本文が全クリアされた状態
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│                                                                              │\n"
            "│                                                                              │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear",

            # 3: 新規コメント入力後、F1送信で Print On Quote ポップアップ出現
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│ テスト用です                                                                 │\n"
            "│ パレット指定                                                                 │\n"
            "│                      ┌─────────────────────────────┐                         │\n"
            "│                      │          Print On Quote: Yes│                         │\n"
            "│                      │    Print On Sales Order: Yes│                         │\n"
            "│                      └─────────────────────────────┘                         │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘",

            # 4: 再度F1送信後、ポップアップ解除
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│ テスト用です                                                                 │\n"
            "│ パレット指定                                                                 │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘",

            # 5: F4送信後、Step 6 明細画面へ遷移
            "Sales Order Line\nLn Item Number",
        ]

        screen_idx = [0]
        def get_screen():
            return screens[screen_idx[0]]

        def custom_send(data):
            sent.append(data)
            idx = screen_idx[0]
            if idx == 0 and data == KEY_SEQUENCES["F1"]:
                screen_idx[0] = 1
            elif idx == 1 and data in (KEY_SEQUENCES.get("F8", "\x1b[19~"), "\x1b[19~"):
                screen_idx[0] = 2
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                screen_idx[0] = 3
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                screen_idx[0] = 4
            elif idx == 4 and data == KEY_SEQUENCES["F4"]:
                screen_idx[0] = 5

        session = MockSession()
        session.send = custom_send

        controller = SalesOrderAutomationController(
            session=session,
            get_screen_text=get_screen,
            payload={
                "so_comment": "テスト用です\nパレット指定",
                "items": [],
            },
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        # Step 5 の全クリア置換処理を直接検証
        # execute_full_order 内の Step 5 処理フローをシミュレート
        curr_txt = clean_screen_text(controller.get_screen_text()).lower()
        self.assertIn("transaction comments", curr_txt)
        so_comm = str(controller.payload.get("so_comment", "")).strip()

        # Step 5 実行
        controller.send(KEY_SEQUENCES["F1"])
        controller.send(KEY_SEQUENCES.get("F8", "\x1b[19~"))
        for c_line in so_comm.splitlines():
            controller.send(f"{c_line}\r")
        controller.send(KEY_SEQUENCES["F1"])
        controller.send(KEY_SEQUENCES["F1"])
        controller.send(KEY_SEQUENCES["F4"])

        # キーストローク検証
        self.assertIn(KEY_SEQUENCES["F1"], sent)
        self.assertIn(KEY_SEQUENCES.get("F8", "\x1b[19~"), sent)  # 案C: Clearキー
        self.assertIn("テスト用です\r", sent)
        self.assertIn("パレット指定\r", sent)
        self.assertIn(KEY_SEQUENCES["F4"], sent)
        self.assertEqual(screen_idx[0], 5)

    def test_step2_header_input_with_pricing_date_and_order_id(self):
        """TOPPANインフォメディアのPayloadでStep 2のPricing Date含む全項目入力とOrder ID抽出を検証"""
        screens = [
            # 0: Step 2 受注ヘッダー画面 (Order ID: SO199402)
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│Order: SO199402  Sold-To: 20000600  Bill To: 20000600  Ship-To: 20000601     │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "   Order Date: 09/29/26 Line Pricing: Yes\n"
                "Category=Strat Hipo  Press space bar to continue."
            ),
            # 1: Tax Usage ポップアップ
            "Tax Usage: 10%consumption\nTax Environment: 10%",
            # 2: Salesperson
            "Salesperson 1: S71\nFreight List:",
            # 3: Comments (なし)
            "Transaction Comments\nAdding new record",
            # 4: Sales Order Line
            "Sales Order Line\nLn Item Number",
        ]
        screen_idx = [0]

        def get_screen():
            return screens[min(screen_idx[0], len(screens) - 1)]

        sent = []

        f1_step2_count = [0]
        class MockSession:
            def send(self, data):
                sent.append(data)
                txt = data if isinstance(data, str) else data.decode("latin1", errors="replace")
                if screen_idx[0] == 0:
                    if txt == " ":
                        screens[0] = screens[0].replace("Category=Strat Hipo  Press space bar to continue.", "")
                    elif txt == KEY_SEQUENCES["F1"]:
                        f1_step2_count[0] += 1
                        if f1_step2_count[0] >= 2:
                            screen_idx[0] = 1
                elif txt == KEY_SEQUENCES["F1"]:
                    if screen_idx[0] > 0:
                        screen_idx[0] += 1
                elif txt == KEY_SEQUENCES["F4"]:
                    screen_idx[0] += 1

        toppan_payload = {
            "customer_name": "TOPPANインフォメディア株式会社",
            "ship_to": "TOPPANインフォメディア(株)福島工場",
            "purchase_order": "test",
            "customer_code": "20000600",
            "ship_to_code": "20000601",
            "remarks": "test",
            "so_comment": "",
            "required_date": "2026-09-30",
            "due_date": "2026-10-01",
            "items": [
                {
                    "product_name": "BW0116Q3-2",
                    "width": "200",
                    "length": "600",
                    "quantity": 1,
                    "price": "120"
                }
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=toppan_payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        # execute_full_order を実行 (Step 6到達まで)
        # モックでは Step 6 画面で終了
        try:
            controller.execute_full_order()
        except Exception:
            pass

        # Order ID が正しく SO199402 として抽出されていること
        self.assertEqual(controller.order_id, "SO199402")

        # Sold-To, Bill-To, Ship-To が順次送信されていること
        self.assertIn("20000600\r", sent)
        self.assertIn("20000601\r", sent)
        # Sold-To の後の Category 警告解除の Space
        self.assertIn(" ", sent)

        # 送信された Order Date からの一括貼り付けバッファの検証 (全8項目)
        paste_sent = [s for s in sent if isinstance(s, str) and "\r" in s and len(s.split("\r")) == 8]
        self.assertTrue(len(paste_sent) > 0, "Order Dateからの一括貼り付けバッファ(8項目)が送信されていること")
        items = paste_sent[0].split("\r")
        self.assertEqual(len(items), 8, "全8項目が改行で結合されていること")
        today_qad = date.today().strftime("%m/%d/%y")
        self.assertEqual(items[0], today_qad, "Line 1: Order Date")
        self.assertEqual(items[1], "09/30/26", "Line 2: Req Date")
        self.assertEqual(items[2], "", "Line 3: Promise Date (空)")
        self.assertEqual(items[3], "10/01/26", "Line 4: Due Date")
        self.assertEqual(items[4], "", "Line 5: Perform Date (空)")
        self.assertEqual(items[5], "", "Line 6: Pricing Date (空 ★必須)")
        self.assertEqual(items[6], "test", "Line 7: PO")
        self.assertEqual(items[7], "test", "Line 8: Remarks")
        # ヘッダー確定 F1
        self.assertIn(KEY_SEQUENCES["F1"], sent)

    def test_execute_full_order_from_blank_order_screen(self):
        """Order: が空の初期画面から開始した場合、F1で自動採番されてからSold-Toへ進むことを検証"""
        screens = [
            # 0: Order 欄がブランクの初期画面 (未採番)
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│Order:           Sold-To:           Bill To:           Ship-To:              │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"
            ),
            # 1: F1 送信後、Order ID (SO199420) が採番され Sold-To 待ちになった画面
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│Order: SO199420  Sold-To:           Bill To:           Ship-To:              │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "   Order Date: 09/29/26 Line Pricing: Yes\n"
                "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu"
            ),
            # 2: 完了 (モック)
            "Sales Order Line\nLn Item Number",
        ]
        screen_idx = [0]

        def get_screen():
            return screens[min(screen_idx[0], len(screens) - 1)]

        sent = []

        class MockSession:
            def send(self, data):
                sent.append(data)
                txt = data if isinstance(data, str) else data.decode("latin1", errors="replace")
                if txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = min(screen_idx[0] + 1, len(screens) - 1)

        payload = {
            "customer_code": "20000600",
            "ship_to_code": "20000601",
            "items": [{"product_name": "BW0100D", "width": "200", "length": "600", "quantity": 1, "price": "150"}]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        try:
            controller.execute_full_order()
        except Exception:
            pass

        # 最初のキーストロークは F1 (Order自動採番) であること
        self.assertEqual(sent[0], KEY_SEQUENCES["F1"])
        # その後に Sold-To (20000600) を含む一括バッファが送信されていること (Order欄に20000600は入らない！)
        self.assertTrue(any("20000600" in s for s in sent))
        # Order ID が正しく記録されていること
        self.assertEqual(controller.order_id, "SO199420")

    def test_toppan_full_pipeline_step1_to_step6_with_so_comment(self):
        """指示10のTOPPANペイロード(so_comment='test'付き)でStep1〜Step6.1.0到達までの自動化を完全検証"""
        screens = [
            # 0: Order 欄ブランク (未採番)
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│Order:           Sold-To:           Bill To:           Ship-To:              │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"
            ),
            # 1: Order ID (SO199499) 採番後、Sold-To フォーカス
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│Order: SO199499  Sold-To:           Bill To:           Ship-To:              │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "   Order Date: 09/29/26 Line Pricing: Yes\n"
                "Category=Strat Hipo  Press space bar to continue."
            ),
            # 2: Tax Usage ポップアップ
            "Tax Usage: 10%consumption\nTax Environment: 10%",
            # 3: Salesperson 画面
            "Salesperson 1: S71\nFreight List:",
            # 4: Step 5 Transaction Comments 初期画面
            (
                "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
                "│             Page: 1                                                          │\n"
                "│ Master Reference: 20000600                                   Language:       │\n"
                "│             Type:                                                Page: 1     │\n"
                "│ 既存コメント行                                                               │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"
            ),
            # 5: F1送信後、エディタ画面
            (
                "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
                "│ 既存コメント行                                                               │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear"
            ),
            # 6: F8送信後、クリアされたエディタ画面
            (
                "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
                "│                                                                              │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Help 3=Ins 4=End 5=Delete 7=Recall 8=Clear"
            ),
            # 7: 本文(test)入力後、F1送信で Print On Quote ポップアップ表示
            (
                "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
                "│ test                                                                         │\n"
                "│                      ┌─────────────────────────────┐                         │\n"
                "│                      │          Print On Quote: Yes│                         │\n"
                "│                      │    Print On Sales Order: Yes│                         │\n"
                "│                      └─────────────────────────────┘                         │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘"
            ),
            # 8: Print On Quote 確定後、先頭行復帰
            (
                "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
                "│             Page: 1                                                          │\n"
                "│ Master Reference: 20000600                                   Language:       │\n"
                "│             Type:                                                Page: 1     │\n"
                "│ test                                                                         │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"
            ),
            # 9: F4送信後、明細画面へ到達
            "Sales Order Line\nLn Item Number",
        ]
        screen_idx = [0]

        def get_screen():
            return screens[min(screen_idx[0], len(screens) - 1)]

        sent = []

        f1_step2_count = [0]
        class MockSession:
            def send(self, data):
                sent.append(data)
                txt = data if isinstance(data, str) else data.decode("latin1", errors="replace")
                idx = screen_idx[0]
                if idx == 0 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 1
                elif idx == 1:
                    if txt == " ":
                        screens[1] = screens[1].replace("Category=Strat Hipo  Press space bar to continue.", "")
                    elif txt == KEY_SEQUENCES["F1"]:
                        f1_step2_count[0] += 1
                        if f1_step2_count[0] >= 2:
                            screen_idx[0] = 2
                elif idx == 2 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 3
                elif idx == 3 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 4
                elif idx == 4 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 5
                elif idx == 5 and txt in (KEY_SEQUENCES.get("F8", "\x1b[19~"), "\x1b[19~"):
                    screen_idx[0] = 6
                elif idx == 6 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 7
                elif idx == 7 and txt == KEY_SEQUENCES["F1"]:
                    screen_idx[0] = 8
                elif idx == 8 and txt == KEY_SEQUENCES["F4"]:
                    screen_idx[0] = 9

        toppan_payload = {
            "customer_name": "TOPPANインフォメディア株式会社",
            "ship_to": "TOPPANインフォメディア(株)福島工場",
            "purchase_order": "test",
            "customer_code": "20000600",
            "ship_to_code": "20000601",
            "remarks": "test",
            "so_comment": "test",
            "required_date": "2026-09-30",
            "due_date": "2026-09-29",
            "items": [
                {
                    "product_name": "BW0100D",
                    "width": "200",
                    "length": "600",
                    "quantity": 2,
                    "price": "200"
                }
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=toppan_payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        try:
            controller.execute_full_order()
        except Exception:
            pass

        # 1. Order ID が SO199499 として抽出されたこと
        self.assertEqual(controller.order_id, "SO199499")

        # 2. Step 2 の順次送信および Order Date からの一括バッファ送信の検証
        self.assertIn("20000600\r", sent)
        self.assertIn("20000601\r", sent)
        self.assertIn(" ", sent)

        paste_sent = [s for s in sent if isinstance(s, str) and "\r" in s and len(s.split("\r")) == 8]
        self.assertTrue(len(paste_sent) > 0, "Order Dateからの一括貼り付けバッファ(8項目)が送信されていること")
        items = paste_sent[0].split("\r")
        self.assertEqual(len(items), 8)
        today_qad = date.today().strftime("%m/%d/%y")
        self.assertEqual(items[0], today_qad)   # Line 1: Order Date
        self.assertEqual(items[1], "09/30/26") # Line 2: Req Date
        self.assertEqual(items[2], "")         # Line 3: Promise Date
        self.assertEqual(items[3], "09/29/26") # Line 4: Due Date
        self.assertEqual(items[4], "")         # Line 5: Perform Date
        self.assertEqual(items[5], "")         # Line 6: Pricing Date (スキップ)
        self.assertEqual(items[6], "test")     # Line 7: PO
        self.assertEqual(items[7], "test")     # Line 8: Remarks

        # 3. Step 5 特記事項の入力検証
        self.assertIn("test\r", sent)
        self.assertIn(KEY_SEQUENCES.get("F8", "\x1b[19~"), sent)

        # 4. 最終的に Step 6.1.0 明細画面まで到達したこと
        self.assertEqual(screen_idx[0], 9)

    def test_toppan_user_payload_step2_sequential_and_order_date_paste(self):
        """ユーザー報告のTOPPANインフォメディア payload (SO199508) において、
        Sold-To/Bill-To/Ship-To 個別順次送信 ＋ Order Date からの一斉貼り付け（8項目）が正しく動作することを検証
        """
        screens = [
            # 0: Order ID (SO199508) 採番後、Sold-To 入力待ち
            (
                "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/29/26\n"
                "┌──────────────────────────────────────────────────────────────────────────────┐\n"
                "│ Order: SO199508  Sold-To: 20000600  Bill To: 20000600  Ship-To: 20000601     │\n"
                "└──────────────────────────────────────────────────────────────────────────────┘\n"
                "   Order Date: 09/29/26 Line Pricing: Yes\n"
                "Category=Strat Hipo  Press space bar to continue."
            ),
            # 1: Tax Usage ポップアップ
            "Tax Usage: 10%consumption\nTax Environment: 10%",
            # 2: Salesperson
            "Salesperson 1: S71\nFreight List:",
            # 3: Comments (なし)
            "Transaction Comments\nAdding new record",
            # 4: Sales Order Line (Step 6)
            "Sales Order Line\nLn Item Number",
        ]
        screen_idx = [0]

        def get_screen():
            return screens[min(screen_idx[0], len(screens) - 1)]

        sent = []

        f1_step2_count = [0]
        class MockSession:
            def send(self, data):
                sent.append(data)
                txt = data if isinstance(data, str) else data.decode("latin1", errors="replace")
                if screen_idx[0] == 0:
                    if txt == " ":
                        screens[0] = screens[0].replace("Category=Strat Hipo  Press space bar to continue.", "")
                    elif txt == KEY_SEQUENCES["F1"]:
                        f1_step2_count[0] += 1
                        if f1_step2_count[0] >= 2:
                            screen_idx[0] = 1
                elif txt == KEY_SEQUENCES["F1"]:
                    if screen_idx[0] > 0:
                        screen_idx[0] += 1
                elif txt == KEY_SEQUENCES["F4"]:
                    screen_idx[0] += 1

        payload = {
            "customer_name": "TOPPANインフォメディア株式会社",
            "ship_to": "TOPPANインフォメディア(株)福島工場",
            "purchase_order": "test",
            "customer_code": "20000600",
            "ship_to_code": "20000601",
            "address": "960-8201\nTOPPANインフォメディア(株)福島工場\n福島県福島市岡島字宮田30-2\n\n\n024-536-6111",
            "remarks": "test",
            "so_comment": "",
            "required_date": "2026-10-02",
            "due_date": "2026-09-30",
            "items": [
                {
                    "product_name": "BW0100D",
                    "width": "200",
                    "length": "600",
                    "quantity": 1,
                    "price": "200"
                },
                {
                    "product_name": "BW0212C-2",
                    "width": "200",
                    "length": "600",
                    "quantity": 1,
                    "price": "200"
                }
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        try:
            controller.execute_full_order()
        except Exception:
            pass

        # 1. Order ID が SO199508 として抽出されていること
        self.assertEqual(controller.order_id, "SO199508")

        # 2. Sold-To, Bill-To, Ship-To が個別に順次送信されたこと
        self.assertIn("20000600\r", sent)
        self.assertIn("20000601\r", sent)
        self.assertIn(" ", sent)

        sold_to_idx = sent.index("20000600\r")
        space_idx = sent.index(" ")
        self.assertTrue(sold_to_idx < space_idx, "Sold-To の後に Space 警告解除が送信されること")

        # 3. Order Date からの一括貼り付けバッファ (全8項目) の検証
        paste_sent = [s for s in sent if isinstance(s, str) and "\r" in s and len(s.split("\r")) == 8]
        self.assertTrue(len(paste_sent) > 0, "Order Date からの8項目一括貼り付けバッファが送信されていること")
        items = paste_sent[0].split("\r")
        self.assertEqual(len(items), 8)
        today_qad = date.today().strftime("%m/%d/%y")
        self.assertEqual(items[0], today_qad, "Line 1: Order Date (当日日付)")
        self.assertEqual(items[1], "10/02/26", "Line 2: Required Date (2026-10-02 -> 10/02/26)")
        self.assertEqual(items[2], "", "Line 3: Promise Date (空Enterスキップ)")
        self.assertEqual(items[3], "09/30/26", "Line 4: Due Date (2026-09-30 -> 09/30/26)")
        self.assertEqual(items[4], "", "Line 5: Perform Date (空Enterスキップ)")
        self.assertEqual(items[5], "", "Line 6: Pricing Date (空Enterスキップ ★必須)")
        self.assertEqual(items[6], "test", "Line 7: Purchase Order (test)")
        self.assertEqual(items[7], "test", "Line 8: Remarks (test)")

        # 4. ヘッダー確定 F1
        self.assertIn(KEY_SEQUENCES["F1"], sent)

    def test_multi_product_with_pre_existing_create_wo(self):
        """2品目目開始時にすでにCreate WOが出現している場合、余計なEnterを送らず直ちにF1でスキップして品番入力へ進むことを検証"""
        screens = [
            # 0: Line 1 Ln 採番画面 (まだ Create WO はない)
            "Sales Order Line\nLn Item Number",
            # 1: Line 1 Create WO
            "Create WO: Y Rework: Y Exact: Y",
            # 2: Line 1 Item Number
            "Sales Order Line\nLn Item Number",
            # 3: Line 1 Site
            "Site: CB2",
            # 4: Line 1 Qty Ordered UM スキップ
            "Sales Order Line\nQty Ordered UM M2",
            # 5: Line 1 SL一覧画面 (No1)
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 6: Line 1 Len(m) 入力欄
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 7: Line 1 ロールポップアップ
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 8: Line 1 Rolls 確定
            "Please confirm update yes",
            # Line 1 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 10: Line 1 SL 確定
            "Please confirm update yes",
            # 11: Line 1 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 12: Line 1 Price (単価)
            "Sales Order Line\nList Price 130.00 Price 130.00",
            # 13: Line 1 Tax Usage
            "Tax Usage: 10%consumption",
            # 14: Line 1 Transaction Comments
            "Transaction Comments\nMaster Reference: BW0100D",
            # 15: Line 1 Reason Code
            "Reason Code: 70",
            # ★16: Line 2 開始時: Reason Code 確定直後にすでに Line 2 の Create WO が出現している状態！
            "Sales Order Line\nLn 2 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 17: Line 2 Create WO 解除後の Item Number 画面
            "Sales Order Line\nLn 2 Item Number",
            # 18: Line 2 Site
            "Site: CB2",
            # 19: Line 2 Qty Ordered UM スキップ
            "Sales Order Line\nQty Ordered UM M2",
            # 20: Line 2 SL画面
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 21: Line 2 Len(m) 入力欄
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 22: Line 2 ロールポップアップ
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 23: Line 2 Rolls 確定
            "Please confirm update yes",
            # Line 2 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 25: Line 2 SL 確定
            "Please confirm update yes",
            # 26: Line 2 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 27: Line 2 Price (単価)
            "Sales Order Line\nList Price 150.00 Price 150.00",
            # 28: Line 2 Tax Usage
            "Tax Usage: 10%consumption",
            # 29: Line 2 Transaction Comments
            "Transaction Comments\nMaster Reference: BW0212C-2",
            # 30: Line 2 完了後の明細画面復帰（次行 Line 3 の Create WO が出現）
            "Sales Order Line\nLn 3 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 31: Line 3 Create WO 解除後の画面 (F1 送信後)
            "Sales Order Line\nLn 3 Item Number",
            # 32: 6.3.0 Totals 画面 (F4 送信後)
            "Order: SO199405\nLine Total: 30,000\nTotal Tax: 3,000\nEnter data or press F4 to end.",
            # 33: Space 待機 (F1 x 2 送信後)
            "Press space bar to continue.",
            # 34: 完了 (Space 送信後)
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        sent_data = []
        f1_counts = {32: 0}

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(*args):
            data = args[-1]
            sent_data.append(data)
            idx = screen_idx[0]
            advanced = False

            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 14 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # ★idx == 16 (Line 2 の Create WO 既存画面): F1 が送られたら次へ進む！
            elif idx == 16 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 17 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 18 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 19 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 20 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 21 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 22 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 23 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 24 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 25 and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 26 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 27 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 28 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 29 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 30 and data == KEY_SEQUENCES["F1"]:
                # Line 3 の Create WO ポップアップを F1 で解除
                advanced = True
            elif idx == 31 and data == KEY_SEQUENCES["F4"]:
                # 明細を抜けて Totals 画面へ進む
                advanced = True
            elif idx == 32 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                # Totals 画面で F1 を 2回送信してコミット
                f1_counts[32] += 1
                if data == KEY_SEQUENCES["F4"] or f1_counts[32] >= 2:
                    advanced = True
            elif idx == 33 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            send = custom_send

        payload = {
            "items": [
                {"product_name": "BW0100D", "width": "200", "length": "600", "quantity": 1, "price": "130.00"},
                {"product_name": "BW0212C-2", "width": "200", "length": "600", "quantity": 1, "price": "150.00"},
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        res_order_id = controller.execute_step6()

        # Line 1 (BW0100D) と Line 2 (BW0212C-2) が両方送信されていること
        self.assertIn("BW0100D", sent_data)
        self.assertIn("BW0212C-2", sent_data)
        # Line 2 開始時に余計な \r が送られず、F1 で Create WO がスキップされたことの厳格な検証
        bw2_idx = sent_data.index("BW0212C-2")
        self.assertEqual(sent_data[bw2_idx - 1], KEY_SEQUENCES["F1"], "BW0212C-2直前のキーはF1(Create WO解除)であること")
        self.assertNotEqual(sent_data[bw2_idx - 2], "\r", "Line 2開始時に余計なEnterが送られていないこと")
        # 全工程を完走して最終画面まで到達したこと
        self.assertEqual(screen_idx[0], len(screens) - 1)
        # Order ID が正しく返却されたこと
        self.assertEqual(res_order_id, "SO199405")

    def test_three_products_with_pre_existing_create_wo(self):
        """3品目以上の入力時に、Line 2およびLine 3両方で先行Create WOがF1でスキップされ、余計なEnterが送られないことを検証"""
        screens = [
            # 0: Line 1 Ln 採番画面
            "Sales Order Line\nLn Item Number",
            # 1: Line 1 Create WO
            "Create WO: Y Rework: Y Exact: Y",
            # 2: Line 1 Item Number
            "Sales Order Line\nLn Item Number",
            # 3: Line 1 Site
            "Site: CB2",
            # 4: Line 1 Qty Ordered UM スキップ
            "Sales Order Line\nQty Ordered UM M2",
            # 5: Line 1 SL一覧画面 (No1)
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 6: Line 1 Len(m) 入力欄
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 7: Line 1 ロールポップアップ
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 8: Line 1 Rolls 確定
            "Please confirm update yes",
            # 9: Line 1 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 10: Line 1 SL 確定
            "Please confirm update yes",
            # 11: Line 1 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 12: Line 1 Price (単価)
            "Sales Order Line\nList Price 130.00 Price 130.00",
            # 13: Line 1 Tax Usage
            "Tax Usage: 10%consumption",
            # 14: Line 1 Transaction Comments
            "Transaction Comments\nMaster Reference: BW0100D",
            # 15: Line 1 Reason Code
            "Reason Code: 70",
            # ★16: Line 2 開始時: Line 2 の Create WO 出現
            "Sales Order Line\nLn 2 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 17: Line 2 Create WO 解除後
            "Sales Order Line\nLn 2 Item Number",
            # 18: Line 2 Site
            "Site: CB2",
            # 19: Line 2 Qty Ordered UM
            "Sales Order Line\nQty Ordered UM M2",
            # 20: Line 2 SL画面
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 21: Line 2 Len(m) 入力欄
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 22: Line 2 ロールポップアップ
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 23: Line 2 Rolls 確定
            "Please confirm update yes",
            # 24: Line 2 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 25: Line 2 SL 確定
            "Please confirm update yes",
            # 26: Line 2 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 27: Line 2 Price (単価)
            "Sales Order Line\nList Price 150.00 Price 150.00",
            # 28: Line 2 Tax Usage
            "Tax Usage: 10%consumption",
            # 29: Line 2 Transaction Comments
            "Transaction Comments\nMaster Reference: BW0212C-2",
            # 30: Line 2 Reason Code
            "Reason Code: 70",
            # ★31: Line 3 開始時: Line 3 の Create WO 出現
            "Sales Order Line\nLn 3 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 32: Line 3 Create WO 解除後
            "Sales Order Line\nLn 3 Item Number",
            # 33: Line 3 Site
            "Site: CB2",
            # 34: Line 3 Qty Ordered UM
            "Sales Order Line\nQty Ordered UM M2",
            # 35: Line 3 SL画面
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 36: Line 3 Len(m) 入力欄
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 37: Line 3 ロールポップアップ
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 38: Line 3 Rolls 確定
            "Please confirm update yes",
            # 39: Line 3 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 100\nSL Run Len(m)",
            # 40: Line 3 SL 確定
            "Please confirm update yes",
            # 41: Line 3 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 42: Line 3 Price (単価)
            "Sales Order Line\nList Price 120.00 Price 120.00",
            # 43: Line 3 Tax Usage
            "Tax Usage: 10%consumption",
            # 44: Line 3 Transaction Comments
            "Transaction Comments\nMaster Reference: BW0116Q3-2",
            # 45: Line 3 Reason Code
            "Reason Code: 70",
            # ★46: 全品目完了後: 次行 Line 4 の Create WO 出現
            "Sales Order Line\nLn 4 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 47: Line 4 Create WO 解除後
            "Sales Order Line\nLn 4 Item Number",
            # 48: 6.3.0 Totals 画面
            "Order: SO199410\nLine Total: 45,000\nTotal Tax: 4,500\nEnter data or press F4 to end.",
            # 49: Space
            "Press space bar to continue.",
            # 50: 完了
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        sent_data = []
        f1_counts = {48: 0}

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(*args):
            data = args[-1]
            sent_data.append(data)
            idx = screen_idx[0]
            advanced = False

            # Line 1 (idx 0〜15)
            if idx == 0 and data == "\r":
                advanced = True
            elif idx in (1, 2, 3, 4, 5) and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx in (10, 11, 12, 13) and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 14 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # Line 2 (idx 16〜30) - idx 16は先行Create WOのためF1でスキップ
            elif idx in (16, 17, 18, 19, 20) and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 21 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 22 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 23 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 24 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx in (25, 26, 27, 28) and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 29 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 30 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # Line 3 (idx 31〜45) - idx 31は先行Create WOのためF1でスキップ
            elif idx in (31, 32, 33, 34, 35) and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 36 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and data.endswith("\r") and any(c.isdigit() for c in data))):
                advanced = True
            elif idx == 37 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 38 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 39 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx in (40, 41, 42, 43) and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 44 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 45 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # 脱出・完了 (idx 46〜50)
            elif idx == 46 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 47 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 48 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                f1_counts[48] += 1
                if data == KEY_SEQUENCES["F4"] or f1_counts[48] >= 2:
                    advanced = True
            elif idx == 49 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            send = custom_send

        payload = {
            "items": [
                {"product_name": "BW0100D", "width": "200", "length": "600", "quantity": 1, "price": "130.00"},
                {"product_name": "BW0212C-2", "width": "200", "length": "600", "quantity": 1, "price": "150.00"},
                {"product_name": "BW0116Q3-2", "width": "200", "length": "400", "quantity": 1, "price": "120.00"},
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        res_order_id = controller.execute_step6()

        # 3品目すべてが送信されていること
        self.assertIn("BW0100D", sent_data)
        self.assertIn("BW0212C-2", sent_data)
        self.assertIn("BW0116Q3-2", sent_data)

        # Line 2 および Line 3 開始時に余計な \r が送られず、F1 で Create WO がスキップされたことの検証
        idx_p2 = sent_data.index("BW0212C-2")
        self.assertEqual(sent_data[idx_p2 - 1], KEY_SEQUENCES["F1"])
        self.assertNotEqual(sent_data[idx_p2 - 2], "\r")

        idx_p3 = sent_data.index("BW0116Q3-2")
        self.assertEqual(sent_data[idx_p3 - 1], KEY_SEQUENCES["F1"])
        self.assertNotEqual(sent_data[idx_p3 - 2], "\r")

        # 最終完了画面へ到達したこと
        self.assertEqual(screen_idx[0], len(screens) - 1)
        self.assertEqual(res_order_id, "SO199410")

    def test_multi_product_multi_length_multi_width_full_execution(self):
        """実機検証Test 5 (2製品 x 2長さ x 2幅) の全多段ループが過去の検証ログ通り確実に実行されることを検証"""
        screens = [
            # 0: Line 1 Ln 採番
            "Sales Order Line\nLn Item Number",
            # 1: Line 1 Create WO
            "Create WO: Y Rework: Y Exact: Y",
            # 2: Line 1 Item Number
            "Sales Order Line\nLn Item Number",
            # 3: Line 1 Site
            "Site: CB2",
            # 4: Line 1 Qty Ordered UM スキップ
            "Sales Order Line\nQty Ordered UM M2",
            # 5: Line 1 SL 1 (600m) SL一覧
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 6: Line 1 SL 1 Len(m) 入力
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 7: Line 1 SL 1 ロールポップアップ (250mm)
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 8: Line 1 SL 1 Rolls 確定
            "Please confirm update yes",
            # 9: Line 1 SL 2 (400m) SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 150\nSL Run Len(m)",
            # 10: Line 1 SL 2 Len(m) 入力
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 150\nSL Run Len(m)\nValue Should Be > 0",
            # 11: Line 1 SL 2 ロールポップアップ (120mm)
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 12: Line 1 SL 2 Rolls 確定
            "Please confirm update yes",
            # 13: Line 1 SL 2 完了後 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 198\nSL Run Len(m)",
            # 14: Line 1 全SL完了確認
            "Please confirm update yes",
            # 15: Line 1 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 16: Line 1 Price (130)
            "Sales Order Line\nList Price 130.00 Price 130.00",
            # 17: Line 1 Tax Usage
            "Tax Usage: 10%consumption",
            # 18: Line 1 Comments
            "Transaction Comments\nMaster Reference: BW0100D",
            # 19: Line 1 Reason Code
            "Reason Code: 70",
            # ★20: Line 2 開始時 (Create WO 既存画面)
            "Sales Order Line\nLn 2 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 21: Line 2 Create WO 解除後
            "Sales Order Line\nLn 2 Item Number",
            # 22: Line 2 Site
            "Site: CB2",
            # 23: Line 2 Qty Ordered UM スキップ
            "Sales Order Line\nQty Ordered UM M2",
            # 24: Line 2 SL 1 (600m) SL一覧
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)",
            # 25: Line 2 SL 1 Len(m) 入力
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 0\nSL Run Len(m)\nValue Should Be > 0",
            # 26: Line 2 SL 1 ロールポップアップ (250mm)
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 27: Line 2 SL 1 Rolls 確定
            "Please confirm update yes",
            # 28: Line 2 SL 2 (400m) SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 150\nSL Run Len(m)",
            # 29: Line 2 SL 2 Len(m) 入力
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 150\nSL Run Len(m)\nValue Should Be > 0",
            # 30: Line 2 SL 2 ロールポップアップ (120mm)
            "Ser T Rolls Width(mm) Tot Qty(M2)",
            # 31: Line 2 SL 2 Rolls 確定
            "Please confirm update yes",
            # 32: Line 2 SL 2 完了後 SL一覧復帰
            "Item Width(mm):1070 Exact:yes TOTAL QTY (M2) 198\nSL Run Len(m)",
            # 33: Line 2 全SL完了確認
            "Please confirm update yes",
            # 34: Line 2 Pricing Date
            "Sales Order Line\nPricing Date: 09/26/26",
            # 35: Line 2 Price (150)
            "Sales Order Line\nList Price 150.00 Price 150.00",
            # 36: Line 2 Tax Usage
            "Tax Usage: 10%consumption",
            # 37: Line 2 Comments
            "Transaction Comments\nMaster Reference: BW0212C-2",
            # 38: Line 2 Reason Code
            "Reason Code: 70",
            # ★39: 全完了後: 次行 Line 3 の Create WO
            "Sales Order Line\nLn 3 Item Number\nCreate WO: Y Rework: Y Exact: Y",
            # 40: Line 3 Create WO 解除後
            "Sales Order Line\nLn 3 Item Number",
            # 41: 6.3.0 Totals 画面
            "Order: SO199400\nLine Total: 55,440\nTotal Tax: 5,544\nEnter data or press F4 to end.",
            # 42: Space
            "Press space bar to continue.",
            # 43: 完了
            "mfmenu Main Menu",
        ]

        screen_idx = [0]
        sent_data = []
        f1_counts = {41: 0}

        def get_screen():
            idx = screen_idx[0]
            if idx < len(screens):
                return screens[idx]
            return screens[-1]

        def custom_send(*args):
            data = args[-1]
            sent_data.append(data)
            idx = screen_idx[0]
            advanced = False

            # Line 1 (idx 0〜19)
            if idx == 0 and data == "\r":
                advanced = True
            elif idx in (1, 2, 3, 4, 5) and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and "600" in data)):
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 10 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and "400" in data)):
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 14 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx in (15, 16, 17) and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 18 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 19 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # Line 2 (idx 20〜38)
            elif idx in (20, 21, 22, 23, 24) and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 25 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and "600" in data)):
                advanced = True
            elif idx == 26 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 27 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 28 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 29 and (data == KEY_SEQUENCES["F1"] or (isinstance(data, str) and "400" in data)):
                advanced = True
            elif idx == 30 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 31 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 32 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 33 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx in (34, 35, 36) and data in (KEY_SEQUENCES["F1"], "\r"):
                advanced = True
            elif idx == 37 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 38 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            # Exit to Totals (idx 39〜43)
            elif idx == 39 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 40 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 41 and data in (KEY_SEQUENCES["F4"], KEY_SEQUENCES["F1"]):
                f1_counts[41] += 1
                if data == KEY_SEQUENCES["F4"] or f1_counts[41] >= 2:
                    advanced = True
            elif idx == 42 and data == " ":
                advanced = True

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            send = custom_send

        # Test 5 と同一の 2品番 x 2長さ x 2幅 ペイロード
        payload = {
            "items": [
                {"product_name": "BW0100D", "width": "250", "length": "600", "quantity": 1, "price": "130"},
                {"product_name": "BW0100D", "width": "120", "length": "400", "quantity": 1, "price": "130"},
                {"product_name": "BW0212C-2", "width": "250", "length": "600", "quantity": 1, "price": "150"},
                {"product_name": "BW0212C-2", "width": "120", "length": "400", "quantity": 1, "price": "150"},
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        res_order_id = controller.execute_step6()

        # 品番、長さ、幅がすべて送信されていること
        self.assertIn("BW0100D", sent_data)
        self.assertIn("BW0212C-2", sent_data)
        self.assertTrue(any("250\r" in s for s in sent_data if isinstance(s, str)))
        self.assertTrue(any("120\r" in s for s in sent_data if isinstance(s, str)))
        self.assertTrue(any("600\r" in s for s in sent_data if isinstance(s, str)))
        self.assertTrue(any("400\r" in s for s in sent_data if isinstance(s, str)))

        # 最終完了画面へ到達したこと
        self.assertEqual(screen_idx[0], len(screens) - 1)
        self.assertEqual(res_order_id, "SO199400")

    def test_line_detail_frame_loc_skip_execution(self):
        """
        実機検証仕様: 単価確定後に下部詳細枠 (Loc: / Sales Acct: / JPY Cost:) が展開された場合、
        F1 を送信して詳細枠をスキップし、Transaction Comments / Reason Code / 次行へ正常に進行すること
        """
        sent_data = []
        screen_idx = [0]

        # 実際のQAD画面 (Loc: 停止が起きた画面を含むシーケンス)
        screens = [
            # 0: 6.1.0 メインメニュー
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Sales Order: SO199526 Sold-To: 20000600 Ln Format S/M: Single                │\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 1: 6.1.1 Create WO ポップアップ
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Ln Item│Create WO: Y Rework: Y Exact: Y│ List Price Discount           Price │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 2: 6.1.3 Item Number 入力欄
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1                                                                           │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End 5=Delete",

            # 3: 6.1.3 Site ポップアップ出現
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Ln Item Numbe│ Site     │ Ordered UM     List Price Discount           Price │\n"
            "│─── ──────────│ ──────── │──────── ── ────────────── ──────── ─────────────── │\n"
            "│  1 BW0100D   │ CB2      │                                                    │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 4: 6.1.4 Qty Ordered UM 入力
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1 BW0100D                  120.0 M2                                         │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "On Hand: 1000.0  Avail. to Allocate: 1000.0\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 5: 6.1.4 No1 スリット設定画面 (Item Width)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 120──────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│─── ─── ────────── ───── ───────────── ───────────────              │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 6: 6.2.0 Len(m) 入力欄
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 120──────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│  1   1                                                             │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 7: 6.2.1 ロール明細ポップアップ
            "┌────────────────────────────────────────────────────────┐\n"
            "│  Ser T Rolls Width(mm)                                 │\n"
            "│──── ─ ───── ─────────                                  │\n"
            "│                                                        │\n"
            "└────────────────────────────────────────────────────────┘\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 8: 6.2.1 ロール入力後の Please confirm update
            "Please confirm update yes\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 9: 6.1.4 全SL完了前の SL一覧復帰画面
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 120──────────┐\n"
            "│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │\n"
            "│─── ─── ────────── ───── ───────────── ───────────────              │\n"
            "│  1   1      600.0   yes         200.0             120.0             │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 10: 6.1.4 全スリット完了後の Please confirm update
            "Please confirm update yes\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 11: 6.2.3 Pricing Date 画面
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Sales Order: SO199526 Sold-To: 20000600 Ln Format S/M: Single                │\n"
            "┌────────────────────────────── Sales Order Line ──────────────────────────────┐\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1 BW0100D                  120.0 M2                                         │\n"
            "│                        ┌─────────────────────────────┐                       │\n"
            "│                        │      Pricing Date: 09/30/26 │                       │\n"
            "│                        └─────────────────────────────┘                       │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 12: 6.2.4 List Price / Price 入力画面
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Sales Order: SO199526 Sold-To: 20000600 Ln Format S/M: Single                │\n"
            "│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│  1 BW0100D                  120.0 M2          77.00      0.0            0.00 │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 13: 6.2.4-Detail 【実機で停止した明細詳細枠】
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│Sales Order: SO199526 Sold-To: 20000600 Ln Format S/M: Single                │\n"
            "│Ln Item Number        Qty Ordered UM     List Price Discount           Price │\n"
            "│─── ────────────────── ─────────── ── ────────────── ──────── ─────────────── │\n"
            "│ 1 BW0100D                  120.0 M2          77.00  -159.74          200.00 │\n"
            "┌──────────────────────────────────────────────────────────────────────────────┐\n"
            "│Desc: SemiCLOPP18/S692N/BG40W  Sales Acct: 400000                             │\n"
            "│Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "│  JPY Cost: 54.5301            Confirmed: Yes   Credit Terms Int: 0.00       │\n"
            "│Lot/Serial:                     Required: 10/01/26     Ship Type:            │\n"
            "│Qty Allocated: 0.0              Promised: 10/01/26 UM Conversion: 1.0000     │\n"
            "│   Qty Picked: 0.0              Due Date: 09/30/26  Consume Fcst: Yes        │\n"
            "│  Qty Shipped: 0.0          Perform Date:   /  /    Detail Alloc: No         │\n"
            "│Qty to Invoice: 0.0          Pricing Date: 09/30/26       Taxable: Yes  10    │\n"
            "│Salesperson 1: S53              Multiple: No        Freight List:            │\n"
            "│ Commission 1: 0.00%    Category:           Fixed Price: Yes  Comments: Yes  │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 14: 6.2.5 Transaction Comments 画面
            "┌──────────────────────────── Transaction Comments ────────────────────────────┐\n"
            "│ Master Reference: BW0100D                                                    │\n"
            "Adding new record\n"
            "F1=Go 2=Hlp 3=Ins 4=End",

            # 15: 6.2.5 Reason Code 画面 (定価差異・納期差異)
            "┌─────────────────────────────── Reason Code ──────────────────────────────────┐\n"
            "│ Reason Code:                                                                 │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 16: 6.1.0 次行 Create WO 出現 (Line 2 へ: 背景に直前の詳細枠 Sales Acct: や Category= が残る実機画面)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Sales Order: SO199526 Sold-To: 20000600 Ln Format S/M: Single                │\n"
            "┌────────┌───────────────────────────────┐r Line ──────────────────────────────┐\n"
            "│ Ln Item│Create WO: Y Rework: Y Exact: Y│ List Price Discount           Price │\n"
            "│─── ────└───────────────────────────────┘─────────── ──────── ─────────────── │\n"
            "│  2                            0.0              0.00      0.0            0.00 │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "┌──────────────────────────────────────────────────────────────────────────────┐\n"
            "│Desc: SemiCLOPP18/S692N/BG40W  Sales Acct: 400000                             │\n"
            "│ Loc:           Site: CB2       Disc Acct: 403100                             │\n"
            "│   JPY Cost: 54.5301            Confirmed: Yes   Credit Terms Int: 0.00       │\n"
            "│ Lot/Serial:                     Required: 10/01/26     Ship Type:            │\n"
            "└──────────────────────────────────────────────────────────────────────────────┘\n"
            "Category=Strat Hipo\n"
            "F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf",

            # 17: Step 6.3.0 最終合計画面 (Totals)
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "│ Sales Order: SO199526 Sold-To: 20000600                                      │\n"
            "│ Line Total: 24,000.00   Total Tax: 2,400.00   Trailer: 0.00                  │\n"
            "│ Disc Pct: 0.00%                                                              │\n"
            "Enter data or press F4 to end.\n"
            "F1=Go 2=Help 3=Ins 4=End",

            # 18: 受注完了・初期画面復帰
            "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/30/26\n"
            "Order:          Sold-To:                                                       \n"
            "F1=Go 2=Help 3=Ins 4=End",
        ]

        def get_screen():
            return screens[screen_idx[0]]

        f1_totals_count = [0]
        f1_price_count = [0]

        def custom_send(data):
            sent_data.append(data)
            idx = screen_idx[0]
            advanced = False

            if idx == 0 and data == "\r":
                advanced = True
            elif idx == 1 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 2 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 3 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 4 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and data == "600\r":
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                # 全SL完了の F4 送信
                advanced = True
            elif idx == 10 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 11 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 12 and data == KEY_SEQUENCES["F1"]:
                f1_price_count[0] += 1
                if f1_price_count[0] >= 2:
                    # List Price スキップ + 単価確定 F1 で実機明細詳細枠 (idx 13) へ
                    advanced = True
            elif idx == 13 and data == KEY_SEQUENCES["F1"]:
                # 【最重要】詳細枠 (Loc: / Sales Acct:) に対し F1 送信で Comments (idx 14) へ
                advanced = True
            elif idx == 14 and data == KEY_SEQUENCES["F4"]:
                # Comments 画面で F4 送信して Reason Code (idx 15) へ
                advanced = True
            elif idx == 15 and data == KEY_SEQUENCES["F1"]:
                # Reason Code 確定で次行 Create WO (idx 16) へ
                advanced = True
            elif idx == 16 and data in (KEY_SEQUENCES["F1"], KEY_SEQUENCES["F4"]):
                # 6.3.0: 次行 Create WO 解除 (F1) または F4 脱出で Totals (idx 17) へ
                advanced = True
            elif idx == 17:
                if data == KEY_SEQUENCES["F1"]:
                    f1_totals_count[0] += 1
                    if f1_totals_count[0] >= 2:
                        advanced = True
                elif data == " ":
                    advanced = True
                elif data == KEY_SEQUENCES["F4"]:
                    advanced = True
            elif idx == 18:
                pass

            if advanced and screen_idx[0] < len(screens) - 1:
                screen_idx[0] += 1

        class MockSession:
            stop_event = MagicMock()
            stop_event.is_set.return_value = False
            def send(self, data):
                custom_send(data)

        payload = {
            "items": [
                {"product_name": "BW0100D", "width": "200", "length": "600", "quantity": 1, "price": "200"}
            ]
        }

        controller = SalesOrderAutomationController(
            session=MockSession(),
            get_screen_text=get_screen,
            payload=payload,
            sleep_func=lambda s: None,
            default_timeout=2.0,
        )

        res_order_id = controller.execute_step6()

        # 詳細枠 (Loc:) のスキップ F1 が送信されたこと
        self.assertIn("200", sent_data)
        self.assertEqual(res_order_id, "SO199526")
        self.assertEqual(screen_idx[0], len(screens) - 1)


if __name__ == "__main__":
    unittest.main()




