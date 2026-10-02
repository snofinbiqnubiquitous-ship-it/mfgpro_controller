"""Offline behaviour tests for the distributed add-ons (no SSH, no browser)."""
import importlib.util
import unittest
from pathlib import Path

from addon_host import AddonAPI, AddonHost, AddonRecord
from qad_report import KEY_CTRL_F, KEY_F1, ReportShell
from tests.qad_fakes import FakeClient, FakeClock, FakeShell, REPORT_ROWS, login_replies, prn_stream
from tests.test_addon_host import FakeUI

ADDONS = Path(__file__).resolve().parents[1] / "addons"


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"test_addon_{name}", ADDONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AddonUI(FakeUI):
    def __init__(self):
        super().__init__()
        self.messages = []

    def qad_credentials(self):
        return ("mfg03", 22, "user", "secret")

    def show_message(self, kind, title, message, parent):
        self.messages.append((kind, title))


class DataTransmissionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module("data_transmission")
        self.clock = FakeClock()
        self.shells = []
        self.replies = []
        self.sent_to_gas = []
        self.ui = AddonUI()
        self.host = AddonHost(self.ui)
        record = AddonRecord("data_transmission", "データ送信", ADDONS / "data_transmission.py")
        self.module.register(AddonAPI(self.host, record), shell_factory=self.shell_factory,
                             sender=lambda data, url, title: self.sent_to_gas.append((data, url)),
                             clock=self.clock)
        self.host.records.append(record)
        self.host._finish_loading()

    def shell_factory(self, *login):
        replies = self.replies.pop(0) if self.replies else {}
        shell = FakeShell(self.clock, replies)
        self.shells.append(shell)
        return ReportShell(*login, client_factory=lambda: FakeClient(shell), clock=self.clock, sleep=self.clock.sleep)

    def run_action(self, key):
        self.host.actions[f"data_transmission.{key}"][1]()
        threads = [t for t in __import__("threading").enumerate() if t.name.startswith("addon-data_transmission")]
        for thread in threads:
            while thread.is_alive():
                self.host.drain()
                thread.join(0.01)
        self.host.drain()

    def test_inventory_keeps_key_sequence_and_forwards_rows(self):
        replies = login_replies()
        replies[KEY_CTRL_F] = [(1.0, prn_stream())]
        self.replies.append(replies)
        self.run_action("inventory")
        self.assertEqual(self.sent_to_gas, [(REPORT_ROWS, self.module.INVENTORY_GAS_URL)])
        self.assertEqual(self.shells[0].sent, ["2\r", "1\r", " ", "99.3.6.1\r", "\r" * 8 + "1fgi\r1fgi\r",
                                               KEY_F1, "32prn\r", KEY_F1, KEY_F1, KEY_CTRL_F])
        self.assertIn("転送完了", self.ui.statuses[-1][0])
        self.assertFalse(self.host.lock(self.module.BUSY).locked())
        self.assertTrue(all(state == "normal" for state in self.ui.states.values()))

    def test_unconfirmed_main_menu_stops_before_menu_code(self):
        self.replies.append({"2\r": [(0.2, "Selection:")], "1\r": [(0.2, "Unexpected screen")]})
        self.run_action("inventory")
        self.assertEqual(self.shells[0].sent, ["2\r", "1\r"])
        self.assertEqual(self.sent_to_gas, [])
        self.assertEqual(self.ui.messages, [("error", "エラー")])
        self.assertEqual(self.ui.statuses[-1][1], "error")
        self.assertFalse(self.host.lock(self.module.BUSY).locked())

    def test_second_start_is_rejected_while_busy(self):
        self.host.lock(self.module.BUSY).acquire()
        self.host.actions["data_transmission.inventory"][1]()
        self.assertEqual(self.ui.messages, [("warning", "データ送信実行中")])
        self.assertEqual(self.shells, [])

    def test_parallel_continues_after_first_report_fails(self):
        self.replies.append(login_replies(prompt=False))           # 99.7.6.20 screen never appears
        sales = login_replies(prompt=False)
        sales["99.7.5.11\r"] = [(0.5, "Invoice")]
        sales[KEY_CTRL_F] = [(1.0, prn_stream())]
        self.replies.append(sales)
        self.run_action("parallel")
        self.assertEqual(len(self.sent_to_gas), 1)
        payload, url = self.sent_to_gas[0]
        self.assertEqual((payload["menu"], payload["data"], url), ("99.7.5.11", REPORT_ROWS, self.module.PARALLEL_GAS_URL))
        self.assertIn("一部エラー", self.ui.statuses[-1][0])
        self.assertNotIn("99.7.5.11\r", self.shells[0].sent)

    def test_complaint_input_is_checked_before_qad(self):
        check = self.module.validate_complaint_input
        self.assertEqual(check(" BW0100D ", "2026/04/01", "2026/10/02", ""), ("BW0100D", "04/01/26", "10/02/26", ""))
        for args in (("", "2026/04/01", "2026/10/02", ""), ("BW 01", "2026/04/01", "2026/10/02", ""),
                     ("製品", "2026/04/01", "2026/10/02", ""), ("BW0100D", "2026/02/30", "2026/10/02", ""),
                     ("BW0100D", "2026/10/03", "2026/10/02", ""), ("BW0100D", "2026/04/01", "2026/10/02", "L 1")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                check(*args)

    def test_complaint_dialog_flow(self):
        captured = {}
        self.module.ComplaintDialog = lambda parent, font, submit: captured.setdefault("submit", submit)

        class Dialog:
            def __init__(self):
                self.events = []
            def winfo_exists(self):
                return True
            def set_running(self, running):
                self.events.append(("running", running))
            def set_status(self, text, color=""):
                self.events.append(("status", text))
            def close(self):
                self.events.append(("close",))

        replies = login_replies("Roll Japan Production")
        replies["99.3.21.4\r"] = [(0.5, "Item Number")]
        replies[KEY_CTRL_F] = [(1.0, prn_stream())]
        self.replies.append(replies)
        self.host.actions["data_transmission.complaint"][1]()
        dialog = Dialog()
        captured["submit"](dialog, "BW0100D", "04/01/26", "10/02/26", "N123")
        for thread in [t for t in __import__("threading").enumerate() if t.name.startswith("addon-data_transmission")]:
            while thread.is_alive():
                self.host.drain()
                thread.join(0.01)
        self.host.drain()
        self.assertEqual(self.sent_to_gas, [(REPORT_ROWS, self.module.COMPLAINT_GAS_URL)])
        self.assertIn("BW0100D\rBW0100D\r\r\r04/01/26\r10/02/26\r1fgi\r1fgi\r\r\r\r\rN123\rN123\r" + "\r" * 11,
                      self.shells[0].sent)
        self.assertEqual(dialog.events[0], ("running", True))
        self.assertEqual(dialog.events[-2:], [("running", False), ("close",)])


class FakeTerminalApi:
    def __init__(self, main_after_f4=True, output_after_f1=True):
        self.main = False
        self.main_after_f4 = main_after_f4
        self.output_after_f1 = output_after_f1
        self.output = False
        self.text = ""
        self.sent = []
        self.started = False

    def set_status(self, *args, **kwargs):
        pass

    log_info = log_error = set_status

    def is_main_menu(self):
        return self.main

    def screen_text(self):
        return self.text

    def is_cursor_at_output_field(self):
        return self.output

    def send_to_tab(self, tab, data):
        self.sent.append(data)
        if data == "\x1bOS":
            self.main = self.main_after_f4
        elif data == "99.7.6.20\r":
            self.main = False
            self.text = "Sales Order Detail Report"
        elif data == "\x1bOP":
            self.output = self.output_after_f1

    def start_32printer(self, tab):
        self.started = True


class OrderBookingTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module("quick_order_booking")
        self.clock = FakeClock()

    def run_macro(self, api):
        self.module.run_order_booking(api, "tab", clock=self.clock, sleep=self.clock.sleep)

    def test_success(self):
        api = FakeTerminalApi()
        self.run_macro(api)
        self.assertEqual(api.sent[:2], ["\x1bOS", "99.7.6.20\r"])
        self.assertEqual(api.sent[2], "\r" * 6 + "1fgi\r1fgi\r")
        self.assertTrue(api.sent[3].startswith("\r" * 8))
        self.assertTrue(api.started)

    def test_stops_when_main_menu_is_not_reached(self):
        api = FakeTerminalApi(main_after_f4=False)
        with self.assertRaisesRegex(RuntimeError, "メインメニュー"):
            self.run_macro(api)
        self.assertEqual(api.sent, ["\x1bOS"] * 4)

    def test_stops_before_32prn_when_output_field_is_not_reached(self):
        api = FakeTerminalApi(output_after_f1=False)
        with self.assertRaisesRegex(RuntimeError, "Output"):
            self.run_macro(api)
        self.assertFalse(api.started)
