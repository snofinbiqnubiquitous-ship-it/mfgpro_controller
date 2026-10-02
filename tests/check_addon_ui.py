"""GUI check of the add-on bars and menu. SSH is blocked and config writes are mocked."""
import ctypes
import importlib.machinery
import importlib.util
import sys
import time
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
loader = importlib.machinery.SourceFileLoader("qad_addon_ui_check", str(ROOT / "自作モダンターミナル.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


def pump(app):
    for _ in range(4):
        app.update()
        time.sleep(0.02)


def labels(menu):
    end = menu.index("end")
    return [(menu.type(i), menu.entrycget(i, "label") if menu.type(i) != "separator" else "-",
             menu.entrycget(i, "state") if menu.type(i) != "separator" else "") for i in range(end + 1)]


with patch.object(module.TerminalApp, "connect_to_server"), \
     patch("paramiko.SSHClient", side_effect=AssertionError("SSH prohibited in UI check")), \
     patch.object(module, "save_config") as save_config:
    app = module.TerminalApp()
    errors = []
    app.report_callback_exception = lambda *error: errors.append(error)
    try:
        app.config.pop("addons_visible", None)
        app.addon_host.refresh_all()
        app.geometry("1280x760+0+0")
        pump(app)
        host = app.addon_host
        print("records:", [(r.id, r.error or "ok") for r in host.records])
        print("addon menu:", labels(app.addon_menu))
        quick, data = app.addon_bars["quick"][0], app.addon_bars["data"][0]
        assert quick.winfo_ismapped() and data.winfo_ismapped()
        buttons = {b.key: b for r in host.records for b in r.buttons}
        assert "addon_data_transmission_inventory" in str(buttons["data_transmission.inventory"].widget)
        assert buttons["quick_order_booking.order_booking"].widget.cget("state") == "disabled"  # not connected
        assert buttons["data_transmission.inventory"].widget.cget("state") == "normal"
        actions = app._shortcut_actions()
        addon_actions = [label for _, (label, _) in actions.items() if "在庫レポート" in label or "OrderBooking" in label]
        print("shortcut targets:", addon_actions)
        view_index = host.ui._menu_index(app.view_menu, "📤 データ送信ボタン名の設定...")
        assert view_index is not None

        from PIL import ImageGrab
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.GetAncestor(app.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).save(ROOT / ".venv" / "addon-bars-visible.png")

        host.set_visible("data_transmission", False)
        pump(app)
        assert not data.winfo_ismapped() and quick.winfo_ismapped()
        assert buttons["data_transmission.inventory"].widget.cget("state") == "disabled"
        assert app.view_menu.entrycget(view_index, "state") == "disabled"
        assert app.config["addons_visible"] == {"data_transmission": False}
        assert save_config.called
        host.set_visible("quick_order_booking", False)
        pump(app)
        assert not quick.winfo_ismapped()
        assert not host.run_action("order_booking.run")
        ImageGrab.grab(window=hwnd).save(ROOT / ".venv" / "addon-bars-hidden.png")
        host.set_visible("data_transmission", True)
        host.set_visible("quick_order_booking", True)
        pump(app)
        assert data.winfo_ismapped() and quick.winfo_ismapped()
        assert buttons["data_transmission.inventory"].widget.cget("state") == "normal"
        host.set_connected(True)
        assert buttons["quick_order_booking.order_booking"].widget.cget("state") == "normal"
        assert not errors, errors
        print("ADDON_UI_OK; SSH_NOT_USED")
    finally:
        app.on_close()
