"""Local GUI smoke check. SSH, submissions, and config writes are blocked."""

import ctypes
from ctypes import wintypes
from datetime import date
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
loader = importlib.machinery.SourceFileLoader("qad_order_ui_check", str(ROOT / "自作モダンターミナル.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


def pump(app):
    for _ in range(3):
        app.update()
        time.sleep(.02)


def tap_control(app):
    widget = app.focus_get()
    assert widget is not None
    widget.event_generate("<KeyPress-Control_L>", state=0)
    widget.event_generate("<KeyRelease-Control_L>", state=4)


def main():
    with patch.object(module.TerminalApp, "connect_to_server"), \
         patch("paramiko.SSHClient", side_effect=AssertionError("SSH prohibited in UI check")), \
         patch.object(module, "save_config") as save_config:
        app = module.TerminalApp()
        callback_errors = []
        app.report_callback_exception = lambda *error: callback_errors.append(error)
        try:
            for key in ("order_customer_name_csv", "order_ship_to_csv"):
                app.config.pop(key, None)
            app.geometry("1280x760+0+0")
            pump(app)
            app.focus_force()
            app.focus_terminal()
            pump(app)
            assert app._order_bindtag in app.textbox._textbox.bindtags()
            tap_control(app)
            assert not app.order_panel_visible.get()
            tap_control(app)
            pump(app)
            assert app.order_panel_visible.get()
            panel = app.order_panel
            assert panel.winfo_ismapped()
            assert len(panel.item_entries) == 5
            assert all(len(row) == 5 for row in panel.item_entries)
            assert panel.fields["remarks"].get("1.0", "end-1c") == ""
            assert panel.fields["so_comment"].get("1.0", "end-1c") == ""
            assert panel.winfo_rootx() >= app.terminal_container.winfo_rootx() + app.terminal_container.winfo_width()

            with tempfile.TemporaryDirectory() as directory:
                csv_path = Path(directory) / "choices.csv"
                csv_path.write_text("顧客名,納品先\n確認用顧客A,確認用倉庫A\n確認用顧客B,確認用倉庫B\n", encoding="utf-8-sig")
                with patch.object(module.filedialog, "askopenfilename", return_value=str(csv_path)):
                    app.import_order_choices("customer_name")
                    app.import_order_choices("ship_to")
                assert save_config.call_count == 2
                assert panel.fields["customer_name"].cget("values") == ["確認用顧客A", "確認用顧客B"]
                assert panel.fields["ship_to"].cget("values") == ["確認用倉庫A", "確認用倉庫B"]
                panel.fields["customer_name"].set("確認用顧客A")
                panel.fields["ship_to"].set("確認用倉庫A")
                panel.fields["purchase_order"].insert(0, "PO-2026-001")

                date_field = panel.fields["required_date"]
                date_field.open_calendar()
                pump(app)
                date_field.month = date(2026, 12, 1)
                date_field._move_month(1)
                assert date_field.month == date(2027, 1, 1)
                date_field.set_date(date(2026, 9, 24))
                panel.fields["due_date"].set_date(date(2026, 10, 1))
                assert date_field.variable.get() == "2026/9/24 (木)"

                panel.submit()
                assert app.last_order_submission is None
                for index, row in enumerate(panel.item_entries):
                    for key, value in {"product_name": f"製品 {index + 1}", "width": "100.5", "length": "2000",
                                       "quantity": str(index + 1), "price": "1250.50"}.items():
                        row[key].insert(0, value)
                panel.submit()
                pump(app)
                assert len(app.last_order_submission["items"]) == 5
                assert app.last_order_submission["items"][0]["quantity"] == 1
                assert app.order_output.winfo_exists()
                app.order_output.destroy()
                app.focus_force()
                panel.fields["purchase_order"].focus_set()
                pump(app)
                # Ctrl+A edits the form rather than selecting/sending terminal text.
                app.select_all_text()
                assert panel.fields["purchase_order"]._entry.selection_present()
                focused = app.focus_get()
                app._order_control_tap.reset()
                focused.event_generate("<KeyPress-Control_L>", state=0)
                focused.event_generate("<KeyPress-a>", state=4)
                focused.event_generate("<KeyRelease-Control_L>", state=4)
                tap_control(app)
                assert app.order_panel_visible.get()
                app._order_control_tap.reset()
                tap_control(app)
                tap_control(app)
                pump(app)
                assert not app.order_panel_visible.get()
                tap_control(app)
                tap_control(app)
                pump(app)
                assert app.order_panel_visible.get()
                assert panel.fields["purchase_order"].get() == "PO-2026-001"

                for width, height in ((1020, 660), (1680, 840)):
                    app.geometry(f"{width}x{height}+0+0")
                    pump(app)
                    assert panel.send_button.winfo_rooty() + panel.send_button.winfo_height() <= app.winfo_rooty() + app.winfo_height()
                    last = panel.item_entries[-1]["price"]
                    last.focus_set()
                    pump(app)
                    canvas = panel.body._parent_canvas
                    assert last.winfo_rooty() + last.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height() + 4
                    print(f"ORDER_LAYOUT_OK {width}x{height}")

                panel.body._parent_canvas.yview_moveto(0)
                panel.fields["customer_name"].focus_set()
                pump(app)
                from PIL import ImageGrab
                user32 = ctypes.windll.user32
                user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
                user32.GetAncestor.restype = wintypes.HWND
                hwnd = user32.GetAncestor(app.winfo_id(), 2)
                ImageGrab.grab(window=hwnd).save(ROOT / ".venv" / "order-entry-preview.png")
                assert not callback_errors, callback_errors
                print("ORDER_CSV_CALENDAR_SEND_SHORTCUTS_OK; SSH_NOT_USED")
        finally:
            app.on_close()


if __name__ == "__main__":
    main()
