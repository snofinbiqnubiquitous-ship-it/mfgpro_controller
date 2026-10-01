import tempfile
from datetime import date, timedelta
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from order_entry import (
    AutocompletePopup, ProductComboBox, DateField, DoubleControlTap, OrderValidationError, collect_order, format_order_date,
    read_choice_csv, normalize_shortcut, shortcut_from_key_event, parse_typed_date
)


class ProductPopupTests(unittest.TestCase):
    def make_popup(self, values, current=""):
        entry = SimpleNamespace(value=current)
        entry.get = lambda: entry.value
        popup = SimpleNamespace(
            all_candidates=values, entry=entry, _page_source=None, _page_query=None,
            _page_offset=0, _selected_index=-1, filtered_candidates=[], PAGE_SIZE=10,
        )
        def show(items):
            popup.filtered_candidates = items
            popup._selected_index = items.index(entry.value) if entry.value in items else -1
        popup._show_popup = Mock(side_effect=show)
        popup._show_page = lambda offset: AutocompletePopup._show_page(popup, offset)
        popup._get_page_source = lambda: AutocompletePopup._get_page_source(popup)
        popup._apply_selection = lambda index: (setattr(popup, "_selected_index", index), setattr(entry, "value", popup.filtered_candidates[index]))
        popup.show_click_candidates = lambda: AutocompletePopup.show_click_candidates(popup)
        popup.is_open = lambda: bool(popup.filtered_candidates)
        return popup

    def test_click_and_arrow_show_only_first_page(self):
        values = [f"製品{i:05d}" for i in range(2000)]
        popup = self.make_popup(values, "製品01999")
        AutocompletePopup._on_entry_click(popup)
        shown = popup._show_popup.call_args.args[0]
        self.assertEqual(shown, values[1990:2000])
        ProductComboBox._open_dropdown_menu(SimpleNamespace(product_autocomplete=popup))
        self.assertEqual(popup._show_popup.call_count, 2)

    def test_arrows_load_adjacent_pages_and_wrap_only_at_ends(self):
        values = [f"製品{i:05d}" for i in range(23)]
        popup = self.make_popup(values)
        popup.show_click_candidates()
        self.assertEqual(popup.filtered_candidates, values[:10])
        for _ in range(11):
            self.assertEqual(AutocompletePopup._on_down_key(popup), "break")
        self.assertEqual(popup.filtered_candidates, values[10:20])
        self.assertEqual(popup.entry.value, values[10])
        self.assertEqual(AutocompletePopup._on_up_key(popup), "break")
        self.assertEqual(popup.entry.value, values[9])
        popup._show_page(20)
        popup._apply_selection(2)
        AutocompletePopup._on_down_key(popup)
        self.assertEqual(popup.entry.value, values[0])
        AutocompletePopup._on_up_key(popup)
        self.assertEqual(popup.entry.value, values[-1])

    def test_filtered_results_load_next_page_on_boundary(self):
        values = [f"製品{i:05d}" for i in range(23)]
        popup = self.make_popup(values, "製品000")
        popup._page_query = "製品000"
        popup._show_popup(values[:10])
        popup._apply_selection(9)
        AutocompletePopup._on_down_key(popup)
        self.assertEqual(popup.filtered_candidates, values[10:20])

    def test_typing_still_searches_all_products(self):
        from order_entry import search_candidates
        values = [f"製品{i:05d}" for i in range(2000)]
        self.assertEqual(search_candidates("製品01999", values, limit=10)[0], "製品01999")

    def test_up_key_at_top_loads_previous_adjacent_candidates(self):
        values = [f"製品{i:05d}" for i in range(50)]
        popup = self.make_popup(values, "製品00020")
        popup._page_source = values
        popup._page_offset = 20
        popup._show_popup(values[20:30])
        popup._apply_selection(0)
        self.assertEqual(popup.entry.value, "製品00020")

        # 候補の上端で ↑ キーを押すと、手前の10候補（製品00010〜製品00019）が展開され、直前の「製品00019」が選択される
        self.assertEqual(AutocompletePopup._on_up_key(popup), "break")
        self.assertEqual(popup.filtered_candidates, values[10:20])
        self.assertEqual(popup.entry.value, "製品00019")
        self.assertEqual(popup._selected_index, 9)


class TypedDateParseTests(unittest.TestCase):
    def test_accepts_supported_formats(self):
        for text in ("2026/12/05", "2026/12/5", "2026-12-05", "20261205", "２０２６／１２／０５", "2026/12/5 (土)"):
            self.assertEqual(parse_typed_date(text), date(2026, 12, 5), text)

    def test_rejects_invalid_dates(self):
        for text in ("", "2026/13/01", "2026/02/30", "12/05/2026", "2026/12"):
            with self.assertRaises(ValueError, msg=text):
                parse_typed_date(text)


class OrderDataTests(unittest.TestCase):
    def setUp(self):
        self.header = dict(customer_name="顧客A", ship_to="納品先A", required_date=date(2026, 9, 24),
                           due_date=date(2026, 10, 1), purchase_order="PO-001", remarks="", so_comment="")
        self.item = dict(product_name="製品A", width="100.5", length="2000", quantity="3", price="0.10")

    def test_dates_and_decimal_values_keep_precision(self):
        result = collect_order(self.header, [self.item, {}, {}, {}, {}])
        self.assertEqual(result["required_date"], "2026-09-24")
        self.assertEqual(format_order_date(date(2026, 9, 24)), "2026/9/24 (木)")
        self.assertEqual(result["items"][0]["price"], "0.10")
        self.assertEqual(result["items"][0]["quantity"], 3)
        self.assertEqual(result["remarks"], "")

    def test_blank_rows_are_skipped_but_partial_rows_are_rejected(self):
        result = collect_order(self.header, [{}, self.item, {}, self.item, {}])
        self.assertEqual(len(result["items"]), 2)
        with self.assertRaises(OrderValidationError) as error:
            collect_order(self.header, [{}, {"product_name": "入力途中"}])
        self.assertEqual(error.exception.field, (1, "width"))

    def test_incomplete_or_invalid_orders_do_not_pass(self):
        for field, value in (("quantity", "1.5"), ("quantity", "0"), ("width", "-1"),
                             ("length", "abc"), ("price", "NaN"), ("price", "Infinity"),
                             ("price", "1e999999")):
            with self.subTest(field=field, value=value), self.assertRaises(OrderValidationError):
                collect_order(self.header, [{**self.item, field: value}])
        for rows in ([], [{}, {}, {}, {}, {}], [self.item] * 6):
            with self.assertRaises(OrderValidationError):
                collect_order(self.header, rows)
        with self.assertRaises(OrderValidationError):
            collect_order({**self.header, "customer_name": ""}, [self.item])

    def test_five_rows_and_freeform_comments(self):
        self.header["remarks"] = "  注記\n2行目"
        result = collect_order(self.header, [self.item] * 5)
        self.assertEqual(len(result["items"]), 5)
        self.assertEqual(result["remarks"], self.header["remarks"])

    def test_choice_csv_utf8_cp932_and_quoted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "choices.csv"
            content = '顧客名,納品先\n"顧客,A",工場1\n顧客B,工場2\n"顧客,A",工場1\n'
            for encoding in ("utf-8-sig", "cp932"):
                path.write_bytes(content.encode(encoding))
                self.assertEqual(read_choice_csv(path, "customer_name"), ["顧客,A", "顧客B"])
                self.assertEqual(read_choice_csv(path, "ship_to"), ["工場1", "工場2"])
            path.write_text("顧客A\n顧客B\n", encoding="utf-8")
            self.assertEqual(read_choice_csv(path, "customer_name"), ["顧客A", "顧客B"])
            path.write_text("別の列,不明な列\nA,B\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_choice_csv(path, "ship_to")


class ControlTapTests(unittest.TestCase):
    def test_two_separate_taps_toggle_once(self):
        detector = DoubleControlTap()
        detector.press("Control_L", 0)
        self.assertFalse(detector.release("Control_L", .1))
        detector.press("Control_R", .2)
        self.assertTrue(detector.release("Control_R", .3))
        self.assertFalse(detector.release("Control_R", .31))

    def test_repeat_hold_chord_and_focus_reset_do_not_toggle(self):
        for mode in ("repeat", "hold", "chord", "focus", "slow"):
            with self.subTest(mode=mode):
                detector = DoubleControlTap()
                detector.press("Control_L", 0)
                if mode == "repeat":
                    detector.press("Control_L", .1)
                    detector.press("Control_L", .2)
                    self.assertFalse(detector.release("Control_L", .3))
                    continue
                self.assertFalse(detector.release("Control_L", .1))
                detector.press("Control_L", .2)
                if mode == "chord":
                    detector.press("c", .21, 4)
                elif mode == "focus":
                    detector.reset()
                when = 1 if mode in ("hold", "slow") else .3
                self.assertFalse(detector.release("Control_L", when))

    def test_double_control_tap_with_numlock_enabled(self):
        # 0x8 represents NumLock on Windows; it should not cancel double control tap
        detector = DoubleControlTap()
        detector.press("Control_L", 0, state=0x8)
        self.assertFalse(detector.release("Control_L", .1))
        detector.press("Control_L", .2, state=0x8)
        self.assertTrue(detector.release("Control_L", .3))


class ShortcutModifierTests(unittest.TestCase):
    def test_alt_is_prohibited_in_normalize_shortcut(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_shortcut("Alt+F2")
        self.assertIn("Alt", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            normalize_shortcut("Ctrl+Alt+F2")
        self.assertIn("Alt", str(ctx.exception))

        # Single F keys and special keys are allowed
        self.assertEqual(normalize_shortcut("F2"), "F2")
        self.assertEqual(normalize_shortcut("f12"), "F12")
        self.assertEqual(normalize_shortcut("PageUp"), "PageUp")

        # Single letters/numbers are prohibited to avoid hijacking text input
        with self.assertRaises(ValueError):
            normalize_shortcut("A")

        # Ctrl and Shift with keys are allowed
        self.assertEqual(normalize_shortcut("Ctrl+F2"), "Ctrl+F2")
        self.assertEqual(normalize_shortcut("Shift+F2"), "Shift+F2")
        self.assertEqual(normalize_shortcut("Ctrl+Shift+F2"), "Ctrl+Shift+F2")
        self.assertEqual(normalize_shortcut("Ctrl+B"), "Ctrl+B")

    def test_numlock_state_does_not_trigger_alt(self):
        import types
        # Single F2 with NumLock ON (0x8) -> recognized as single key "F2", NOT "Alt+F2"
        event_f2_numlock = types.SimpleNamespace(state=0x8, keysym="F2")
        self.assertEqual(shortcut_from_key_event(event_f2_numlock), "F2")

        # Single F2 with 0x0 -> "F2"
        event_f2_pure = types.SimpleNamespace(state=0x0, keysym="F2")
        self.assertEqual(shortcut_from_key_event(event_f2_pure), "F2")

        # Single regular character 'a' with NumLock ON -> None (not allowed as single key)
        event_char_numlock = types.SimpleNamespace(state=0x8, keysym="a")
        self.assertIsNone(shortcut_from_key_event(event_char_numlock))

        # state 0x4 | 0x8 is Control + NumLock. Should be Ctrl+F2, NOT Alt+Ctrl+F2.
        event_ctrl_numlock = types.SimpleNamespace(state=0x4 | 0x8, keysym="F2")
        self.assertEqual(shortcut_from_key_event(event_ctrl_numlock), "Ctrl+F2")

        # state 0x1 | 0x4 | 0x8 is Shift + Control + NumLock.
        event_all = types.SimpleNamespace(state=0x1 | 0x4 | 0x8, keysym="F2")
        self.assertEqual(shortcut_from_key_event(event_all), "Ctrl+Shift+F2")


class OrderNavigationTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        from order_entry import OrderEntryPanel
        self.root = ctk.CTk()
        self.root.geometry("1000x700")
        colors = {
            "panel": "#F8FAFC", "border": "#E2E8F0", "text": "#1E293B",
            "muted": "#64748B", "button": "#E2E8F0", "hover": "#CBD5E1",
            "accent": "#2563EB", "on_accent": "#FFFFFF", "accent_hover": "#1D4ED8",
            "error": "#EF4444",
        }
        self.panel = OrderEntryPanel(self.root, colors, "Meiryo UI", lambda p: None, lambda: None)
        self.panel.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def test_right_arrow_on_ship_to_moves_to_required_date(self):
        panel = self.panel
        ship_inner = panel._get_inner_widget(panel.fields["ship_to"])
        ship_inner.focus_force()
        self.root.update()
        ship_inner.event_generate("<Right>")
        self.root.update()
        self.assertIs(self.root.focus_get(), panel._get_inner_widget(panel.fields["required_date"]))

    def test_arrow_key_spatial_navigation(self):
        panel = self.panel
        root = self.root

        # Helper to get the inner focused widget
        def inner(f):
            return panel._get_inner_widget(f)

        # Start at customer_name
        inner(panel.fields["customer_name"]).focus_set()
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["customer_name"]))

        # Right -> ship_to
        inner(panel.fields["customer_name"]).event_generate("<Right>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["ship_to"]))

        # Down -> required_date
        root.focus_get().event_generate("<Down>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["required_date"]))

        # Down -> due_date
        root.focus_get().event_generate("<Down>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["due_date"]))

        # Down -> purchase_order
        root.focus_get().event_generate("<Down>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["purchase_order"]))

        # Down -> remarks or so_comment
        root.focus_get().event_generate("<Down>")
        root.update()
        self.assertIn(root.focus_get(), (inner(panel.fields["remarks"]), inner(panel.fields["so_comment"])))

        # From detail row 0 product_name, navigate right across all columns
        inner(panel.fields[(0, "product_name")]).focus_set()
        root.update()
        for col in ("width", "length", "quantity", "price"):
            root.focus_get().event_generate("<Right>")
            root.update()
            self.assertIs(root.focus_get(), inner(panel.fields[(0, col)]))

        # Down to row 1 price
        root.focus_get().event_generate("<Down>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields[(1, "price")]))

        # Up back to row 0 price
        root.focus_get().event_generate("<Up>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields[(0, "price")]))

        # Left across row 0
        for col in ("quantity", "length", "width", "product_name"):
            root.focus_get().event_generate("<Left>")
            root.update()
            self.assertIs(root.focus_get(), inner(panel.fields[(0, col)]))

        # Up to remarks
        root.focus_get().event_generate("<Up>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["remarks"]))

        # Up to purchase_order
        root.focus_get().event_generate("<Up>")
        root.update()
        self.assertIs(root.focus_get(), inner(panel.fields["purchase_order"]))


class DateFieldKeyboardNavTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        self.root = ctk.CTk()
        self.root.geometry("600x400")
        colors = {
            "panel": "#F8FAFC", "border": "#E2E8F0", "text": "#1E293B",
            "muted": "#64748B", "button": "#E2E8F0", "hover": "#CBD5E1",
            "accent": "#2563EB", "on_accent": "#FFFFFF", "accent_hover": "#1D4ED8",
            "error": "#EF4444",
        }
        self.df = DateField(self.root, colors, "Meiryo UI")
        self.df.pack(padx=20, pady=20)
        self.root.update()

    def tearDown(self):
        self.df.close_calendar()
        self.root.destroy()

    def test_typing_digit_opens_popup_and_accepts_direct_date(self):
        df, root = self.df, self.root
        df.set_date(date(2026, 9, 24))
        df.entry._entry.focus_force()
        root.update()
        df.entry._entry.event_generate("<KeyPress-2>")
        root.update()
        root.after(50)
        for _ in range(5):
            root.update()
        self.assertTrue(df._is_calendar_open())
        typed = df.input_entry._entry
        self.assertEqual(typed.get(), "2")
        typed.insert("end", "026/12/05")
        typed.focus_force()
        root.update()
        typed.event_generate("<Return>")
        root.update()
        self.assertFalse(df._is_calendar_open())
        self.assertEqual(df.value, date(2026, 12, 5))
        self.assertEqual(df.variable.get(), "2026/12/5 (土)")

    def test_invalid_direct_date_keeps_popup_open(self):
        df, root = self.df, self.root
        df.set_date(date(2026, 9, 24))
        df.open_calendar()
        root.update()
        df._start_typing("2026/02/30")
        df.input_entry._entry.focus_force()
        root.update()
        df.input_entry._entry.event_generate("<Return>")
        root.update()
        self.assertTrue(df._is_calendar_open())
        self.assertEqual(df.value, date(2026, 9, 24))

    def test_calendar_cursor_move_updates_direct_input(self):
        df, root = self.df, self.root
        df.set_date(date(2026, 9, 24))
        df.open_calendar()
        for _ in range(5):
            root.update()
        df._move_cursor_date(1)
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 9, 25))
        self.assertEqual(df.input_var.get(), "2026/09/25")

    def test_calendar_cursor_key_navigation_and_confirm(self):
        df = self.df
        root = self.root

        # Initial date
        df.set_date(date(2026, 9, 24))
        self.assertEqual(df.value, date(2026, 9, 24))

        # Open calendar
        df.open_calendar()
        root.update()
        self.assertTrue(df._is_calendar_open())
        self.assertEqual(df.cursor_date, date(2026, 9, 24))

        # Navigate Right -> 2026-09-25
        df.entry._entry.event_generate("<Right>")
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 9, 25))

        # Navigate Down -> 2026-10-02 (advances to next month)
        df.entry._entry.event_generate("<Down>")
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 10, 2))
        self.assertEqual(df.month, date(2026, 10, 1))

        # Navigate Up -> 2026-09-25 (returns to September)
        df.entry._entry.event_generate("<Up>")
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 9, 25))
        self.assertEqual(df.month, date(2026, 9, 1))

        # Navigate Left -> 2026-09-24
        df.entry._entry.event_generate("<Left>")
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 9, 24))

        # Navigate Right twice -> 2026-09-26
        df.entry._entry.event_generate("<Right>")
        root.update()
        df.entry._entry.event_generate("<Right>")
        root.update()
        self.assertEqual(df.cursor_date, date(2026, 9, 26))

        # Confirm with Return
        df.entry._entry.event_generate("<Return>")
        root.update()

        # Calendar should be closed and date confirmed
        self.assertFalse(df._is_calendar_open())
        self.assertEqual(df.value, date(2026, 9, 26))
        self.assertEqual(df.variable.get(), format_order_date(date(2026, 9, 26)))

    def test_calendar_no_flicker_retains_widgets(self):
        df = self.df
        root = self.root

        df.set_date(date(2026, 9, 15))
        df.open_calendar()
        root.update()

        # Capture widget IDs of buttons and month label
        label_id = id(df._month_label)
        btn_ids = [id(btn) for row in df._cell_buttons for btn in row]
        btn_15 = df._date_to_button[date(2026, 9, 15)]
        btn_16 = df._date_to_button[date(2026, 9, 16)]

        # Move cursor to 16
        df.entry._entry.event_generate("<Right>")
        root.update()

        # Label and button objects MUST be identically retained (no destruction)
        self.assertEqual(id(df._month_label), label_id)
        current_btn_ids = [id(btn) for row in df._cell_buttons for btn in row]
        self.assertEqual(current_btn_ids, btn_ids)

        # Style check: 16 is now accented, 15 is panel
        self.assertEqual(btn_16.cget("bg"), df.colors["accent"])
        self.assertEqual(btn_15.cget("bg"), df.colors["panel"])
        self.assertIs(df._selected_button, btn_16)


class CustomerInfoAndAddressTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        from order_entry import OrderEntryPanel, CustomerInfoData
        self.root = ctk.CTk()
        self.root.geometry("800x600")
        self.colors = {
            "panel": "#F8FAFC", "border": "#E2E8F0", "text": "#1E293B",
            "muted": "#64748B", "button": "#E2E8F0", "hover": "#CBD5E1",
            "accent": "#2563EB", "on_accent": "#FFFFFF", "accent_hover": "#1D4ED8",
            "error": "#EF4444",
        }
        self.sample_data = {
            "CUST01": {
                "name": "テスト顧客A",
                "destinations": {
                    "DEST01": {
                        "name": "納品先A1",
                        "address": "100-0001\n東京都千代田区1-1\nTEL:03-1111-2222",
                    },
                    "DEST02": {
                        "name": "納品先A2",
                        "address": "200-0002\n大阪府大阪市2-2\nTEL:06-3333-4444",
                    },
                },
            },
            "CUST02": {
                "name": "テスト顧客B",
                "destinations": {
                    "DEST03": {
                        "name": "納品先B1",
                        "address": "300-0003\n愛知県名古屋市3-3\nTEL:052-5555-6666",
                    },
                },
            },
        }
        self.cust_info = CustomerInfoData(self.sample_data)
        self.panel = OrderEntryPanel(
            self.root, self.colors, "Meiryo UI",
            lambda p: None, lambda: None, customer_info=self.cust_info,
        )
        self.panel.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.panel.close_popups()
        self.root.destroy()

    def test_customer_and_destination_linking_with_address(self):
        panel = self.panel
        customer_combo = panel.fields["customer_name"]
        ship_to_combo = panel.fields["ship_to"]
        self.assertEqual(customer_combo.cget("values"), ["テスト顧客A", "テスト顧客B"])

        # テスト顧客Aを選択 -> 納品先ドロップダウンに「納品先A1」「納品先A2」
        customer_combo.set("テスト顧客A")
        panel._on_customer_selected("テスト顧客A")
        self.assertEqual(ship_to_combo.cget("values"), ["納品先A1", "納品先A2"])

        # 納品先A1を選択 -> address_box に該当住所が表示される
        ship_to_combo.set("納品先A1")
        panel._on_ship_to_selected("納品先A1")
        address_text = panel.address_box.get("1.0", "end-1c").strip()
        self.assertEqual(address_text, "100-0001\n東京都千代田区1-1\nTEL:03-1111-2222")

        # 納品先A2を選択 -> address_box が更新される
        ship_to_combo.set("納品先A2")
        panel._on_ship_to_selected("納品先A2")
        address_text = panel.address_box.get("1.0", "end-1c").strip()
        self.assertEqual(address_text, "200-0002\n大阪府大阪市2-2\nTEL:06-3333-4444")

        # テスト顧客B（納品先が1件）を選択 -> 自動で「納品先B1」が選択され住所が表示される
        customer_combo.set("テスト顧客B")
        panel._on_customer_selected("テスト顧客B")
        self.assertEqual(ship_to_combo.cget("values"), ["納品先B1"])
        self.assertEqual(ship_to_combo.get(), "納品先B1")
        address_text = panel.address_box.get("1.0", "end-1c").strip()
        self.assertEqual(address_text, "300-0003\n愛知県名古屋市3-3\nTEL:052-5555-6666")

    def test_autocomplete_search_and_keyboard_selection(self):
        panel = self.panel
        customer_combo = panel.fields["customer_name"]
        entry = customer_combo._entry

        from order_entry import search_candidates
        candidates = ["ﾀﾞｲｵｰﾐｳﾗ株式会社", "株式会社なかじま", "凸版印刷株式会社"]
        self.assertEqual(search_candidates("だいお", candidates), ["ﾀﾞｲｵｰﾐｳﾗ株式会社"])
        self.assertEqual(search_candidates("ナカジマ", candidates), ["株式会社なかじま"])
        self.assertEqual(search_candidates("印刷", candidates), ["凸版印刷株式会社"])

        # 顧客名入力欄に「てすと」と入力（カタカナ「テスト」にひらがなで一致）
        entry.delete(0, "end")
        entry.insert(0, "てすと")
        panel.customer_autocomplete._on_key_release(type("Event", (), {"keysym": "a"})())
        self.root.update()

        # ポップアップが開いて「テスト顧客A」が候補に出ていること
        self.assertTrue(panel.customer_autocomplete.is_open())
        self.assertIn("テスト顧客A", panel.customer_autocomplete.filtered_candidates)

        # Downキーで候補選択
        panel.customer_autocomplete._on_down_key(None)
        self.assertEqual(panel.customer_autocomplete._selected_index, 0)

        # Returnキーで確定
        panel.customer_autocomplete._on_return_key(None)
        self.root.update()

        # ポップアップが閉じ、顧客名に反映され、納品先候補も連動していること
        self.assertFalse(panel.customer_autocomplete.is_open())
        self.assertEqual(customer_combo.get(), "テスト顧客A")
        self.assertEqual(panel.fields["ship_to"].cget("values"), ["納品先A1", "納品先A2"])

    def test_order_output_terminal_demo_button(self):
        from order_entry import OrderOutputTerminalWindow
        submitted_payloads = []

        class DummyParent:
            def __init__(self, root):
                self.root = root
                self.order_panel = None
            def winfo_rootx(self): return 100
            def winfo_rooty(self): return 100
            def winfo_width(self): return 800
            def winfo_height(self): return 600
            def _process_order_submission(self, payload):
                submitted_payloads.append(payload)

        parent = DummyParent(self.root)
        term_win = OrderOutputTerminalWindow(parent=self.root)
        term_win.parent = parent

        # デモボタンが存在すること
        self.assertTrue(hasattr(term_win, "demo_btn"))
        self.assertEqual(term_win.demo_btn.cget("text"), "🧪 デモ注文送信 (2製品)")

        # デモボタンを押下 (_on_demo_clicked)
        term_win._on_demo_clicked()

        # 送信された payload の検証
        self.assertEqual(len(submitted_payloads), 1)
        p = submitted_payloads[0]
        self.assertEqual(p["customer_code"], "20000600")
        self.assertEqual(p["ship_to_code"], "20000601")
        today = date.today()
        exp_due = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        exp_req = (today + timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertEqual(p["required_date"], exp_req)
        self.assertEqual(p["due_date"], exp_due)
        self.assertEqual(len(p["items"]), 2)
        self.assertEqual(p["items"][0]["product_name"], "BW0100D")
        self.assertEqual(p["items"][1]["product_name"], "BW0116Q3-2")

        # ターミナルウィンドウ内にも反映されていること
        self.assertEqual(term_win.submission_count, 1)
        self.assertEqual(term_win.last_payload, p)

        term_win.destroy()


if __name__ == "__main__":
    unittest.main()

