"""Header tests with explicit VT cursor positions. Scenarios are synthetic, not live proof."""
import unittest
from unittest.mock import patch
from order_entry import SalesOrderAutomationController, KEY_SEQUENCES
from tests.order_replay import StrictReplay, ExpectedSend


def header(field, bill="CUST", ship="DEST", warning=""):
    row = f"Order: SO123456  Sold-To: CUST     Bill To: {bill:<8} Ship-To: {ship:<8}"
    date = "Order Date: 10/02/26 Line Pricing: Yes"
    labels = {"sold": "Sold-To:", "bill": "Bill To:", "ship": "Ship-To:"}
    y, x = (3, len("Order Date: ")) if field == "date" else (2, row.index(labels[field]) + len(labels[field]) + 1)
    return f"Sales Order Maintenance\n{row}\n{date}\n{warning}\x1b[{y};{x + 1}H"


class HeaderReady(Exception):
    pass


class HeaderReadinessTests(unittest.TestCase):
    def controller(self, replay):
        return SalesOrderAutomationController(replay, replay.get_screen_text,
            {"customer_code": "CUST", "ship_to_code": "DEST"},
            sleep_func=replay.sleep, default_timeout=2)

    def run_header(self, expected, result=HeaderReady, initial=None):
        replay = StrictReplay(initial or header("sold"), expected)
        controller = self.controller(replay)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now), \
             patch("order_entry.build_order_header_fields", side_effect=HeaderReady):
            with self.assertRaises(result):
                controller.execute_full_order()
        replay.assert_finished()
        return replay

    def test_enter_already_advances_without_extra_f1(self):
        self.run_header([ExpectedSend("CUST\r", header("bill"), 0.8),
            ExpectedSend("CUST\r", header("ship"), 0.7),
            ExpectedSend("DEST\r", header("date"), 0.7)])

    def test_sold_to_requires_one_f1_and_warning_clear(self):
        self.run_header([ExpectedSend("CUST\r", header("sold")),
            ExpectedSend(KEY_SEQUENCES["F1"], header("sold", warning="Press space bar to continue.")),
            ExpectedSend(" ", header("bill"), 0.7),
            ExpectedSend("CUST\r", header("ship")), ExpectedSend("DEST\r", header("date"))])

    def test_static_labels_cannot_send_ship_to_while_bill_to_is_active(self):
        replay = self.run_header([ExpectedSend("CUST\r", header("bill")),
            ExpectedSend("CUST\r", header("bill"))], TimeoutError)
        self.assertNotIn("DEST\r", [data for _, data in replay.sent])

    def test_qad_error_stops_before_ship_to(self):
        self.run_header([ExpectedSend("CUST\r", header("bill")),
            ExpectedSend("CUST\r", header("bill", warning="ERROR: Not a valid customer. Please re-enter."))], RuntimeError)

    def test_wrong_codes_stop_before_header_paste(self):
        self.run_header([ExpectedSend("CUST\r", header("bill")),
            ExpectedSend("CUST\r", header("ship")),
            ExpectedSend("DEST\r", header("date", bill="DEST"))], RuntimeError)

    def test_missing_codes_stop_before_header_paste(self):
        replay = StrictReplay("Order Date:")
        with self.assertRaises(RuntimeError):
            self.controller(replay)._verify_header_codes("CUST", "DEST")

    def test_unknown_cursor_sends_nothing(self):
        self.run_header([], TimeoutError, initial=header("sold") + "\x1b[24;1H")

    def test_consecutive_warnings_before_bill_to(self):
        self.run_header([ExpectedSend("CUST\r", header("sold", warning="Category=A Press space bar to continue.")),
            ExpectedSend(" ", header("sold"), followup=(0.3, header("sold", warning="Credit warning Press space bar to continue."))),
            ExpectedSend(" ", header("bill")), ExpectedSend("CUST\r", header("ship")),
            ExpectedSend("DEST\r", header("date"))])
