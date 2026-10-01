"""正常系・通信境界のオフライン回帰試験。"""

import unittest
from unittest.mock import patch

from order_entry import SalesOrderAutomationController
from tests.order_replay import StrictReplay, ExpectedSend, step6_replay


class ReplayTests(unittest.TestCase):
    def test_fragmented_cp932_and_escape_sequence_wait_for_complete_text(self):
        replay = StrictReplay()
        data = replay.screen_bytes("納品先")
        # ESCシーケンスと日本語文字の途中を含め、1バイトずつ遅延受信する。
        for index, byte in enumerate(data, 1):
            replay.schedule(index * 0.05, bytes([byte]))
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            result = controller.wait_for_screen(lambda text: "納品先" in text)
        self.assertIn("納品先", result)
        self.assertNotIn("�", result)
        self.assertGreaterEqual(replay.now, len(data) * 0.05)
        replay.assert_finished()

    def test_warning_is_answered_by_space_without_enter(self):
        replay = StrictReplay("Press space bar to continue.",
                              [ExpectedSend(" ", "ready", 0.2)])
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            controller.wait_for_screen(lambda text: "ready" in text)
        replay.assert_finished()

    def test_disconnect_stops_waiting(self):
        replay = StrictReplay()
        replay.schedule(0.1, None)
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            with self.assertRaises(InterruptedError):
                controller.wait_for_screen(lambda text: False)
        self.assertEqual(replay.sent, [])

    def test_timeout_does_not_send_keys(self):
        replay = StrictReplay()
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep, default_timeout=0.2)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            with self.assertRaises(TimeoutError):
                controller.wait_for_screen(lambda text: False)
        self.assertEqual(replay.sent, [])

    def test_user_abort_does_not_send_keys(self):
        replay = StrictReplay()
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {})
        controller.abort()
        with self.assertRaises(InterruptedError):
            controller.send("\r")
        self.assertEqual(replay.sent, [])

    def test_single_line_every_keystroke_is_checked(self):
        replay, payload = step6_replay()
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, payload,
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            self.assertEqual(controller.execute_step6(), "SO123456")
        replay.assert_finished()

    def test_replay_rejects_early_keys_instead_of_ignoring_them(self):
        replay = StrictReplay("old", [ExpectedSend("a", "new", 1), ExpectedSend("b")])
        replay.send("a")
        with self.assertRaisesRegex(AssertionError, "先走り"):
            replay.send("b")
        replay.sleep(1)
        replay.send("b")
        replay.assert_finished()

    def test_slow_server_responses_are_awaited_before_next_key(self):
        # 旧実装の固定待機(0.12〜0.25秒)を超える0.7秒の応答遅延でも、応答前に次のキーを送らない
        replay, payload = step6_replay(delay=0.7)
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, payload,
                                                     sleep_func=replay.sleep)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            self.assertEqual(controller.execute_step6(), "SO123456")
        replay.assert_finished()

    def test_screen_switch_wait_is_not_shortened_by_speed_setting(self):
        # 設計書2.10: Ln自動採番のEnter後は、速度設定10%でも0.4秒未満で次のキーを送らない
        replay, payload = step6_replay()
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, payload,
                                                     sleep_func=replay.sleep, sleep_rate_percent=10)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            controller.execute_step6()
        replay.assert_finished()
        (enter_at, enter), (next_at, _) = replay.sent[0], replay.sent[1]
        self.assertEqual(enter, "\r")
        self.assertGreaterEqual(next_at - enter_at, 0.4 - 1e-9)

    def test_missing_response_is_waited_for_and_logged(self):
        replay = StrictReplay("ready", [ExpectedSend("X")])
        logs = []
        controller = SalesOrderAutomationController(replay, replay.get_screen_text, {},
                                                     sleep_func=replay.sleep, logger=logs.append)
        with patch("order_entry.time.monotonic", side_effect=lambda: replay.now):
            self.assertFalse(controller.send_and_settle("X", 0.1))
        self.assertGreaterEqual(replay.now, controller.RESPONSE_WINDOW)
        self.assertTrue(any("画面応答がありません" in line for line in logs))
        replay.assert_finished()
