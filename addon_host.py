"""Add-on loader for the items on the quick menu and data transmission bars.

Each file in ``addons/`` is one item (for example "在庫送信"). It defines
``ADDON = {"id": ..., "name": ...}`` and ``register(api)``. Items can be added,
removed (moved to ``addons/_removed``) and hidden from Tools > Add-ons without
changing the terminal. A failing add-on is reported and skipped.
"""
import importlib.util
import queue
import re
import shutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

BAR_QUICK = "quick"
BAR_DATA = "data"
BARS = (BAR_QUICK, BAR_DATA)
VISIBILITY_KEY = "addons_visible"
NAMES_KEY = "addon_button_names"
REMOVED_DIR = "_removed"
ADDON_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")


@dataclass
class AddonButton:
    addon_id: str
    button_id: str
    bar: str
    default_label: str
    command: object
    color: str
    hover_color: str
    requires_connection: bool
    busy_group: str = ""
    legacy_label: tuple = ()
    enabled: bool = True
    widget: object = None

    @property
    def key(self):
        return f"{self.addon_id}.{self.button_id}"


@dataclass
class AddonRecord:
    id: str
    name: str
    path: Path
    error: str = ""
    buttons: list = field(default_factory=list)
    actions: dict = field(default_factory=dict)


class ButtonHandle:
    """Handle returned to an add-on; changes are applied on the UI thread."""

    def __init__(self, host, button):
        self._host = host
        self._button = button

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

    parent = property(lambda self: self._host.ui.parent)
    colors = property(lambda self: self._host.ui.colors)
    font_family = property(lambda self: self._host.ui.font_family)

    # --- registration (inside register only) ---
    def add_button(self, button_id, label, command, *, bar, color="#2563EB", hover_color=None,
                   requires_connection=False, busy_group="", legacy_label=()):
        """busy_group: buttons sharing a group are disabled while one of them runs.
        legacy_label: (config key, item key) of a name saved by an older version."""
        if bar not in BARS:
            raise ValueError(f"未対応のバー: {bar}")
        if not ADDON_ID_RE.match(button_id):
            raise ValueError(f"ボタンIDは英小文字・数字・_で指定してください: {button_id}")
        if any(b.button_id == button_id for b in self._record.buttons):
            raise ValueError(f"ボタンIDが重複しています: {button_id}")
        button = AddonButton(self.id, button_id, bar, label, command, color, hover_color or color,
                             bool(requires_connection), busy_group, tuple(legacy_label))
        self._record.buttons.append(button)
        return ButtonHandle(self._host, button)

    def register_action(self, action_id, command):
        if action_id in self._host.actions or action_id in self._record.actions:
            raise ValueError(f"アクションIDが重複しています: {action_id}")
        self._record.actions[action_id] = command

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
        self._host.call_in_ui(lambda: (self._host.ui.config.__setitem__(key, value), self._host.ui.save_config()))

    def begin_busy(self, group):
        """Start exclusive work. Returns False when the group is already running."""
        if not self._host.lock(group).acquire(blocking=False):
            return False
        self._host.call_in_ui(lambda: self._host.refresh_group(group))
        return True

    def end_busy(self, group):
        lock = self._host.lock(group)
        if lock.locked():
            lock.release()
        self._host.call_in_ui(lambda: self._host.refresh_group(group))

    def is_busy(self, group):
        return self._host.lock(group).locked()

    # --- QAD and the terminal (values are read on the UI thread) ---
    def qad_credentials(self):
        return self._host.ui_query(self._host.ui.qad_credentials)

    def is_connected(self):
        return bool(self._host.ui_query(self._host.ui.is_connected))

    def active_tab(self):
        return self._host.ui_query(self._host.ui.active_tab)

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
    """Loads add-ons and keeps their buttons in sync with visibility, names and state."""

    def __init__(self, ui, logger=None):
        self.ui = ui
        self.logger = logger
        self.directory = None
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
        self.directory = Path(directory)
        if self.directory.is_dir():
            for path in sorted(self.directory.glob("*.py")):
                if not path.name.startswith("_"):
                    self.records.append(self._load_record(path))
        else:
            self.log("info", f"アドオンフォルダがありません: {self.directory}")
        for record in self.records:
            self._attach(record)
        self.ui.build_addon_menu(self.records)
        self.refresh_all()
        return self.records

    def _load_record(self, path, ignore_id=None):
        record = AddonRecord(id=f"file:{path.stem}", name=path.stem, path=path)
        try:
            spec = importlib.util.spec_from_file_location(f"qad_addon_{path.stem}_{time.monotonic_ns()}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            meta = getattr(module, "ADDON", None)
            if not isinstance(meta, dict) or not callable(getattr(module, "register", None)):
                raise ValueError("ADDON = {'id': ..., 'name': ...} と register(api) が必要です。")
            addon_id = str(meta.get("id", ""))
            if not ADDON_ID_RE.match(addon_id):
                raise ValueError(f"アドオンIDは英小文字・数字・_で指定してください: {addon_id!r}")
            if any(r.id == addon_id for r in self.records if r.id != ignore_id):
                raise ValueError(f"アドオンIDが重複しています: {addon_id}")
            record.id = addon_id
            record.name = str(meta.get("name") or addon_id)
            module.register(AddonAPI(self, record))
            clash = [a for a in record.actions if a in self.actions]
            if clash:
                raise ValueError(f"アクションIDが重複しています: {', '.join(clash)}")
        except Exception as exc:
            # A broken add-on leaves nothing behind.
            record.buttons.clear()
            record.actions.clear()
            record.error = f"{type(exc).__name__}: {exc}"
            self.log("error", f"アドオン読み込みエラー ({path.name}): {record.error}\n{traceback.format_exc()}")
        else:
            self.log("info", f"アドオンを読み込みました: {record.name} ({path.name})")
        return record

    def _attach(self, record):
        for action_id, command in record.actions.items():
            self.actions[action_id] = (record.id, command)
        for button in record.buttons:
            button.widget = self.ui.create_button(button, self.label(button))

    # --- add and remove ---
    def install(self, source):
        """Copy an add-on file into the folder and load it at once."""
        source = Path(source)
        if self.directory is None:
            raise RuntimeError("アドオンフォルダが設定されていません。")
        if source.suffix.lower() != ".py" or source.name.startswith("_"):
            raise ValueError("「_」で始まらない .py ファイルを選んでください。")
        target = self.directory / source.name
        if target.exists() and target.resolve() != source.resolve():
            raise ValueError(f"同じ名前のファイルがあります: {source.name}")
        record = self._load_record(source)
        if record.error:
            raise ValueError(record.error)
        self.directory.mkdir(parents=True, exist_ok=True)
        if target.resolve() != source.resolve():
            shutil.copy2(source, target)
        record.path = target
        self.records.append(record)
        self._attach(record)
        self.ui.build_addon_menu(self.records)
        self.refresh_all()
        return record

    def remove(self, record):
        """Unload an add-on and move its file to addons/_removed (restorable)."""
        for button in record.buttons:
            self.ui.destroy_button(button)
            button.widget = None
        for action_id in record.actions:
            self.actions.pop(action_id, None)
        if record in self.records:
            self.records.remove(record)
        moved = None
        if record.path.exists():
            folder = record.path.parent / REMOVED_DIR
            folder.mkdir(exist_ok=True)
            moved = folder / f"{record.path.stem}_{time.strftime('%Y%m%d%H%M%S')}{record.path.suffix}"
            shutil.move(str(record.path), str(moved))
        self.ui.build_addon_menu(self.records)
        self.refresh_all()
        return moved

    # --- names ---
    def label(self, button):
        names = self.ui.config.get(NAMES_KEY)
        if isinstance(names, dict) and names.get(button.key):
            return names[button.key]
        if button.legacy_label:
            legacy = self.ui.config.get(button.legacy_label[0])
            if isinstance(legacy, dict) and legacy.get(button.legacy_label[1]):
                return legacy[button.legacy_label[1]]
        return button.default_label

    def buttons(self):
        return [b for r in self.records if not r.error for b in r.buttons]

    def set_labels(self, labels):
        """labels: {button key: text}; empty text restores the default label."""
        names = self.ui.config.get(NAMES_KEY)
        names = dict(names) if isinstance(names, dict) else {}
        for button in self.buttons():
            if button.key in labels:
                names[button.key] = labels[button.key].strip() or button.default_label
                self.ui.set_button_text(button, names[button.key])
        self.ui.config[NAMES_KEY] = names
        self.ui.save_config()

    # --- visibility and state ---
    def is_visible(self, addon_id):
        visible = self.ui.config.get(VISIBILITY_KEY, {})
        return bool(visible.get(addon_id, True)) if isinstance(visible, dict) else True

    def set_visible(self, addon_id, visible):
        settings = self.ui.config.get(VISIBILITY_KEY)
        settings = dict(settings) if isinstance(settings, dict) else {}
        settings[addon_id] = bool(visible)
        self.ui.config[VISIBILITY_KEY] = settings
        self.ui.save_config()
        self.refresh_all()

    def set_connected(self, connected):
        self.connected = bool(connected)
        self.refresh_all()

    def button_state(self, button):
        if not self.is_visible(button.addon_id) or not button.enabled:
            return "disabled"
        if button.busy_group and self.lock(button.busy_group).locked():
            return "disabled"
        if button.requires_connection and not self.connected:
            return "disabled"
        return "normal"

    def refresh_button(self, button):
        if button.widget is not None:
            self.ui.set_button_state(button, self.button_state(button))

    def refresh_group(self, group):
        for button in self.buttons():
            if button.busy_group == group:
                self.refresh_button(button)

    def refresh_all(self):
        for bar in BARS:
            ordered = [b for b in self.buttons() if b.bar == bar]
            shown = [b for b in ordered if self.is_visible(b.addon_id)]
            self.ui.layout_bar(bar, ordered, shown)
            for button in ordered:
                self.refresh_button(button)

    def run_action(self, action_id):
        """Run a registered action. Hidden add-ons do not run (also for shortcuts)."""
        entry = self.actions.get(action_id)
        if entry is None or not self.is_visible(entry[0]):
            return False
        entry[1]()
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
    host = property(lambda self: self.app.addon_host)

    def save_config(self):
        self._save_config(self.app.config)

    def set_status(self, text, status_type, clear_delay):
        self.app.set_status(text, status_type, clear_delay=clear_delay)

    def show_message(self, kind, title, message, parent):
        from tkinter import messagebox
        target = parent if parent is not None and parent.winfo_exists() else self.app
        show = {"error": messagebox.showerror, "warning": messagebox.showwarning}.get(kind, messagebox.showinfo)
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

    # --- buttons ---
    def create_button(self, button, label):
        import tkinter as tk
        import customtkinter as ctk
        _, frame = self.app.addon_bars[button.bar]
        # A named holder keeps the widget path stable for keyboard shortcut assignments.
        holder = tk.Frame(frame, name=f"addon_{button.addon_id}_{button.button_id}",
                          bg=self.app.ui_colors["panel"], bd=0, highlightthickness=0)
        widget = ctk.CTkButton(
            holder, text=label, height=28, fg_color=button.color, hover_color=button.hover_color,
            text_color="#FFFFFF", corner_radius=6, command=button.command,
            font=ctk.CTkFont(family=self.app.ui_font_family, size=12, weight="bold"),
        )
        widget.pack()
        widget.bind("<Button-3>", lambda event, b=button: self.button_menu(event, b))
        widget.holder = holder
        return widget

    def destroy_button(self, button):
        if button.widget is not None:
            button.widget.holder.destroy()

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

    def button_menu(self, event, button):
        import tkinter as tk
        menu = tk.Menu(self.app, tearoff=False)
        menu.add_command(label="ボタン名を変更...", command=lambda: self.open_names(button.key))
        menu.add_command(label="初期の名前に戻す", command=lambda: self.host.set_labels({button.key: ""}))
        menu.add_separator()
        menu.add_command(label="このボタンを非表示にする", command=lambda: self.set_visible(button.addon_id, False))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # --- Tools > Add-ons ---
    def set_visible(self, addon_id, visible):
        self.host.set_visible(addon_id, visible)
        if addon_id in self._menu_vars:
            self._menu_vars[addon_id].set(visible)

    def build_addon_menu(self, records):
        import tkinter as tk
        menu = self.app.addon_menu
        menu.delete(0, "end")
        self._menu_vars.clear()
        for record in records:
            if record.error:
                menu.add_command(label=f"{record.name}（読み込みエラー）", state="disabled")
                continue
            variable = tk.BooleanVar(self.app, value=self.host.is_visible(record.id))
            self._menu_vars[record.id] = variable
            menu.add_checkbutton(label=record.name, variable=variable,
                                 command=lambda r=record.id, v=variable: self.host.set_visible(r, v.get()))
        if not records:
            menu.add_command(label="アドオンがありません", state="disabled")
        menu.add_separator()
        menu.add_command(label="アドオンを追加...", command=self.install_dialog)
        remove_menu = tk.Menu(menu, tearoff=False)
        for record in records:
            remove_menu.add_command(label=record.name, command=lambda r=record: self.remove_dialog(r))
        menu.add_cascade(label="アドオンを削除", menu=remove_menu, state="normal" if records else "disabled")
        menu.add_command(label="ボタン名の設定...", command=self.open_names,
                         state="normal" if self.host.buttons() else "disabled")
        menu.add_command(label="アドオンフォルダを開く", command=self.open_folder)

    def install_dialog(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(parent=self.app, title="追加するアドオンを選択",
                                          filetypes=[("アドオン (*.py)", "*.py")])
        if not path:
            return
        try:
            record = self.host.install(path)
        except Exception as exc:
            messagebox.showerror("アドオンを追加できません", str(exc), parent=self.app)
            return
        self.app.set_status(f"アドオンを追加しました: {record.name}", "success", clear_delay=4)

    def remove_dialog(self, record):
        from tkinter import messagebox
        if not messagebox.askyesno("アドオンの削除", f"「{record.name}」を削除しますか？\nファイルは addons/_removed に移動します。",
                                   parent=self.app):
            return
        try:
            self.host.remove(record)
        except OSError as exc:
            messagebox.showerror("アドオンを削除できません", str(exc), parent=self.app)
            return
        self.app.set_status(f"アドオンを削除しました: {record.name}", "success", clear_delay=4)

    def open_folder(self):
        import os
        folder = self.host.directory
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def open_names(self, focus_key=None):
        import tkinter as tk
        import customtkinter as ctk
        buttons = self.host.buttons()
        if not buttons:
            return
        colors, family = self.app.ui_colors, self.app.ui_font_family
        font = lambda size, bold=False: ctk.CTkFont(family=family, size=size, weight="bold" if bold else "normal")
        window = ctk.CTkToplevel(self.app)
        window.title("ボタン名の設定")
        window.configure(fg_color=colors["background"])
        window.transient(self.app)
        window.grab_set()
        form = ctk.CTkFrame(window, fg_color=colors["panel"], corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=(16, 8))
        entries = {}
        for index, button in enumerate(buttons):
            ctk.CTkLabel(form, text=next(r.name for r in self.host.records if r.id == button.addon_id),
                         font=font(12, True), text_color=colors["text"], anchor="w").pack(
                fill="x", padx=16, pady=(12 if index == 0 else 8, 2))
            row = ctk.CTkFrame(form, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(0, 4))
            entry = ctk.CTkEntry(row, font=font(12), height=30, width=360)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entry.insert(0, self.host.label(button))
            ctk.CTkButton(row, text="初期名", width=60, height=28, fg_color="transparent",
                          hover_color=colors["hover"], border_width=1, border_color=colors["border"],
                          text_color=colors["text"], font=font(11),
                          command=lambda e=entry, d=button.default_label: (e.delete(0, tk.END), e.insert(0, d))).pack(side="right")
            entries[button.key] = entry
            if button.key == focus_key:
                entry.focus_set()
                entry.select_range(0, tk.END)

        def save():
            self.host.set_labels({key: entry.get() for key, entry in entries.items()})
            window.destroy()

        bar = ctk.CTkFrame(window, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(bar, text="保存", width=90, fg_color="#2563EB", hover_color="#1D4ED8",
                      text_color="#FFFFFF", font=font(12, True), command=save).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bar, text="キャンセル", width=90, fg_color=colors["button"], hover_color=colors["hover"],
                      text_color=colors["text"], font=font(12), command=window.destroy).pack(side="right")
        return window
