"""Offline tests for 32prn decoding, report parsing and raw shell waits."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from qad_report import (ReportShell, ShellWaitTimeout, cleanup_gas_temp_files, decode_32prn_stream,
                        parse_report_to_rows, send_to_gas_via_browser)
from tests.qad_fakes import FakeClient, FakeClock, FakeShell, REPORT_ROWS, REPORT_TEXT, prn_stream


def make_shell(replies=None, chunk_size=None):
    clock = FakeClock()
    shell = FakeShell(clock, replies, chunk_size)
    report = ReportShell("h", 22, "u", "p", client_factory=lambda: FakeClient(shell), clock=clock, sleep=clock.sleep)
    report.open(80, 24)
    return report, shell, clock


class DecodeAndParseTests(unittest.TestCase):
    def test_round_trip_with_each_terminator(self):
        for terminator in (b"end\r\n", b"end\n", b"end\x1b[4i", b"end"):
            with self.subTest(terminator=terminator):
                tail = b"" if terminator == b"end" else b"tail"
                text = decode_32prn_stream(b"screen noise\r\n" + prn_stream(terminator=terminator) + tail)
                self.assertEqual(text, REPORT_TEXT)

    def test_missing_markers_are_reported(self):
        with self.assertRaisesRegex(ValueError, "ヘッダー"):
            decode_32prn_stream(b"no stream")
        with self.assertRaisesRegex(ValueError, "フッター"):
            decode_32prn_stream(b"begin 0 32PRINTER\r\nM")

    def test_parse_fixed_width_report(self):
        self.assertEqual(parse_report_to_rows(REPORT_TEXT), REPORT_ROWS)


class ShellWaitTests(unittest.TestCase):
    def test_main_menu_split_across_packets_and_prompt_answered_once(self):
        shell, fake, _ = make_shell({" ": [(0.2, "Please "), (0.3, "select a function:")]})
        fake.schedule(0.1, "Pausing... Press space bar to continue")
        self.assertTrue(shell.wait_main_menu(timeout=5))
        self.assertEqual(fake.sent, [" "])

    def test_missing_main_menu_stops(self):
        shell, fake, clock = make_shell()
        fake.schedule(0.1, "Some other screen")
        with self.assertRaises(ShellWaitTimeout):
            shell.wait_main_menu(timeout=3)
        self.assertGreaterEqual(clock.now, 3)

    def test_wait_text_keeps_cp932_bytes_split_across_packets(self):
        shell, fake, _ = make_shell(chunk_size=1)
        fake.schedule(0.1, "在庫レポート Item Number")
        self.assertTrue(shell.wait_text("在庫レポート", timeout=10))


class ReceiveTests(unittest.TestCase):
    def test_end_marker_split_across_packets(self):
        shell, fake, _ = make_shell(chunk_size=5)
        fake.schedule(0.1, prn_stream())
        rows, _, size = shell.receive_rows(max_wait=60)
        self.assertEqual(rows, REPORT_ROWS)
        self.assertEqual(size, len(prn_stream()))

    def test_end_text_before_header_is_ignored(self):
        shell, fake, _ = make_shell()
        fake.schedule(0.1, b"Output:\r\nend\r\n")
        fake.schedule(0.5, prn_stream())
        rows, _, _ = shell.receive_rows(max_wait=60)
        self.assertEqual(rows, REPORT_ROWS)

    def test_waiting_progress_is_reported_once_per_four_seconds(self):
        shell, fake, _ = make_shell()
        fake.schedule(9.0, prn_stream())
        events = []
        shell.receive_32prn(max_wait=60, on_progress=lambda stage, elapsed: events.append((stage, elapsed)))
        self.assertEqual(events, [("waiting", 4), ("waiting", 8), ("capturing", 9)])

    def test_timeout(self):
        shell, _, _ = make_shell()
        with self.assertRaises(ShellWaitTimeout):
            shell.receive_32prn(max_wait=2)


class GasPageTests(unittest.TestCase):
    def test_page_is_written_and_old_pages_are_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "gas_submit_old.html"
            old.write_text("x", encoding="utf-8")
            os.utime(old, (time.time() - 7200, time.time() - 7200))
            self.assertEqual(cleanup_gas_temp_files(folder), 1)
            self.assertFalse(old.exists())
        opened = []
        path = send_to_gas_via_browser({"menu": "99.7.5.11", "data": REPORT_ROWS}, "https://example.invalid/exec",
                                       launcher=opened.append)
        try:
            self.assertEqual(opened, [path])
            page = Path(path).read_text(encoding="utf-8")
            self.assertIn("データ件数: 2 件", page)
            self.assertIn('action="https://example.invalid/exec"', page)
        finally:
            os.remove(path)
