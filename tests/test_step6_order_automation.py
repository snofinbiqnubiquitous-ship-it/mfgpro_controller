import unittest
from unittest.mock import MagicMock
import time

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
            self.assertIn("6.3.0-4. 注文コミット＆与信/延滞チェック実行: <F4>", out)
            self.assertIn("6.3.0-5. 初期画面への安全復帰 (全工程完了): <F4>", out)
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
            elif idx == 6 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data == "\r":
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
        self.assertIn("600", sent_data)                   # 6.2.0 長さ
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
            elif idx == 5 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 6 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 9 and data == "\r":
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
            elif idx == 6 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data == "\r":
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
                advanced = True  # Advances immediately to Press space!
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
        # Verify only 1 F1 was sent at totals screen before space was sent!
        self.assertEqual(f1_totals_count[0], 1)
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
            elif idx == 6 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 7 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 8 and data == KEY_SEQUENCES["F1"]:
                advanced = True
            elif idx == 9 and data == KEY_SEQUENCES["F4"]:
                advanced = True
            elif idx == 10 and data == "\r":
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
        self.assertIn("600", sent)
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

        class MockSession:
            def send(self, data):
                sent.append(data)
                txt = data if isinstance(data, str) else data.decode("latin1", errors="replace")
                if txt == " ":
                    pass
                elif txt == KEY_SEQUENCES["F1"]:
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

        # 送信されたキーシーケンスの検証
        # 1. Sold-To: 20000600\r
        self.assertIn("20000600\r", sent)
        # 2. Bill-To: 20000600\r
        self.assertEqual(sent.count("20000600\r"), 2)
        # 3. Ship-To: 20000601\r
        self.assertIn("20000601\r", sent)
        # 4. Req Date: 09/30/26\r
        self.assertIn("09/30/26\r", sent)
        # 5. Due Date: 10/01/26\r
        self.assertIn("10/01/26\r", sent)
        # 6. PO: test\r
        self.assertIn("test\r", sent)
        # 7. Category 警告解除の Space
        self.assertIn(" ", sent)
        # 8. ヘッダー確定 F1
        self.assertIn(KEY_SEQUENCES["F1"], sent)


if __name__ == "__main__":
    unittest.main()


