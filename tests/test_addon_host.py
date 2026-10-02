"""Offline tests for add-on loading, visibility and thread handoff."""
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

from addon_host import AddonHost


class FakeUI:
    def __init__(self, config=None):
        self.config = config if config is not None else {}
        self.saved = 0
        self.layouts = {}
        self.states = {}
        self.menu_states = {}
        self.menu = []
        self.statuses = []
        self.parent = self.colors = self.font_family = None

    def save_config(self):
        self.saved += 1

    def create_button(self, button):
        return f"widget:{button.key}"

    def set_button_text(self, button, text):
        pass

    def set_button_state(self, button, state):
        self.states[button.key] = state

    def layout_bar(self, bar, ordered, shown):
        self.layouts[bar] = [b.key for b in shown]

    def add_menu_item(self, item):
        return item.label

    def set_menu_item_state(self, item, state):
        self.menu_states[item.label] = state

    def build_addon_menu(self, records):
        self.menu = [(r.name, bool(r.error)) for r in records]

    def set_status(self, text, status_type, clear_delay):
        self.statuses.append((text, status_type))

    def is_connected(self):
        return True


GOOD = '''
ADDON = {"id": "%(id)s", "name": "%(name)s"}
calls = []
def register(api):
    api.add_button("run", "Run", lambda: calls.append("run"), bar="%(bar)s", requires_connection=%(conn)s)
    api.add_view_menu_command("%(name)s settings", lambda: None)
    api.register_action("%(id)s.run", lambda: calls.append("action"))
'''


def write(folder, name, text):
    (Path(folder) / name).write_text(textwrap.dedent(text), encoding="utf-8")


class AddonHostTests(unittest.TestCase):
    def load(self, files, config=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in files.items():
            write(folder.name, name, text)
        ui = FakeUI(config)
        host = AddonHost(ui)
        host.load_directory(folder.name)
        return host, ui

    def good(self, addon_id, bar="data", conn=False):
        return GOOD % {"id": addon_id, "name": addon_id.title(), "bar": bar, "conn": conn}

    def test_broken_add_ons_are_reported_and_others_still_load(self):
        host, ui = self.load({
            "a_good.py": self.good("alpha"),
            "b_syntax.py": "def register(api):\n    return (\n",
            "c_raises.py": 'ADDON = {"id": "gamma", "name": "G"}\ndef register(api):\n'
                           '    api.add_button("x", "X", None, bar="quick")\n'
                           '    api.register_action("gamma.x", None)\n    raise RuntimeError("boom")\n',
            "d_duplicate.py": self.good("alpha"),
            "e_missing.py": "x = 1\n",
            "_private.py": "raise SystemExit\n",
        })
        self.assertEqual([(r.name, bool(r.error)) for r in host.records],
                         [("Alpha", False), ("b_syntax", True), ("G", True), ("d_duplicate", True), ("e_missing", True)])
        self.assertEqual(ui.layouts, {"quick": [], "data": ["alpha.run"]})
        self.assertNotIn("gamma.x", host.actions)
        self.assertIn("重複", host.records[3].error)

    def test_visibility_hides_buttons_menu_and_actions_and_is_saved(self):
        config = {}
        host, ui = self.load({"a.py": self.good("alpha", "quick")}, config)
        module_calls = []
        host.actions["alpha.run"] = ("alpha", lambda: module_calls.append(1))
        host.set_visible("alpha", False)
        self.assertEqual(config["addons_visible"], {"alpha": False})
        self.assertEqual(ui.saved, 1)
        self.assertEqual(ui.layouts["quick"], [])
        self.assertEqual(ui.states["alpha.run"], "disabled")
        self.assertEqual(ui.menu_states["Alpha settings"], "disabled")
        self.assertFalse(host.run_action("alpha.run"))
        host.set_visible("alpha", True)
        self.assertEqual(ui.layouts["quick"], ["alpha.run"])
        self.assertEqual(ui.states["alpha.run"], "normal")
        self.assertTrue(host.run_action("alpha.run"))
        self.assertEqual(module_calls, [1])

    def test_saved_hidden_state_applies_at_start_and_new_add_ons_are_visible(self):
        host, ui = self.load({"a.py": self.good("alpha"), "b.py": self.good("beta")},
                             {"addons_visible": {"alpha": False, "removed": False}})
        self.assertEqual(ui.layouts["data"], ["beta.run"])

    def test_connection_requirement(self):
        host, ui = self.load({"a.py": self.good("alpha", conn=True), "b.py": self.good("beta")})
        self.assertEqual(ui.states, {"alpha.run": "disabled", "beta.run": "normal"})
        host.set_connected(True)
        self.assertEqual(ui.states["alpha.run"], "normal")

    def test_background_calls_wait_for_the_ui_thread(self):
        host, ui = self.load({"a.py": self.good("alpha")})
        api_record = host.records[0]
        from addon_host import AddonAPI
        api = AddonAPI(host, api_record)
        result = {}
        worker = threading.Thread(target=lambda: (api.set_status("busy", "working"),
                                                  result.setdefault("connected", api.is_connected())))
        worker.start()
        while worker.is_alive():
            host.drain()
            worker.join(0.01)
        self.assertEqual(ui.statuses, [("busy", "working")])
        self.assertTrue(result["connected"])

    def test_distributed_add_ons_register(self):
        ui = FakeUI()
        host = AddonHost(ui)
        host.load_directory(Path(__file__).resolve().parents[1] / "addons")
        self.assertEqual([(r.id, r.error) for r in host.records],
                         [("data_transmission", ""), ("quick_order_booking", "")])
        self.assertEqual(ui.layouts["quick"], ["quick_order_booking.order_booking"])
        self.assertEqual(ui.layouts["data"], ["data_transmission.inventory", "data_transmission.complaint",
                                              "data_transmission.parallel"])
        self.assertIn("order_booking.run", host.actions)
