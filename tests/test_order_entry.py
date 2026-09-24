import tempfile
from datetime import date
from pathlib import Path
import unittest

from order_entry import DoubleControlTap, OrderValidationError, collect_order, format_order_date, read_choice_csv


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


if __name__ == "__main__":
    unittest.main()
