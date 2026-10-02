"""Add-on loader for the quick menu and data transmission bars.

Each file in ``addons/`` defines ``ADDON = {"id": ..., "name": ...}`` and
``register(api)``. Add-ons are loaded once at start-up. A failing add-on is
reported and skipped so the terminal still starts. Visibility is stored per
add-on in ``terminal_config.json`` under ``addons_visible``.
"""
import importlib.util
import queue
import re
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

BAR_QUICK = "quick"
BAR_DATA = "data"
BARS = (BAR_QUICK, BAR_DATA)
VISIBILITY_KEY = "addons_visible"
ADDON_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


@dataclass
class AddonButton:
    addon_id: str
    button_id: str
    bar: str
    label: str
    command: object
    color: str
    hover_color: str
    requires_connection: bool
    on_right_click: object = None
    enabled: bool = True
    widget: object = None

    @property
    def key(self):
        return f"{self.addon_id}.{self.button_id}"


@dataclass
class AddonMenuItem:
    addon_id: str
    label: str
    command: object
    handle: object = None


@dataclass
class AddonRecord:
    id: str
    name: str
    path: Path
    error: str = ""
    buttons: list = field(default_factory=list)
    menu_items: list = field(default_factory=list)
    actions: dict = field(default_factory=dict)


class ButtonHandle:
    """Handle returned to an add-on; changes are applied on the UI thread."""

    def __init__(self, host, button):
        self._host = host
        self._button = button

    def set_text(self, text):
        def apply():
            self._button.label = text
            self._host.ui.set_button_text(self._button, text)
        self._host.call_in_ui(apply)

    def set_enabled(self, enabled):
        def apply():
            self._button.enabled = bool(enabled)
            self._host.refresh_button(self._button)
        self._host.call_in_ui(apply)


class AddonAPI:
    """Functions an add-on may use. Background threads may call every method."""

    def __init__(self, host, record):
        self._host = host
        self._record = record
        self.id = record.id
        self.name = record.name

    @property
    def parent(self):
        return self._host.ui.parent

    @property
    def colors(self):
        return self._host.ui.colors

    @property
    def font_family(self):
        return self._host.ui.font_family

    # --- registration (start-up only) ---
    def add_button(self, button_id, label, command, *, bar, color="#2563EB", hover_color=None,
                   requires_connection=False, on_right_click=None):
        if bar not in BARS:
            raise ValueError(f"未対応のバー: {bar}")
        if not ADDON_ID_RE.match(button_id):
            raise ValueError(f"ボタンIDは英小文字・数字・_で指定してください: {button_id}")
        if any(b.button_id == button_id for b in self._record.buttons):
            raise ValueError(f"ボタンIDが重複しています: {button_id}")
        button = AddonButton(self.id, button_id, bar, label, command, color, hover_color or color,
                             bool(requires_connection), on_right_click)
        self._record.buttons.append(button)
        return ButtonHandle(self._host, button)

    def add_view_menu_command(self, label, command):
        self._record.menu_items.append(AddonMenuItem(self.id, label, command))

    def register_action(self, action_id, command):
        if action_id in self._host.actions:
            raise ValueError(f"アクションIDが重複しています: {action_id}")
        self._record.actions[action_id] = command
        self._host.actions[action_id] = (self.id, command)

    # --- UI and logging ---
    def call_in_ui(self, function):
        self._host.call_in_ui(function)

    def ui_query(self, function, timeout=3.0):
        return self._host.ui_query(function, timeout)

    def set_status(self, text, status_type="info", clear_delay=None):
        self._host.call_in_ui(lambda: self._host.ui.set_status(text, status_type, clear_delay))

    def show_error(self, title, message, parent=None):
        self._host.call_in_ui(lambda: self._host.ui.show_message("error", title, message, parent))

    def show_warning(self, title, message, parent=None):
        self._host.call_in_ui(lambda: self._host.ui.show_message("warning", title, message, parent))

    def log_info(self, message):
        self._host.log("info", f"[{self.id}] {message}")

    def log_warning(self, message):
        self._host.log("warning", f"[{self.id}] {message}")

    def log_error(self, message, exc_info=False):
        self._host.log("error", f"[{self.id}] {message}", exc_info)

    def run_in_background(self, function, name):
        def runner():
            try:
                function()
            except Exception as exc:
                self.log_error(f"バックグラウンド処理エラー: {exc}", exc_info=True)
        thread = threading.Thread(target=runner, daemon=True, name=f"addon-{self.id}-{name}")
        thread.start()
        return thread

    # --- settings and exclusive work ---
    def config_get(self, key, default=None):
        return self._host.ui.config.get(key, default)

    def config_set(self, key, value):
        self._host.ui.config[key] = value
        self._host.ui.save_config()

    def try_acquire(self, name):
        return self._host.lock(name).acquire(blocking=False)

    def release(self, name):
        lock = self._host.lock(name)
        if lock.locked():
            lock.release()

    def is_busy(self, name):
        return self._host.lock(name).locked()

    # --- QAD and the terminal (values are read on the UI thread) ---
    def qad_credentials(self):
        return self._host.ui_query(self._host.ui.qad_credentials)

    def is_connected(self):
        return bool(self._host.ui_query(self._host.ui.is_connected))

    def active_tab(self):
        return self._host.ui_query(self._host.ui.active_tab)

    def is_active_tab(self, tab):
        return self._host.ui_query(lambda: self._host.ui.active_tab() is tab and self._host.ui.is_connected())

    def is_main_menu(self):
        return bool(self._host.ui_query(self._host.ui.is_main_menu))

    def screen_text(self):
        return self._host.ui_query(self._host.ui.screen_text) or ""

    def is_cursor_at_output_field(self):
        return bool(self._host.ui_query(self._host.ui.is_cursor_at_output_field))

    def is_report_busy(self):
        return bool(self._host.ui_query(self._host.ui.is_report_busy))

    def send_to_tab(self, tab, data):
        """Send only while the captured tab is still active and connected."""
        def send():
            if self._host.ui.active_tab() is not tab or not self._host.ui.is_connected():
                return False
            tab.session.send(data)
            return True
        if not self._host.ui_query(send):
            raise RuntimeError("操作中のタブが切り替わったか切断されたため中止しました。")

    def start_32printer(self, tab):
        def start():
            if self._host.ui.active_tab() is not tab or not self._host.ui.is_connected():
                return False
            self._host.ui.start_32printer()
            return True
        if not self._host.ui_query(start):
            raise RuntimeError("操作中のタブが切り替わったか切断されたため中止しました。")


class AddonHost:
    """Loads add-ons and keeps their buttons in sync with visibility and connection."""

    def __init__(self, ui, logger=None):
        self.ui = ui
        self.logger = logger
        self.records = []
        self.actions = {}
        self._locks = {}
        self._locks_guard = threading.Lock()
        self._queue = queue.SimpleQueue()
        self._main_thread = threading.current_thread()
        self.connected = False

    # --- threading ---
    def lock(self, name):
        with self._locks_guard:
            return self._locks.setdefault(name, threading.Lock())

    def call_in_ui(self, function):
        if threading.current_thread() is self._main_thread:
            function()
        else:
            self._queue.put(function)

    def ui_query(self, function, timeout=3.0):
        if threading.current_thread() is self._main_thread:
            return function()
        done = threading.Event()
        result = {}

        def run():
            try:
                result["value"] = function()
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()
        self._queue.put(run)
        if not done.wait(timeout):
            raise TimeoutError("画面状態の取得がタイムアウトしました。")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def drain(self, limit=200):
        """Run queued UI work. Called periodically from the Tk main loop."""
        for _ in range(limit):
            try:
                function = self._queue.get_nowait()
            except queue.Empty:
                return
            try:
                function()
            except Exception as exc:
                self.log("error", f"アドオンのUI処理エラー: {exc}", True)

    def log(self, level, message, exc_info=False):
        if self.logger is not None:
            getattr(self.logger, level)(message, exc_info=exc_info)

    # --- loading ---
    def load_directory(self, directory):
        directory = Path(directory)
        if not directory.is_dir():
            self.log("info", f"アドオンフォルダがありません: {directory}")
            self._finish_loading()
            return self.records
        for path in sorted(directory.glob("*.py")):
            if not path.name.startswith("_"):
                self._load_file(path)
        self._finish_loading()
        return self.records

    def _load_file(self, path):
        record = AddonRecord(id=f"file:{path.stem}", name=path.stem, path=path)
        try:
            spec = importlib.util.spec_from_file_location(f"qad_addon_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            meta = getattr(module, "ADDON", None)
            if not isinstance(meta, dict) or not callable(getattr(module, "register", None)):
                raise ValueError("ADDON = {'id': ..., 'name': ...} と register(api) が必要です。")
            addon_id = str(meta.get("id", ""))
            if not ADDON_ID_RE.match(addon_id):
                raise ValueError(f"アドオンIDは英小文字・数字・_で指定してください: {addon_id!r}")
            if any(r.id == addon_id for r in self.records):
                raise ValueError(f"アドオンIDが重複しています: {addon_id}")
            record.id = addon_id
            record.name = str(meta.get("name") or addon_id)
            module.register(AddonAPI(self, record))
        except Exception as exc:
            # Undo partial registration so a broken add-on leaves nothing behind.
            for action_id in record.actions:
                self.actions.pop(action_id, None)
            record.buttons.clear()
            record.menu_items.clear()
            record.actions.clear()
            record.error = f"{type(exc).__name__}: {exc}"
            self.log("error", f"アドオン読み込みエラー ({path.name}): {record.error}\n{traceback.format_exc()}")
        else:
            self.log("info", f"アドオンを読み込みました: {record.name} ({path.name})")
        self.records.append(record)

    def _finish_loading(self):
        for record in self.records:
            for button in record.buttons:
                button.widget = self.ui.create_button(button)
            for item in record.menu_items:
                item.handle = self.ui.add_menu_item(item)
        self.ui.build_addon_menu(self.records)
        self.refresh_all()

    # --- visibility and state ---
    def is_visible(self, addon_id):
        visible = self.ui.config.get(VISIBILITY_KEY, {})
        return bool(visible.get(addon_id, True)) if isinstance(visible, dict) else True

    def set_visible(self, addon_id, visible):
        settings = self.ui.config.get(VISIBILITY_KEY)
        if not isinstance(settings, dict):
            settings = {}
        settings[addon_id] = bool(visible)
        self.ui.config[VISIBILITY_KEY] = settings
        self.ui.save_config()
        self.refresh_all()

    def set_connected(self, connected):
        self.connected = bool(connected)
        self.refresh_all()

    def record(self, addon_id):
        return next((r for r in self.records if r.id == addon_id), None)

    def button_state(self, button):
        if not self.is_visible(button.addon_id) or not button.enabled:
            return "disabled"
        if button.requires_connection and not self.connected:
            return "disabled"
        return "normal"

    def refresh_button(self, button):
        self.ui.set_button_state(button, self.button_state(button))

    def refresh_all(self):
        loaded = [r for r in self.records if not r.error]
        for bar in BARS:
            ordered = [b for r in loaded for b in r.buttons if b.bar == bar]
            shown = [b for b in ordered if self.is_visible(b.addon_id)]
            self.ui.layout_bar(bar, ordered, shown)
            for button in ordered:
                self.refresh_button(button)
        for record in loaded:
            for item in record.menu_items:
                self.ui.set_menu_item_state(item, "normal" if self.is_visible(record.id) else "disabled")

    def run_action(self, action_id):
        """Run a registered action. Hidden add-ons do not run (also for shortcuts)."""
        entry = self.actions.get(action_id)
        if entry is None:
            return False
        addon_id, command = entry
        if not self.is_visible(addon_id):
            return False
        command()
        return True


class TkAddonUI:
    """Connects AddonHost to the terminal window. All methods run on the Tk thread."""

    def __init__(self, app, save_config):
        self.app = app
        self._save_config = save_config
        self._menu_vars = {}

    parent = property(lambda self: self.app)
    colors = property(lambda self: self.app.ui_colors)
    font_family = property(lambda self: self.app.ui_font_family)
    config = property(lambda self: self.app.config)

    def save_config(self):
        self._save_config(self.app.config)

    def set_status(self, text, status_type, clear_delay):
        self.app.set_status(text, status_type, clear_delay=clear_delay)

    def show_message(self, kind, title, message, parent):
        from tkinter import messagebox
        target = parent if parent is not None and parent.winfo_exists() else self.app
        show = messagebox.showerror if kind == "error" else messagebox.showwarning
        show(title, message, parent=target)

    def qad_credentials(self):
        return self.app._get_qad_credentials()

    def is_connected(self):
        return bool(self.app.is_connected and self.app.session)

    def active_tab(self):
        return self.app.active_tab

    def is_main_menu(self):
        return self.app.is_main_menu()

    def screen_text(self):
        return self.app._get_current_screen_text()

    def is_cursor_at_output_field(self):
        return self.app._is_cursor_at_output_field()

    def is_report_busy(self):
        return bool(getattr(self.app, "_is_capturing_winprint", False) or getattr(self.app, "_is_waiting_query", False))

    def start_32printer(self):
        self.app.input_32printer()

    # --- widgets ---
    def create_button(self, button):
        import tkinter as tk
        import customtkinter as ctk
        _, frame = self.app.addon_bars[button.bar]
        # A named holder keeps the widget path stable for keyboard shortcut assignments.
        holder = tk.Frame(frame, name=f"addon_{button.addon_id}_{button.button_id}",
                          bg=self.app.ui_colors["panel"], bd=0, highlightthickness=0)
        widget = ctk.CTkButton(
            holder, text=button.label, height=28, fg_color=button.color, hover_color=button.hover_color,
            text_color="#FFFFFF", corner_radius=6, command=button.command,
            font=ctk.CTkFont(family=self.app.ui_font_family, size=12, weight="bold"),
        )
        widget.pack()
        if button.on_right_click is not None:
            widget.bind("<Button-3>", button.on_right_click)
        widget.holder = holder
        return widget

    def set_button_text(self, button, text):
        if button.widget is not None:
            button.widget.configure(text=text)

    def set_button_state(self, button, state):
        if button.widget is not None:
            button.widget.configure(state=state)

    def layout_bar(self, bar, ordered, shown):
        container, _ = self.app.addon_bars[bar]
        for button in ordered:
            button.widget.holder.pack_forget()
        for button in shown:
            button.widget.holder.pack(side="left", padx=4, pady=2)
        if shown:
            container.grid()
        else:
            container.grid_remove()

    @staticmethod
    def _menu_index(menu, label):
        end = menu.index("end")
        for index in range(0 if end is None else end + 1):
            try:
                if menu.entrycget(index, "label") == label:
                    return index
            except Exception:
                continue
        return None

    def add_menu_item(self, item):
        menu = self.app.view_menu
        self.app._addon_view_menu_index += 1
        menu.insert_command(self.app._addon_view_menu_index, label=item.label, command=item.command)
        return item.label

    def set_menu_item_state(self, item, state):
        index = self._menu_index(self.app.view_menu, item.handle)
        if index is not None:
            self.app.view_menu.entryconfigure(index, state=state)

    def build_addon_menu(self, records):
        import tkinter as tk
        menu = self.app.addon_menu
        menu.delete(0, "end")
        self._menu_vars.clear()
        if not records:
            menu.add_command(label="アドオンがありません", state="disabled")
            return
        for record in records:
            if record.error:
                menu.add_command(label=f"{record.name}（読み込みエラー）", state="disabled")
                continue
            variable = tk.BooleanVar(self.app, value=self.app.addon_host.is_visible(record.id))
            self._menu_vars[record.id] = variable
            menu.add_checkbutton(label=record.name, variable=variable,
                                 command=lambda r=record.id, v=variable: self.app.addon_host.set_visible(r, v.get()))
