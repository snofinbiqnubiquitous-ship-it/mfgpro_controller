"""未解決の安全条件。失敗をexpectedFailureで合格扱いにしない。

scripts/verify_order.py --acceptance で明示的に実行する。
"""

import unittest
from unittest.mock import patch
from order_entry import SalesOrderAutomationController, KEY_SEQUENCES
from tests.order_replay import StrictReplay, ExpectedSend, step6_replay


class AcceptanceTests(unittest.TestCase):
    def wait(self, replay, predicate):
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep, default_timeout=2)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            controller.wait_for_screen(predicate)
        replay.assert_finished()

    def test_background_label_must_not_bypass_warning(self):
        replay = StrictReplay("Sold-To:\nPress space bar to continue.",
                              [ExpectedSend(" ", "Sold-To:", 0.6)])
        self.wait(replay, lambda text: "sold-to:" in text)
        self.assertGreaterEqual(replay.now, 0.6)

    def test_delayed_warning_clear_must_not_receive_duplicate_space(self):
        replay = StrictReplay("Press space bar to continue.",
                              [ExpectedSend(" ", "ready", 0.9)])
        self.wait(replay, lambda text: "ready" in text)

    def test_category_text_without_prompt_must_not_receive_space(self):
        replay = StrictReplay("Category=A")
        replay.schedule(0.5, replay.screen_bytes("ready"))
        self.wait(replay, lambda text: "ready" in text)

    def test_missing_bill_to_transition_must_stop_before_next_field(self):
        from tests.test_header_readiness import header
        replay = StrictReplay(header("sold"), [ExpectedSend("TESTCUSTOMER\r")])
        controller = SalesOrderAutomationController(
            replay, replay.get_screen_text,
            {"customer_code": "TESTCUSTOMER", "ship_to_code": "TESTDEST"},
            sleep_func=replay.sleep, default_timeout=1)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            with self.assertRaises(TimeoutError):
                controller.execute_full_order()
        replay.assert_finished()

    def test_warning_after_first_totals_f1_must_not_receive_second_f1(self):
        replay, payload = step6_replay(early_warning=True)
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, payload,
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            controller.execute_step6()
        replay.assert_finished()

    def test_completed_without_warning_must_not_receive_space(self):
        replay, payload = step6_replay(no_warning=True)
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, payload,
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            controller.execute_step6()
        replay.assert_finished()
