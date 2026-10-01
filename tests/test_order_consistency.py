"""SSH接続・GUI起動なしで送信先固定と事前表示の整合を確認する。"""

import ast
import copy
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from order_entry import OrderOutputTerminalWindow, build_order_header_fields, clean_screen_text
from terminal_core import TerminalSession


def make_session(text):
    session = TerminalSession("unused", 22, "unused", "unused", queue.Queue())
    session.feed(text.encode("cp932"))
    return session


class OrderConsistencyTests(unittest.TestCase):
    def test_screen_reader_does_not_consume_gui_updates(self):
        session = make_session("Sales Order\r\n納品先")
        dirty = set(session.screen.dirty)
        cursor = (session.screen.cursor.y, session.screen.cursor.x)
        self.assertIn("納品先", session.get_screen_text())
        self.assertEqual(set(session.screen.dirty), dirty)
        self.assertEqual((session.screen.cursor.y, session.screen.cursor.x), cursor)
        self.assertIsNotNone(session.snapshot())

    def _prepare_worker(self, error=None):
        # アプリ全体の起動処理を避け、製品コードの実メソッドをそのまま実行する。
        path = Path(__file__).resolve().parents[1] / "自作モダンターミナル.pyw"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        app_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TerminalApp")
        method = next(n for n in app_class.body if isinstance(n, ast.FunctionDef)
                      and n.name == "run_sales_order_automation")
        controller = MagicMock()
        controller.execute_full_order.return_value = "SO123456"
        controller.execute_full_order.side_effect = error
        factory = MagicMock(return_value=controller)
        workers, callbacks = [], []
        namespace = dict(
            copy=copy, clean_screen_text=clean_screen_text,
            SalesOrderAutomationController=factory,
            log_info=MagicMock(), log_warning=MagicMock(), log_error=MagicMock(),
            messagebox=MagicMock(),
            threading=SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(
                start=lambda: workers.append(kwargs["target"]))),
        )
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
        session = make_session("mfmenu Main Menu")
        app = SimpleNamespace(
            active_tab=SimpleNamespace(session=session), session=session, is_connected=True,
            _record_completed_order=MagicMock(),
            last_order_submission=None, set_status=MagicMock(), _show_input_error=MagicMock(),
            after=lambda delay, callback: callbacks.append(callback),
            _get_current_screen_text=MagicMock(side_effect=AssertionError("GUI画面を参照した")),
        )
        payload = {"items": [{"product_name": "TEST", "quantity": 1}]}
        namespace[method.name](app, payload)
        return app, session, payload, workers, callbacks, factory

    def test_tab_switch_and_input_edit_do_not_change_running_order(self):
        app, session, payload, workers, callbacks, factory = self._prepare_worker()
        app.active_tab = SimpleNamespace(session=make_session("Sales Order Line"))
        app.session = app.active_tab.session
        payload["items"][0]["quantity"] = 99
        workers[0]()
        args = factory.call_args.kwargs
        self.assertIs(args["session"], session)
        self.assertIn("mfmenu", args["get_screen_text"]())
        self.assertEqual(args["payload"]["items"][0]["quantity"], 1)
        app._record_completed_order.assert_called_once_with(args["payload"], "SO123456")
        factory.return_value.execute_full_order.assert_called_once()
        factory.return_value.execute_step6.assert_not_called()
        app._get_current_screen_text.assert_not_called()

    def test_delayed_error_dialog_preserves_exception_message(self):
        for error in (TimeoutError("画面待機失敗"), RuntimeError("送信失敗")):
            with self.subTest(error=type(error).__name__):
                app, _, _, workers, callbacks, _ = self._prepare_worker(error)
                workers[0]()
                for callback in callbacks:
                    callback()
                self.assertIn(str(error), app._show_input_error.call_args.args[0])
                self.assertFalse(app._is_running_order_automation)
                app._record_completed_order.assert_not_called()

    def test_preview_describes_current_transport_without_claiming_verification(self):
        chunks = []
        text = MagicMock()
        text.insert.side_effect = lambda index, value, *tags: chunks.append(value)
        window = SimpleNamespace(submission_count=0, count_label=MagicMock(),
                                 textbox=SimpleNamespace(_textbox=text))
        payload = dict(required_date="2026-10-09", due_date="2026-10-07",
                       purchase_order="PO-TEST", remarks="備考", items=[])
        OrderOutputTerminalWindow.append_submission(window, payload)
        rendered = "".join(chunks)
        self.assertIn("注文コミット＆与信/延滞チェック実行: <F1>", rendered)
        self.assertIn("合計画面に残っている場合のみ <F4>", rendered)
        self.assertIn("登録結果の検証ではありません", rendered)
        self.assertNotIn("サーバーへ実送信は行わず", rendered)
        fields = build_order_header_fields(payload)
        self.assertEqual(fields[1:], ["10/09/26", "", "10/07/26", "", "", "PO-TEST", "備考"])
        self.assertIn("\n".join(fields), rendered)


if __name__ == "__main__":
    unittest.main()
