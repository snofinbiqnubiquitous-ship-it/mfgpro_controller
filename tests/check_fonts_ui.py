"""GUI check of fonts: QAD screen keeps the monospaced font, the rest uses Yu Gothic.
SSH is blocked; a recorded 99.7.1.1 screen is fed into a local virtual terminal."""
import ctypes
import importlib.machinery
import importlib.util
import queue
import sys
import time
import tkinter.font as tkfont
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
loader = importlib.machinery.SourceFileLoader("qad_font_check", str(ROOT / "自作モダンターミナル.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
from terminal_core import TerminalSession
from order_entry import get_default_demo_payload

SCREEN = "\n".join([
    "xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             10/02/26",
    "┌──────────────────────────────────────────────────────────────────────────────┐",
    "│ Order: SO199727  Sold-To: 20000600  Bill To: 20000600  Ship-To: 20000601     │",
    "└──────────────────────────────────────────────────────────────────────────────┘",
    "┌────────────── Sold-To ───────────────┐┌────────────── Ship-To ───────────────┐",
    "│ TOPPANｲﾝﾌｫﾒﾃﾞｨｱ株式会社              ││ TOPPANｲﾝﾌｫﾒﾃﾞｨｱ㈱福島工場            │",
    "│ 東京都港区芝浦3-19-26                ││ 福島県福島市岡島字宮田30-2           │",
    "│ 港区                      108-0023   ││ 福島市                    960-8201   │",
    "└──────────────────────────────────────┘└──────────────────────────────────────┘",
    "┌──────────────────────────────────────────────────────────────────────────────┐",
    "│    Order Date: 10/02/26 Line Pricing: Yes      Confirmed: Yes                │",
    "│Purchase Order: test                                        Reprice: No       │",
    "└──────────────────────────────────────────────────────────────────────────────┘",
])


def pump(app, rounds=6):
    for _ in range(rounds):
        app.update()
        time.sleep(0.03)


def grab(widget, name):
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    ImageGrab.grab(window=user32.GetAncestor(widget.winfo_id(), 2)).save(ROOT / ".venv" / name)


with patch.object(module.TerminalApp, "connect_to_server"), \
     patch("paramiko.SSHClient", side_effect=AssertionError("SSH prohibited in font check")), \
     patch.object(module, "save_config"):
    app = module.TerminalApp()
    errors = []
    app.report_callback_exception = lambda *error: errors.append(error)
    try:
        app.geometry("1300x780+0+0")
        tab = app.active_tab
        session = TerminalSession("unused", 22, "unused", "unused", queue.Queue())
        session.feed(("\x1b[2J\x1b[H" + SCREEN.replace("\n", "\r\n")).encode("cp932"))
        tab.session = session
        app._update_tab_screen(tab, force=True)
        pump(app)
        terminal_family = app.textbox._textbox.cget("font")
        actual = tkfont.Font(root=app, font=terminal_family).actual("family")
        menu_family = tkfont.nametofont("TkMenuFont", root=app).actual("family")
        yu = tkfont.Font(root=app, family="Yu Gothic").actual("family")
        print("terminal font:", app.terminal_font_family, "->", actual)
        print("menu font is Yu Gothic:", menu_family == yu, "| ui font:", app.ui_font_family)
        assert app.terminal_font_family == "Consolas" and actual == "Consolas"
        assert menu_family == yu
        tb = app.textbox._textbox
        rights = {row: tb.bbox(f"{row}.end-1c")[0] for row in range(2, 14) if tb.bbox(f"{row}.end-1c")}
        print("right border x by row:", rights)
        assert max(rights.values()) - min(rights.values()) <= 2, rights
        app.order_panel_visible.set(True)
        app._sync_order_panel()
        pump(app, 10)
        grab(app, "font-terminal-sidebar.png")
        app.toggle_output_terminal()
        app.output_terminal_window.append_submission(get_default_demo_payload())
        app.output_terminal_window.geometry("880x620+60+60")
        pump(app, 10)
        f3 = app.output_terminal_window.textbox._textbox
        assert tkfont.Font(root=app, font=f3.tag_cget("term_label", "font")).actual("family") == yu
        f3.see("1.0")
        pump(app, 6)
        lines = f3.get("1.0", "end").splitlines()
        value_x = set()
        for row, line in enumerate(lines, 1):
            if "\t: " in line:
                box = f3.bbox(f"{row}.{line.index(chr(9)) + 1}")
                if box:
                    value_x.add(box[0])
        print("F3 value column x:", sorted(value_x))
        assert len(value_x) == 1, value_x
        grab(app.output_terminal_window, "font-f3.png")
        assert not errors, errors
        print("FONT_CHECK_OK; SSH_NOT_USED")
    finally:
        app.on_close()
