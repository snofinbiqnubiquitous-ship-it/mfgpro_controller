"""GUI check of add-on items: hide, add, remove, rename and busy state.

SSH is blocked, config writes are mocked and add-ons are loaded from a temporary
copy so the repository folder is not changed.
"""
import ctypes
import importlib.machinery
import importlib.util
import shutil
import sys
import tempfile
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

EXTRA = '''
ADDON = {"id": "check_item", "name": "確認用アイテム"}
def register(api):
    api.add_button("run", "確認用", lambda: None, bar="data", color="#0F766E", busy_group="gas_transmission")
'''


def pump(app):
    for _ in range(4):
        app.update()
        time.sleep(0.02)


def grab(app, name):
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    ImageGrab.grab(window=user32.GetAncestor(app.winfo_id(), 2)).save(ROOT / ".venv" / name)


with tempfile.TemporaryDirectory() as work:
    work = Path(work)
    shutil.copytree(ROOT / "addons", work / "addons", ignore=shutil.ignore_patterns("__pycache__", "_removed"))
    (work / "incoming").mkdir()
    extra = work / "incoming" / "21_check_item.py"
    extra.write_text(EXTRA, encoding="utf-8")
    with patch.object(module.TerminalApp, "connect_to_server"), \
         patch("paramiko.SSHClient", side_effect=AssertionError("SSH prohibited in UI check")), \
         patch.object(module, "save_config") as save_config, \
         patch.object(module, "PROJECT_ROOT", work):
        app = module.TerminalApp()
        errors = []
        app.report_callback_exception = lambda *error: errors.append(error)
        try:
            app.config.pop("addons_visible", None)
            app.config.pop("addon_button_names", None)
            app.addon_host.refresh_all()
            app.geometry("1280x760+0+0")
            pump(app)
            host = app.addon_host
            menu = app.addon_menu
            entries = [(menu.type(i), menu.entrycget(i, "label") if menu.type(i) != "separator" else "-") for i in range(menu.index("end") + 1)]
            print("records:", [(r.name, r.error or "ok") for r in host.records])
            print("tools > add-ons:", entries)
            buttons = {b.key: b for b in host.buttons()}
            inventory = buttons["inventory_transmission.run"].widget
            data_bar = app.addon_bars["data"][0]
            grab(app, "addon-items-all.png")

            app.addon_host.ui.set_visible("inventory_transmission", False)
            pump(app)
            assert not inventory.winfo_ismapped() and inventory.cget("state") == "disabled"
            assert buttons["complaint_transmission.run"].widget.winfo_ismapped() and data_bar.winfo_ismapped()
            for addon_id in ("complaint_transmission", "backlog_sales_transmission"):
                host.set_visible(addon_id, False)
            pump(app)
            assert not data_bar.winfo_ismapped() and app.addon_bars["quick"][0].winfo_ismapped()
            for addon_id in ("inventory_transmission", "complaint_transmission", "backlog_sales_transmission"):
                host.set_visible(addon_id, True)

            record = host.install(extra)
            pump(app)
            added = record.buttons[0].widget
            assert (work / "addons" / "21_check_item.py").is_file() and added.winfo_ismapped()
            assert any(menu.type(i) == "checkbutton" and menu.entrycget(i, "label") == "確認用アイテム" for i in range(menu.index("end") + 1))
            grab(app, "addon-items-added.png")

            host.set_labels({"inventory_transmission.run": "在庫だけ送る"})
            assert inventory.cget("text") == "在庫だけ送る"
            host.set_labels({"inventory_transmission.run": ""})
            assert inventory.cget("text") == "📦 在庫レポートGAS送信 (99.3.6.1)"

            host.lock("gas_transmission").acquire()
            host.refresh_group("gas_transmission")
            assert all(buttons[k].widget.cget("state") == "disabled" for k in buttons if k != "order_booking.run")
            assert added.cget("state") == "disabled"
            host.lock("gas_transmission").release()
            host.refresh_group("gas_transmission")

            host.remove(record)
            pump(app)
            assert not added.winfo_exists()
            assert not (work / "addons" / "21_check_item.py").exists()
            assert list((work / "addons" / "_removed").glob("21_check_item_*.py"))
            assert save_config.called and not errors, errors
            print("ADDON_ITEMS_UI_OK; SSH_NOT_USED; REPOSITORY_ADDONS_UNCHANGED")
        finally:
            app.on_close()
