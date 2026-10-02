"""Offline tests for add-on loading, add/remove, visibility, names and thread handoff."""
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

from addon_host import AddonAPI, AddonHost


class FakeUI:
    def __init__(self, config=None):
        self.config = config if config is not None else {}
        self.saved = 0
        self.layouts = {}
        self.states = {}
        self.texts = {}
        self.destroyed = []
        self.menu = []
        self.statuses = []
        self.parent = self.colors = self.font_family = None

    def save_config(self):
        self.saved += 1

    def create_button(self, button, label):
        self.texts[button.key] = label
        return f"widget:{button.key}"

    def destroy_button(self, button):
        self.destroyed.append(button.key)

    def set_button_text(self, button, text):
        self.texts[button.key] = text

    def set_button_state(self, button, state):
        self.states[button.key] = state

    def layout_bar(self, bar, ordered, shown):
        self.layouts[bar] = [b.key for b in shown]

    def build_addon_menu(self, records):
        self.menu = [(r.name, bool(r.error)) for r in records]

    def set_status(self, text, status_type, clear_delay):
        self.statuses.append((text, status_type))

    def is_connected(self):
        return True


GOOD = '''
ADDON = {"id": "%(id)s", "name": "%(name)s"}
def register(api):
    api.add_button("run", "%(name)s button", lambda: None, bar="%(bar)s", requires_connection=%(conn)s,
                   busy_group="%(group)s", legacy_label=("old_names", "%(id)s"))
    api.register_action("%(id)s.run", lambda: None)
'''


def good(addon_id, bar="data", conn=False, group=""):
    return GOOD % {"id": addon_id, "name": addon_id.title(), "bar": bar, "conn": conn, "group": group}


class AddonHostTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def load(self, files, config=None):
        for name, text in files.items():
            (self.folder / name).write_text(textwrap.dedent(text), encoding="utf-8")
        ui = FakeUI(config)
        host = AddonHost(ui)
        host.load_directory(self.folder)
        return host, ui

    def test_broken_add_ons_are_reported_and_others_still_load(self):
        host, ui = self.load({
            "a_good.py": good("alpha"),
            "b_syntax.py": "def register(api):\n    return (\n",
            "c_raises.py": 'ADDON = {"id": "gamma", "name": "G"}\ndef register(api):\n'
                           '    api.add_button("x", "X", None, bar="quick")\n'
                           '    api.register_action("gamma.x", None)\n    raise RuntimeError("boom")\n',
            "d_duplicate.py": good("alpha"),
            "e_missing.py": "x = 1\n",
            "_private.py": "raise SystemExit\n",
        })
        self.assertEqual(ui.menu, [("Alpha", False), ("b_syntax", True), ("G", True), ("d_duplicate", True), ("e_missing", True)])
        self.assertEqual(ui.layouts, {"quick": [], "data": ["alpha.run"]})
        self.assertEqual(set(host.actions), {"alpha.run"})
        self.assertIn("重複", host.records[3].error)

    def test_each_item_hides_independently_with_its_shortcut_action(self):
        config = {}
        host, ui = self.load({"a.py": good("alpha"), "b.py": good("beta")}, config)
        host.set_visible("alpha", False)
        self.assertEqual(config["addons_visible"], {"alpha": False})
        self.assertEqual(ui.layouts["data"], ["beta.run"])
        self.assertEqual(ui.states["alpha.run"], "disabled")
        self.assertFalse(host.run_action("alpha.run"))
        self.assertTrue(host.run_action("beta.run"))
        host.set_visible("beta", False)
        self.assertEqual(ui.layouts["data"], [])
        host.set_visible("alpha", True)
        self.assertEqual(ui.layouts["data"], ["alpha.run"])
        self.assertEqual(ui.states["alpha.run"], "normal")

    def test_saved_hidden_state_applies_at_start(self):
        _, ui = self.load({"a.py": good("alpha"), "b.py": good("beta")}, {"addons_visible": {"alpha": False}})
        self.assertEqual(ui.layouts["data"], ["beta.run"])

    def test_install_and_remove_without_restart(self):
        host, ui = self.load({"a.py": good("alpha")})
        source_dir = tempfile.TemporaryDirectory()
        self.addCleanup(source_dir.cleanup)
        source = Path(source_dir.name) / "b_new.py"
        source.write_text(textwrap.dedent(good("beta", bar="quick")), encoding="utf-8")
        record = host.install(source)
        self.assertTrue((self.folder / "b_new.py").is_file())
        self.assertEqual(ui.layouts, {"quick": ["beta.run"], "data": ["alpha.run"]})
        self.assertIn("beta.run", host.actions)
        with self.assertRaisesRegex(ValueError, "同じ名前"):
            host.install(source)
        clash = Path(source_dir.name) / "c_clash.py"
        clash.write_text(textwrap.dedent(good("alpha")), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "重複"):
            host.install(clash)
        self.assertFalse((self.folder / "c_clash.py").exists())

        moved = host.remove(record)
        self.assertFalse((self.folder / "b_new.py").exists())
        self.assertEqual(moved.parent, self.folder / "_removed")
        self.assertEqual(ui.destroyed, ["beta.run"])
        self.assertNotIn("beta.run", host.actions)
        self.assertEqual(ui.layouts["quick"], [])
        self.assertEqual(ui.menu, [("Alpha", False)])
        # Moved files are not loaded again at the next start.
        self.assertEqual([r.id for r in AddonHost(FakeUI()).load_directory(self.folder)], ["alpha"])

    def test_button_names_use_legacy_value_then_saved_value(self):
        config = {"old_names": {"alpha": "在庫送信"}}
        host, ui = self.load({"a.py": good("alpha")}, config)
        self.assertEqual(ui.texts["alpha.run"], "在庫送信")
        host.set_labels({"alpha.run": "在庫だけ送る"})
        self.assertEqual((ui.texts["alpha.run"], config["addon_button_names"]["alpha.run"]), ("在庫だけ送る", "在庫だけ送る"))
        host.set_labels({"alpha.run": ""})
        self.assertEqual(ui.texts["alpha.run"], "Alpha button")

    def test_busy_group_disables_all_members_and_connection_rule(self):
        host, ui = self.load({"a.py": good("alpha", group="gas"), "b.py": good("beta", group="gas"),
                              "c.py": good("gamma", conn=True)})
        self.assertEqual(ui.states["gamma.run"], "disabled")
        api = AddonAPI(host, host.records[0])
        self.assertTrue(api.begin_busy("gas"))
        self.assertFalse(api.begin_busy("gas"))
        self.assertEqual((ui.states["alpha.run"], ui.states["beta.run"]), ("disabled", "disabled"))
        api.end_busy("gas")
        self.assertEqual((ui.states["alpha.run"], ui.states["beta.run"]), ("normal", "normal"))
        host.set_connected(True)
        self.assertEqual(ui.states["gamma.run"], "normal")

    def test_background_calls_wait_for_the_ui_thread(self):
        host, ui = self.load({"a.py": good("alpha")})
        api = AddonAPI(host, host.records[0])
        result = {}
        worker = threading.Thread(target=lambda: (api.set_status("busy", "working"),
                                                  result.setdefault("connected", api.is_connected())))
        worker.start()
        while worker.is_alive():
            host.drain()
            worker.join(0.01)
        self.assertEqual(ui.statuses, [("busy", "working")])
        self.assertTrue(result["connected"])

    def test_distributed_add_ons_are_four_independent_items(self):
        ui = FakeUI({"data_transmission_names": {"inventory": "📦 在庫送信"}})
        host = AddonHost(ui)
        host.load_directory(Path(__file__).resolve().parents[1] / "addons")
        self.assertEqual([(r.name, r.error) for r in host.records],
                         [("OrderBooking出力", ""), ("在庫送信", ""), ("Complaint送信", ""), ("受注残＆売上送信", "")])
        self.assertEqual(ui.layouts["quick"], ["order_booking.run"])
        self.assertEqual(ui.layouts["data"], ["inventory_transmission.run", "complaint_transmission.run",
                                              "backlog_sales_transmission.run"])
        self.assertEqual(ui.texts["inventory_transmission.run"], "📦 在庫送信")
        self.assertIn("order_booking.run", host.actions)
