"""Order entry UI and validation; no network or QAD side effects."""

import calendar
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import difflib
from functools import lru_cache
import io
import json
from pathlib import Path
import re
import time
import tkinter as tk
from tkinter import messagebox
import unicodedata

import customtkinter as ctk
from ui_fonts import FONT_FAMILY
from order_date_picker import OrderDateRangePicker

try:
    from terminal_core import KEY_SEQUENCES
except ImportError:
    KEY_SEQUENCES = {
        "Return": "\r", "KP_Enter": "\r", "space": " ",
        "BackSpace": "\b", "Delete": "\b", "KP_Delete": "\b",
        "Tab": "\t", "Escape": "\x1b",
        "F1": "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
        "Up": "\x1b[A", "Down": "\x1b[B", "Right": "\x1b[C", "Left": "\x1b[D",
        "Ctrl+F": "\x06",
    }


# 実送信とF3表示で共有する現行の確定キー。実機ログとの相違は設計書7章参照。
ORDER_TOTALS_COMMIT_KEY = "F1"

WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
ITEM_FIELDS = ("product_name", "width", "length", "quantity", "price")
ITEM_LABELS = ("Item code", "巾", "長さ", "本数", "価格")
SHORTCUT_MODIFIERS = {"ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift"}
SHORTCUT_RESERVED = {"Ctrl+Shift+Esc", "Ctrl+A", "Ctrl+C", "Ctrl+D", "Ctrl+E", "Ctrl+H",
                     "Ctrl+T", "Ctrl+V", "Ctrl+W", "Ctrl+Tab", "Ctrl+Shift+C",
                     "Ctrl+Shift+Tab", "Shift+Tab", "Ctrl+PageUp", "Ctrl+PageDown"}


def normalize_shortcut(shortcut):
    """Return a canonical modified or single key, or reject unsafe/system-reserved keys."""
    raw = str(shortcut).replace("Control", "Ctrl").strip()
    parts = [part.strip() for part in raw.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError("キーを指定してください。")
    modifiers = []
    key = None
    for part in parts:
        lowered = part.lower()
        if lowered == "alt":
            raise ValueError("Altキーはショートカットに使用できません。")
        modifier = SHORTCUT_MODIFIERS.get(lowered)
        if modifier:
            if modifier in modifiers:
                raise ValueError("同じ修飾キーを重複して指定できません。")
            modifiers.append(modifier)
        elif key is None:
            key = part
        else:
            raise ValueError("割り当てるキーは1つ指定してください。")
    if key is None:
        raise ValueError("キーを指定してください。")
    aliases = {"return": "Enter", "kp_enter": "Enter", "spacebar": "Space", "space": "Space",
               "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
               "prior": "PageUp", "next": "PageDown", "pageup": "PageUp",
               "pagedown": "PageDown", "left": "Left", "right": "Right",
               "up": "Up", "down": "Down", "tab": "Tab", "home": "Home", "end": "End",
               "insert": "Insert", "pause": "Pause"}
    lowered = key.lower()
    if re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", lowered):
        key = lowered.upper()
    elif len(key) == 1:
        key = key.upper()
    else:
        key = aliases.get(lowered, key)
    valid_keys = r"[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|Enter|Space|Esc|Backspace|Delete|PageUp|PageDown|Left|Right|Up|Down|Tab|Home|End|Insert|Pause"
    if not re.fullmatch(valid_keys, key):
        raise ValueError("文字、数字、Fキー、矢印キー、特殊キーのいずれかを指定してください。")
    if not modifiers:
        allowed_single = re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])|PageUp|PageDown|Insert|Pause|Home|End", key)
        if not allowed_single:
            raise ValueError(f"「{key}」は単独では設定できません。Fキー（F1〜F24）や特殊キーを指定するか、Ctrl/Shiftと組み合わせてください。")
    ordered = [modifier for modifier in ("Ctrl", "Shift") if modifier in modifiers]
    result = "+".join((*ordered, key)) if ordered else key
    if result in SHORTCUT_RESERVED:
        raise ValueError("Windowsまたはターミナルの標準ショートカットは変更できません。")
    return result


def shortcut_from_key_event(event):
    """Read key and modifiers from Tk's event state (single keys and Ctrl/Shift allowed)."""
    key = event.keysym
    if key in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock", "Scroll_Lock"):
        return None
    state = event.state
    modifiers = [name for bit, name in ((0x4, "Ctrl"), (0x1, "Shift")) if state & bit]
    aliases = {"return": "Enter", "kp_enter": "Enter", "space": "Space",
               "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
               "prior": "PageUp", "next": "PageDown"}
    key = aliases.get(key.lower(), key.upper() if len(key) == 1 else key)
    shortcut_str = "+".join((*modifiers, key)) if modifiers else key
    try:
        return normalize_shortcut(shortcut_str)
    except ValueError:
        return None


class ShortcutSettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, actions, assignments, colors, font_family, on_save, on_capture):
        super().__init__(parent)
        self.actions = actions
        self.assignments = assignments
        self.colors = colors
        self.font_family = font_family
        self.on_save = on_save
        self.on_capture = on_capture
        self.selected_id = None
        self.geometry("540x250")
        self.minsize(480, 230)
        self.resizable(False, False)
        self.configure(fg_color=colors["panel"])
        self.transient(parent)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="対象", text_color=colors["text"],
                     font=(font_family, 12)).grid(row=0, column=0, padx=20, pady=(16, 4), sticky="w")
        self.action_names = {label: action_id for action_id, (label, _) in actions.items()}
        self.action_picker = ctk.CTkComboBox(
            self, values=list(self.action_names), height=34, font=(font_family, 13),
            dropdown_font=(font_family, 12), fg_color="#FFFFFF", text_color=colors["text"],
            border_color=colors["border"], button_color=colors["button"],
            button_hover_color=colors["hover"], corner_radius=7, command=self._select_action,
        )
        self.action_picker.grid(row=1, column=0, padx=20, sticky="ew")
        self.action_picker.bind("<KeyPress>", self._block_picker_typing, add="+")
        ctk.CTkLabel(self, text="キー", text_color=colors["text"],
                     font=(font_family, 12)).grid(row=2, column=0, padx=20, pady=(12, 4), sticky="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=3, column=0, padx=20, sticky="ew")
        row.grid_columnconfigure(0, weight=1)
        self.key_entry = ctk.CTkEntry(row, height=36, font=(font_family, 13),
                                     fg_color="#FFFFFF", text_color=colors["text"],
                                     border_color=colors["border"], corner_radius=7,
                                     placeholder_text="未設定")
        self.key_entry.grid(row=0, column=0, sticky="ew")
        self.record_button = tk.Button(row, text="キーを記録", command=self._start_recording,
                                       bg=colors["button"], fg=colors["text"], relief="flat", bd=0,
                                       font=(font_family, 11), padx=12, pady=7, takefocus=True)
        self.record_button.grid(row=0, column=1, padx=(8, 0))
        self.error_label = ctk.CTkLabel(self, text="", text_color=colors["error"],
                                        font=(font_family, 11), anchor="w")
        self.error_label.grid(row=4, column=0, padx=20, pady=(5, 0), sticky="ew")
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=5, column=0, padx=20, pady=(8, 14), sticky="ew")
        self.clear_button = tk.Button(self.footer, text="解除", command=self._clear,
                                      bg=colors["panel"], fg=colors["muted"], relief="flat", bd=0,
                                      font=(font_family, 11), padx=10, pady=7, takefocus=True)
        self.clear_button.pack(side="left")
        self.save_button = tk.Button(self.footer, text="設定", command=self._save,
                                     bg=colors["accent"], fg=colors["on_accent"],
                                     activebackground=colors["accent_hover"],
                                     relief="flat", bd=0, font=(font_family, 11),
                                     padx=18, pady=7, takefocus=True)
        self.save_button.pack(side="right")
        if self.action_names:
            self.action_picker.set(next(iter(self.action_names)))
            self._select_action(self.action_picker.get())
        self.update_idletasks()
        parent_x, parent_y = parent.winfo_rootx(), parent.winfo_rooty()
        x = max(0, min(parent_x + (parent.winfo_width() - self.winfo_width()) // 2,
                       self.winfo_screenwidth() - self.winfo_width()))
        y = max(0, min(parent_y + (parent.winfo_height() - self.winfo_height()) // 2,
                       self.winfo_screenheight() - self.winfo_height() - 48))
        self.geometry(f"+{x}+{y}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _block_picker_typing(self, event):
        if event.keysym not in ("Up", "Down", "Return", "KP_Enter", "Escape"):
            return "break"

    def _select_action(self, label):
        self.selected_id = self.action_names.get(label)
        self.key_entry.configure(state="normal")
        self.key_entry.delete(0, "end")
        current = self.assignments.get(self.selected_id, "")
        if current:
            self.key_entry.insert(0, current)
        self.key_entry.configure(state="readonly")
        self.error_label.configure(text="")

    def _start_recording(self):
        self.key_entry.configure(state="normal")
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, "キー入力待ち")
        self.error_label.configure(text="")
        self.on_capture(self.key_entry)

    def capture(self, event):
        key = event.keysym
        if key in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock", "Scroll_Lock"):
            return "break"
        state = event.state
        modifiers = [name for bit, name in ((0x4, "Ctrl"), (0x1, "Shift")) if state & bit]
        aliases = {"return": "Enter", "kp_enter": "Enter", "space": "Space",
                   "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
                   "prior": "PageUp", "next": "PageDown"}
        key = aliases.get(key.lower(), key.upper() if len(key) == 1 else key)
        shortcut_str = "+".join((*modifiers, key)) if modifiers else key
        try:
            shortcut = normalize_shortcut(shortcut_str)
        except ValueError as exc:
            self.error_label.configure(text=str(exc))
            return "break"
        self.key_entry.configure(state="normal")
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, shortcut)
        self.key_entry.configure(state="readonly")
        self.error_label.configure(text="")
        self.on_capture(None)
        return "break"

    def _clear(self):
        if self.on_save(self.selected_id, ""):
            self._select_action(self.action_picker.get())

    def _save(self):
        shortcut = self.key_entry.get().strip()
        if shortcut == "キー入力待ち":
            self.error_label.configure(text="保存するキーを押してください。")
            return
        if shortcut:
            try:
                shortcut = normalize_shortcut(shortcut)
            except ValueError as exc:
                self.error_label.configure(text=str(exc))
                return
        if self.on_save(self.selected_id, shortcut):
            self.destroy()


def read_choice_csv(path, field):
    aliases = {"customer_name": ("顧客名", "customer_name", "customer"),
               "ship_to": ("納品先", "ship_to", "destination")}[field]
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp932")
    rows = [row for row in csv.reader(io.StringIO(content, newline="")) if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSVに候補がありません。")
    header = [cell.strip().lower() for cell in rows[0]]
    column = next((i for i, label in enumerate(header) if label in aliases), None)
    if column is not None:
        rows = rows[1:]
    elif all(len(row) == 1 for row in rows):
        column = 0
    else:
        raise ValueError(f"CSVの先頭行に「{aliases[0]}」列を設定してください。")
    values = list(dict.fromkeys(row[column].strip() for row in rows
                               if len(row) > column and row[column].strip()))
    if not values:
        raise ValueError(f"CSVの「{aliases[0]}」列に候補がありません。")
    return values


def read_customer_ship_to_csv(path):
    """Read a two-column customer/destination CSV into ordered choices."""
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp932")
    rows = [row for row in csv.reader(io.StringIO(content, newline=""))
            if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSVに顧客・納品先の組み合わせがありません。")

    headers = [cell.strip().lower() for cell in rows[0]]
    customer_aliases = {"顧客", "顧客名", "customer", "customer_name"}
    ship_to_aliases = {"納品先", "ship_to", "destination"}
    customer_column = next((i for i, label in enumerate(headers) if label in customer_aliases), None)
    ship_to_column = next((i for i, label in enumerate(headers) if label in ship_to_aliases), None)
    has_header = customer_column is not None and ship_to_column is not None
    if not has_header:
        customer_column, ship_to_column = 0, 1

    choices = {}
    for row in rows[1:] if has_header else rows:
        if len(row) <= max(customer_column, ship_to_column):
            continue
        customer, ship_to = row[customer_column].strip(), row[ship_to_column].strip()
        if not customer or not ship_to:
            continue
        destinations = choices.setdefault(customer, [])
        if ship_to not in destinations:
            destinations.append(ship_to)
    if not choices:
        raise ValueError("顧客名と納品先が両方入力された行がありません。")
    return choices


class CustomerInfoData:
    """Holds customer names, their destination lists, and destination address mappings."""

    def __init__(self, raw_data=None):
        self.raw_data = {}
        self.customer_names = []
        self.customer_ship_tos = {}
        self.addresses = {}
        if raw_data:
            self.load(raw_data)

    def load(self, data):
        self.raw_data = data if isinstance(data, dict) else {}
        cust_order = []
        cust_dest_map = {}
        addr_map = {}

        if isinstance(data, dict):
            for ccode, cinfo in data.items():
                if not isinstance(cinfo, dict):
                    continue
                cname = str(cinfo.get("name", "")).strip()
                if not cname:
                    continue
                if cname not in cust_dest_map:
                    cust_order.append(cname)
                    cust_dest_map[cname] = []

                dests = cinfo.get("destinations", {})
                if isinstance(dests, dict):
                    for dcode, dinfo in dests.items():
                        if not isinstance(dinfo, dict):
                            continue
                        dname = str(dinfo.get("name", "")).strip()
                        addr = str(dinfo.get("address", ""))
                        if not dname:
                            continue
                        if dname not in cust_dest_map[cname]:
                            cust_dest_map[cname].append(dname)
                        key = (cname, dname)
                        if key not in addr_map or (not addr_map[key] and addr):
                            addr_map[key] = addr

        self.customer_names = cust_order
        self.customer_ship_tos = cust_dest_map
        self.addresses = addr_map

    def get_destinations(self, customer):
        return list(self.customer_ship_tos.get(str(customer).strip(), []))

    def get_address(self, customer, destination):
        c = str(customer).strip()
        d = str(destination).strip()
        return self.addresses.get((c, d), "")

    def get_customer_key(self, customer, destination=None):
        """顧客名に対応するKey (customerCode) を返す。納品先がある場合は所属ccodeを優先特定。"""
        c = str(customer).strip()
        d = str(destination).strip() if destination else ""
        if not c:
            return ""

        if d and isinstance(self.raw_data, dict):
            for ccode, cinfo in self.raw_data.items():
                if not isinstance(cinfo, dict):
                    continue
                if str(cinfo.get("name", "")).strip() == c:
                    dests = cinfo.get("destinations", {})
                    if isinstance(dests, dict):
                        for dcode, dinfo in dests.items():
                            if isinstance(dinfo, dict) and str(dinfo.get("name", "")).strip() == d:
                                return str(ccode)

        if isinstance(self.raw_data, dict):
            for ccode, cinfo in self.raw_data.items():
                if isinstance(cinfo, dict) and str(cinfo.get("name", "")).strip() == c:
                    return str(ccode)

        return ""

    def get_destination_key(self, customer, destination):
        """顧客名と納品先に対応するKey (納品先Code) を返す。"""
        c = str(customer).strip()
        d = str(destination).strip()
        if not d:
            return ""

        if isinstance(self.raw_data, dict):
            for ccode, cinfo in self.raw_data.items():
                if not isinstance(cinfo, dict):
                    continue
                if c and str(cinfo.get("name", "")).strip() != c:
                    continue
                dests = cinfo.get("destinations", {})
                if isinstance(dests, dict):
                    for dcode, dinfo in dests.items():
                        if isinstance(dinfo, dict) and str(dinfo.get("name", "")).strip() == d:
                            return str(dcode)

            for ccode, cinfo in self.raw_data.items():
                if not isinstance(cinfo, dict):
                    continue
                dests = cinfo.get("destinations", {})
                if isinstance(dests, dict):
                    for dcode, dinfo in dests.items():
                        if isinstance(dinfo, dict) and str(dinfo.get("name", "")).strip() == d:
                            return str(dcode)

        return ""


def find_customer_info_path():
    candidates = [
        Path(__file__).resolve().parent / "customerInfo.txt",
        Path.cwd() / "customerInfo.txt",
        Path(r"C:\Users\0138018\.antigravity\mfgpro_controller\customerInfo.txt"),
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except Exception:
            pass
    return None


def read_customer_info_file(path=None):
    if path is None:
        path = find_customer_info_path()
    if path is None:
        return CustomerInfoData()

    path_obj = Path(path)
    if not path_obj.is_file():
        return CustomerInfoData()

    raw = path_obj.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            content = raw.decode(enc)
            data = json.loads(content)
            return CustomerInfoData(data)
        except Exception:
            continue
    return CustomerInfoData()


def find_item_list_path():
    candidates = [
        Path(__file__).resolve().parent / "itemList.json",
        Path(__file__).resolve().parent / "item_list.json",
        Path.cwd() / "itemList.json",
        Path.cwd() / "item_list.json",
        Path(r"C:\Users\0138018\.antigravity\mfgpro_controller\itemList.json"),
        Path(r"C:\Users\0138018\.antigravity\mfgpro_controller\item_list.json"),
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except Exception:
            pass
    return None


def read_item_list_file(path=None):
    if path is None:
        path = find_item_list_path()
    if path is None:
        return {}

    path_obj = Path(path)
    if path_obj.is_dir():
        for fname in ("itemList.json", "item_list.json"):
            cand = path_obj / fname
            if cand.is_file():
                path_obj = cand
                break
        else:
            return {}

    if not path_obj.is_file():
        return {}

    raw = path_obj.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            content = raw.decode(enc)
            data = json.loads(content)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            continue
    return {}


def handle_field_delete(widget, on_change=None):
    """入力欄（Entry / CTkEntry / HighlightComboBox / Textbox）でDelete/KP_Delete押下時に確実に文字を消去する。
    1. 選択範囲がある場合：選択範囲の文字列を削除
    2. カーソル位置の右側に文字がある場合：カーソル右側の文字を削除（通常のDelete）
    3. カーソルが末尾にある場合（入力直後など）：直前の文字を削除（Backspace相当で消去）
    4. 削除後にon_changeコールバックを実行し、連動表示（コード・説明など）を即時更新
    """
    try:
        # Textbox (tk.Text or CTkTextbox)
        if hasattr(widget, "_textbox") or isinstance(widget, tk.Text):
            raw_tb = getattr(widget, "_textbox", widget)
            if raw_tb.tag_ranges("sel"):
                raw_tb.delete("sel.first", "sel.last")
            else:
                ins = raw_tb.index("insert")
                end_idx = raw_tb.index("end-1c")
                if raw_tb.compare(ins, "<", end_idx):
                    raw_tb.delete(ins)
                elif raw_tb.compare(ins, ">", "1.0"):
                    raw_tb.delete(f"{ins}-1c")
            if callable(on_change):
                on_change()
            return "break"

        # Entry (tk.Entry or CTkEntry or HighlightComboBox)
        raw_entry = getattr(widget, "_entry", widget)
        if hasattr(raw_entry, "selection_present") and raw_entry.selection_present():
            first = raw_entry.index("sel.first")
            last = raw_entry.index("sel.last")
            raw_entry.delete(first, last)
        else:
            ins = raw_entry.index("insert")
            val = raw_entry.get()
            t_len = len(val)
            if ins < t_len:
                raw_entry.delete(ins)
            elif ins > 0:
                raw_entry.delete(ins - 1)
        if callable(on_change):
            on_change()
        return "break"
    except Exception:
        return None


class HighlightComboBox(ctk.CTkComboBox):
    """選択中のドロップダウン項目の背景色を変え、何が選択されているか明瞭にするComboBox。
    Entry互換の insert/delete メソッドも提供。"""
    def __init__(self, *args, colors=None, on_change=None, **kwargs):
        self.ui_colors = colors or {}
        self.on_change = on_change
        super().__init__(*args, **kwargs)
        self.set("")
        self._entry.bind("<Delete>", lambda e: handle_field_delete(self._entry, on_change=lambda: self.on_change(self.get()) if callable(self.on_change) else None))
        self._entry.bind("<KP_Delete>", lambda e: handle_field_delete(self._entry, on_change=lambda: self.on_change(self.get()) if callable(self.on_change) else None))

    def _open_dropdown_menu(self):
        current_val = self.get().strip()
        accent_bg = self.ui_colors.get("accent", "#0284C7")
        accent_fg = self.ui_colors.get("on_accent", "#FFFFFF")
        hover_bg = self.ui_colors.get("accent_hover", "#0369A1")
        panel_bg = self.ui_colors.get("panel", "#FFFFFF")
        text_fg = self.ui_colors.get("text", "#0F172A")

        if hasattr(self, "_dropdown_menu") and self._dropdown_menu is not None:
            menu = self._dropdown_menu
            try:
                num = menu.index("end")
                if num is not None:
                    for i in range(num + 1):
                        raw = self._values[i] if i < len(self._values) else ""
                        raw_str = str(raw).strip()
                        if raw_str and raw_str == current_val:
                            # 選択中の項目: アクセント背景色・白文字・インジケータ付き
                            menu.entryconfigure(
                                i,
                                label=f"  *  {raw}",
                                background=accent_bg,
                                foreground=accent_fg,
                                activebackground=hover_bg,
                                activeforeground=accent_fg,
                            )
                        else:
                            menu.entryconfigure(
                                i,
                                label=f"     {raw}",
                                background=panel_bg,
                                foreground=text_fg,
                                activebackground=self.ui_colors.get("hover", "#E2E8F0"),
                                activeforeground=text_fg,
                            )
            except Exception:
                pass

        super()._open_dropdown_menu()

    def insert(self, index, string):
        self._entry.insert(index, string)
        if callable(self.on_change):
            self.on_change(self.get())

    def delete(self, first, last=None):
        self._entry.delete(first, last)
        if callable(self.on_change):
            self.on_change(self.get())

    def set(self, value):
        super().set(value)
        if callable(self.on_change):
            self.on_change(self.get())


class ProductComboBox(HighlightComboBox):
    """Show the lightweight search popup from the arrow as well as the entry."""

    def _open_dropdown_menu(self):
        autocomplete = getattr(self, "product_autocomplete", None)
        if autocomplete is not None:
            autocomplete.show_click_candidates()
            return
        super()._open_dropdown_menu()


def to_katakana(text):
    """ひらがなを全角カタカナに変換"""
    return "".join(chr(ord(c) + 0x60) if "\u3041" <= c <= "\u3096" else c for c in text)


@lru_cache(maxsize=16384)
def _normalize_for_search_cached(text):
    return to_katakana(unicodedata.normalize("NFKC", text).strip().lower())


def normalize_for_search(text):
    """NFKC正規化＋全角カタカナ統一＋小文字化で表記揺れを完全吸収"""
    # 候補一覧はキー入力ごとに同じ文字列を正規化するため、結果を再利用する。
    return _normalize_for_search_cached(str(text))


def search_candidates(query, candidates, limit=10):
    """入力値に近い候補を、前方一致＞部分一致＞あいまい一致の順にスコアリングして抽出"""
    if not query:
        return list(candidates)[:limit]
    nq = normalize_for_search(query)
    if not nq:
        return list(candidates)[:limit]

    exact = []
    prefix = []
    substr = []
    fuzzy = []

    for c in candidates:
        nc = normalize_for_search(c)
        if nc == nq:
            exact.append(c)
        elif nc.startswith(nq):
            prefix.append((len(nc), c))
        elif nq in nc:
            substr.append((nc.find(nq), len(nc), c))
        elif len(nq) >= 2:
            # real_quick_ratio/quick_ratioはratioの上限値。0.4未満が確定した候補は精密比較を省く。
            matcher = difflib.SequenceMatcher(None, nq, nc)
            if matcher.real_quick_ratio() >= 0.4 and matcher.quick_ratio() >= 0.4:
                sim = matcher.ratio()
                if sim >= 0.4:
                    fuzzy.append((sim, c))

    prefix.sort(key=lambda x: x[0])
    substr.sort(key=lambda x: (x[0], x[1]))
    fuzzy.sort(key=lambda x: -x[0])

    res = exact + [x[1] for x in prefix] + [x[2] for x in substr] + [x[1] for x in fuzzy]
    return list(dict.fromkeys(res))[:limit]


class AutocompletePopup:
    """入力欄（CTkComboBox/Entry）の直下に候補リストを自動ポップアップするコントローラ"""

    PAGE_SIZE = 10

    def __init__(self, parent_widget, colors, font_family, on_select=None):
        self.parent_widget = parent_widget
        self.colors = colors
        self.font_family = font_family
        self.on_select = on_select
        self.all_candidates = []
        self.filtered_candidates = []
        self.popup = None
        self.listbox = None
        self._selected_index = -1
        self._is_visible = False
        self._is_updating_entry = False
        self._original_query = ""
        self._page_source = None
        self._page_offset = 0
        self._page_query = None

        if hasattr(parent_widget, "_entry"):
            self.entry = parent_widget._entry
        elif hasattr(parent_widget, "entry"):
            self.entry = getattr(parent_widget.entry, "_entry", parent_widget.entry)
        else:
            self.entry = parent_widget

        self.entry.bind("<KeyRelease>", self._on_key_release, add="+")
        self.entry.bind("<Down>", self._on_down_key, add="+")
        self.entry.bind("<Up>", self._on_up_key, add="+")
        self.entry.bind("<Return>", self._on_return_key, add="+")
        self.entry.bind("<KP_Enter>", self._on_return_key, add="+")
        self.entry.bind("<Escape>", self._on_escape_key, add="+")
        self.entry.bind("<Tab>", self._on_tab_key, add="+")
        self.entry.bind("<FocusOut>", self._on_focus_out, add="+")
        self.entry.bind("<Button-1>", self._on_entry_click, add="+")
        if self.entry is not parent_widget:
            parent_widget.bind("<Return>", self._on_return_key, add="+")
            parent_widget.bind("<KP_Enter>", self._on_return_key, add="+")

    def _on_entry_click(self, event=None):
        if not self.is_open():
            self.show_click_candidates()

    def show_click_candidates(self):
        if not self.all_candidates:
            return
        current = self.entry.get().strip()
        self._page_source = self.all_candidates
        self._page_query = None
        selected = self.all_candidates.index(current) if current in self.all_candidates else 0
        self._show_page((selected // self.PAGE_SIZE) * self.PAGE_SIZE)

    def _show_page(self, offset):
        self._page_offset = offset
        self._show_popup(self._page_source[offset:offset + self.PAGE_SIZE])

    def set_candidates(self, candidates):
        self.all_candidates = [str(c).strip() for c in candidates if str(c).strip()]
        self._page_source = None
        self._page_query = None

    def is_open(self):
        return bool(self.popup is not None and self.popup.winfo_exists() and self._is_visible)

    def _ensure_popup(self):
        if self.popup is None or not self.popup.winfo_exists():
            top = self.parent_widget.winfo_toplevel()
            self.popup = tk.Toplevel(top)
            self.popup.wm_overrideredirect(True)
            try:
                self.popup.attributes("-topmost", True)
            except Exception:
                pass
            frame = tk.Frame(self.popup, bg=self.colors["border"], bd=1)
            frame.pack(fill="both", expand=True)
            self.listbox = tk.Listbox(
                frame, font=(self.font_family, 11),
                bg="#FFFFFF", fg=self.colors["text"],
                selectbackground=self.colors["accent"],
                selectforeground=self.colors["on_accent"],
                exportselection=False,
                activestyle="none", relief="flat", bd=0, highlightthickness=0,
            )
            self.listbox.pack(fill="both", expand=True, padx=1, pady=1)
            self.listbox.bind("<Button-1>", self._on_listbox_click)
            self.listbox.bind("<Motion>", self._on_listbox_motion)

    def _on_key_release(self, event):
        if getattr(self, "_is_updating_entry", False):
            return
        if event.keysym in ("Return", "KP_Enter", "Escape", "Up", "Down", "Left", "Right",
                            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                            "Caps_Lock", "Tab", "ISO_Left_Tab"):
            return
        query = self.entry.get().strip()
        self._original_query = query
        if not query:
            self.close()
            return
        hits = search_candidates(query, self.all_candidates, limit=10)
        if not hits:
            self.close()
            return
        if len(hits) == 1 and hits[0] == query:
            self.close()
            return
        top_hit = next((h for h in hits if h == query), hits[0])
        if top_hit in self.all_candidates:
            master_idx = self.all_candidates.index(top_hit)
            self._page_source = self.all_candidates
            self._page_query = query
            self._page_offset = master_idx
            self._show_popup(hits)
        else:
            self._page_source = None
            self._page_query = query
            self._page_offset = 0
            self._show_popup(hits)

    def _show_popup(self, items):
        self._ensure_popup()
        self.filtered_candidates = items
        self.listbox.delete(0, "end")

        current_val = self.entry.get().strip()
        matched_idx = -1
        accent_light = self.colors.get("accent_light", "#E0F2FE")
        accent_color = self.colors.get("accent", "#0284C7")
        text_color = self.colors.get("text", "#0F172A")

        for idx, item in enumerate(items):
            item_str = str(item).strip()
            if current_val and item_str == current_val:
                matched_idx = idx
                self.listbox.insert("end", f"  *  {item_str}")
                self.listbox.itemconfigure(idx, background=accent_light, foreground=accent_color)
            else:
                self.listbox.insert("end", f"     {item_str}")
                self.listbox.itemconfigure(idx, background="#FFFFFF", foreground=text_color)

        if matched_idx >= 0:
            self._selected_index = matched_idx
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(matched_idx)
            self.listbox.see(matched_idx)
        else:
            self._selected_index = -1
            self.listbox.selection_clear(0, "end")

        if self.parent_widget.winfo_width() <= 1:
            self.parent_widget.update_idletasks()
        rx = self.parent_widget.winfo_rootx()
        ry = self.parent_widget.winfo_rooty() + self.parent_widget.winfo_height() + 2
        rw = max(self.parent_widget.winfo_width(), 260)
        rh = min(220, len(items) * 24 + 4)

        try:
            screen_h = self.parent_widget.winfo_screenheight()
            if ry + rh > screen_h - 40:
                ry = max(0, self.parent_widget.winfo_rooty() - rh - 2)
        except Exception:
            pass

        self.popup.geometry(f"{rw}x{rh}+{rx}+{ry}")
        self.popup.deiconify()
        self.popup.lift()
        self._is_visible = True
        self.entry.focus_set()

    def _apply_selection(self, index):
        if not self.filtered_candidates:
            return
        self._selected_index = index
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)
        if 0 <= index < len(self.filtered_candidates):
            val = self.filtered_candidates[index]
            self._set_entry_text(val)

    def _set_entry_text(self, text):
        self._is_updating_entry = True
        try:
            self.entry.delete(0, "end")
            self.entry.insert(0, text)
            self.entry.selection_range(0, "end")
            self.entry.icursor("end")
        finally:
            self._is_updating_entry = False

    def _on_down_key(self, event=None):
        if self.is_open() and self.filtered_candidates:
            if self._selected_index >= len(self.filtered_candidates) - 1:
                source = self._get_page_source()
                if source is not None and len(source) > 0:
                    offset = self._page_offset + len(self.filtered_candidates)
                    if offset < len(source):
                        self._show_page(offset)
                        self._apply_selection(0)
                        return "break"
                    else:
                        self._show_page(0)
                        self._apply_selection(0)
                        return "break"
            new_idx = (self._selected_index + 1) % len(self.filtered_candidates)
            self._apply_selection(new_idx)
            return "break"
        return None

    def _on_up_key(self, event=None):
        if self.is_open() and self.filtered_candidates:
            if self._selected_index <= 0:
                source = self._get_page_source()
                if source is not None and len(source) > 0:
                    if self._page_offset > 0:
                        old_offset = self._page_offset
                        new_offset = max(0, old_offset - self.PAGE_SIZE)
                        self._show_page(new_offset)
                        prev_idx = (old_offset - 1) - new_offset
                        self._apply_selection(max(0, min(prev_idx, len(self.filtered_candidates) - 1)))
                        return "break"
                    else:
                        offset = ((len(source) - 1) // self.PAGE_SIZE) * self.PAGE_SIZE
                        self._show_page(offset)
                        self._apply_selection(len(self.filtered_candidates) - 1)
                        return "break"
                new_idx = len(self.filtered_candidates) - 1
            else:
                new_idx = self._selected_index - 1
            self._apply_selection(new_idx)
            return "break"
        return None

    def _get_page_source(self):
        if self._page_source is not None:
            return self._page_source
        if self._page_query is not None:
            self._page_source = search_candidates(self._page_query, self.all_candidates, limit=None)
            return self._page_source
        return self.all_candidates if self.all_candidates else None

    def _on_return_key(self, event=None):
        if self.is_open() and self.filtered_candidates:
            if 0 <= self._selected_index < len(self.filtered_candidates):
                choice = self.filtered_candidates[self._selected_index]
                self.select_value(choice)
                return "break"
            elif len(self.filtered_candidates) == 1:
                self.select_value(self.filtered_candidates[0])
                return "break"
            elif self.filtered_candidates:
                self.select_value(self.filtered_candidates[0])
                return "break"
        else:
            if self.all_candidates:
                self.show_click_candidates()
                return "break"
        return None

    def _on_escape_key(self, event=None):
        if self.is_open():
            if hasattr(self, "_original_query") and self._original_query:
                self._set_entry_text(self._original_query)
            self.close()
            return "break"
        return None

    def _on_tab_key(self, event=None):
        if self.is_open() and self.filtered_candidates:
            if 0 <= self._selected_index < len(self.filtered_candidates):
                choice = self.filtered_candidates[self._selected_index]
                self.select_value(choice)
            self.close()
        return None

    def _on_listbox_click(self, event):
        idx = self.listbox.nearest(event.y)
        if 0 <= idx < len(self.filtered_candidates):
            self.select_value(self.filtered_candidates[idx])
        return "break"

    def _on_listbox_motion(self, event):
        idx = self.listbox.nearest(event.y)
        if 0 <= idx < len(self.filtered_candidates) and idx != self._selected_index:
            self._selected_index = idx
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)

    def select_value(self, value):
        self._set_entry_text(value)
        if hasattr(self.parent_widget, "set"):
            self.parent_widget.set(value)
        self.close()
        if self.on_select:
            self.on_select(value)

    def _on_focus_out(self, event):
        self.parent_widget.after(150, self._check_focus_and_close)

    def _check_focus_and_close(self):
        if self.is_open():
            try:
                focused = self.parent_widget.winfo_toplevel().focus_get()
                if focused not in (self.entry, self.listbox):
                    self.close()
            except Exception:
                self.close()

    def close(self):
        self._is_visible = False
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.withdraw()
        self._selected_index = -1


def format_order_date(value):
    return f"{value.year}/{value.month}/{value.day} ({WEEKDAYS[value.weekday()]})"


def parse_typed_date(text):
    """直接入力の日付 (yyyy/mm/dd, yyyy/m/d, yyyy-mm-dd, yyyymmdd。全角・曜日付きも可) を date にする。"""
    value = unicodedata.normalize("NFKC", str(text)).strip()
    value = re.sub(r"\s*\(.*\)\s*$", "", value)
    match = (re.fullmatch(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", value)
             or re.fullmatch(r"(\d{4})(\d{2})(\d{2})", value))
    if not match:
        raise ValueError(f"日付の形式が正しくありません: {text}")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


class OrderValidationError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def collect_order(header, rows):
    """Dates use ISO, dimensions/prices use decimal strings, counts use ints."""
    result = {key: str(header.get(key, "")).strip() for key in
              ("customer_name", "ship_to", "purchase_order", "customer_code", "ship_to_code", "address")}
    result.update({key: str(header.get(key, "")) for key in ("remarks", "so_comment")})
    for key, label in (("customer_name", "顧客名"), ("ship_to", "納品先")):
        if not result[key]:
            raise OrderValidationError(key, f"{label}を入力してください。")
    for key, label in (("required_date", "Required date"), ("due_date", "Due date")):
        value = header.get(key)
        if not isinstance(value, date):
            raise OrderValidationError(key, f"{label}を選択してください。")
        result[key] = value.isoformat()
    if len(rows) > 5:
        raise OrderValidationError("items", "明細は5行まで入力できます。")
    items = []
    for row_index, row in enumerate(rows):
        item = {key: str(row.get(key, "")).strip() for key in ITEM_FIELDS}
        if not any(item.values()):
            continue
        for key, label in zip(ITEM_FIELDS, ITEM_LABELS):
            field = (row_index, key)
            if not item[key]:
                raise OrderValidationError(field, f"{row_index + 1}行目の{label}を入力してください。")
            if key == "product_name":
                continue
            try:
                number = Decimal(item[key])
            except InvalidOperation:
                raise OrderValidationError(field, f"{row_index + 1}行目の{label}を数値で入力してください。") from None
            if not number.is_finite() or number < 0 or (key != "price" and number == 0):
                condition = "0以上" if key == "price" else "0より大きい"
                raise OrderValidationError(field, f"{row_index + 1}行目の{label}は{condition}数値にしてください。")
            # Bound pathological exponents before producing a fixed-point string.
            if number.adjusted() > 20 or number.as_tuple().exponent < -10:
                raise OrderValidationError(field, f"{row_index + 1}行目の{label}の桁数を確認してください。")
            if key == "quantity":
                if number != number.to_integral_value():
                    raise OrderValidationError(field, f"{row_index + 1}行目の本数は整数にしてください。")
                item[key] = int(number)
            else:
                item[key] = format(number, "f")
        items.append(item)
    if not items:
        raise OrderValidationError((0, "product_name"), "明細を1行以上入力してください。")
    result["items"] = items
    return result


ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def clean_screen_text(text: str) -> str:
    """ターミナル画面テキストから ANSI エスケープシーケンスとヌル文字を除去"""
    if not text:
        return ""
    return ANSI_ESCAPE_PATTERN.sub("", text).replace("\x00", "")


def format_dimension_value(val) -> str:
    """長さ・幅の数値を整形 (整数の場合は小数点以下を除去、小数の場合は末尾の余分な0を除去)"""
    if val is None:
        return ""
    s = str(val).replace(",", "").strip()
    if not s:
        return ""
    try:
        d = Decimal(s)
        if d == d.to_integral_value():
            return str(int(d))
        return format(d.normalize(), "f")
    except Exception:
        return s


def format_price_value(val) -> str:
    """価格の数値を整形 (整数の場合はそのまま、小数の場合は有効桁数を維持)"""
    if val is None:
        return ""
    s = re.sub(r"[^\d.]", "", str(val).strip())
    if not s:
        return ""
    try:
        d = Decimal(s)
        if d == d.to_integral_value():
            return str(int(d))
        return format(d.normalize(), "f")
    except Exception:
        return s


def group_order_items(items: list[dict]) -> list[dict]:
    """サイドバーから渡された注文明細 (items) を QAD 99.7.1.1 の入力階層に合わせて構造化する。

    構造:
    [
        {
            "line_no": 1,
            "product_name": "OZS200",
            "price": "320.00",
            "length_groups": [
                {
                    "sl": 1,
                    "length": "600",
                    "entries": [
                        {"ser": 1, "rolls": 1, "width": "1530"},
                        {"ser": 2, "rolls": 2, "width": "1070"}
                    ]
                },
                ...
            ]
        },
        ...
    ]
    """
    if not items:
        return []

    products = []
    prod_map = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        p_name = str(item.get("product_name", "")).strip()
        if not p_name:
            continue

        raw_len = format_dimension_value(item.get("length", ""))
        raw_width = format_dimension_value(item.get("width", ""))
        try:
            qty = int(Decimal(str(item.get("quantity", 1)).strip()))
            if qty <= 0:
                qty = 1
        except Exception:
            qty = 1
        raw_price = format_price_value(item.get("price", ""))

        if p_name not in prod_map:
            prod_entry = {
                "line_no": len(products) + 1,
                "product_name": p_name,
                "price": raw_price,
                "length_groups": [],
                "_len_map": {},
            }
            prod_map[p_name] = prod_entry
            products.append(prod_entry)
        else:
            prod_entry = prod_map[p_name]
            if not prod_entry["price"] and raw_price:
                prod_entry["price"] = raw_price

        len_map = prod_entry["_len_map"]
        if raw_len not in len_map:
            lg = {
                "sl": len(prod_entry["length_groups"]) + 1,
                "length": raw_len,
                "entries": [],
                "_width_map": {},
            }
            len_map[raw_len] = lg
            prod_entry["length_groups"].append(lg)
        else:
            lg = len_map[raw_len]

        w_map = lg["_width_map"]
        if raw_width in w_map:
            w_map[raw_width]["rolls"] += qty
        else:
            entry = {
                "ser": len(lg["entries"]) + 1,
                "rolls": qty,
                "width": raw_width,
            }
            w_map[raw_width] = entry
            lg["entries"].append(entry)

    for p in products:
        p.pop("_len_map", None)
        for lg in p["length_groups"]:
            lg.pop("_width_map", None)

    return products


def build_order_header_fields(payload):
    """実送信とF3表示で同じ8項目・空スキップ・日付変換を使用する。"""
    def qad_date(value):
        if not value:
            return ""
        try:
            return date.fromisoformat(str(value)).strftime("%m/%d/%y")
        except ValueError:
            return str(value)

    return [
        date.today().strftime("%m/%d/%y"),
        qad_date(payload.get("required_date", "")), "",
        qad_date(payload.get("due_date", "")), "", "",
        str(payload.get("purchase_order", "")).strip(),
        str(payload.get("remarks", "")).strip(),
    ]


def is_space_prompt(clean_lower_text: str) -> bool:
    """明示的な Space 要求プロンプト（Press space bar to continue 等）が存在するか判定する。
    単なる 'category=' 等の文字列単体では Space 要求と判定しない。
    """
    if not clean_lower_text:
        return False
    return (
        "press space" in clean_lower_text
        or "space bar" in clean_lower_text
        or "spacebar" in clean_lower_text
        or "space to continue" in clean_lower_text
    )


def is_order_completed(clean_lower_text: str) -> bool:
    """QAD 99.7.1.1 の注文確定後の完了・復帰画面（メインメニューまたはHOME画面）を判定する。
    HOME画面（空の受注入力初期画面: Order空欄、Sold-To、Bill To等のヘッダー表示）も含めて検知する。
    """
    if not clean_lower_text:
        return False
    txt = clean_lower_text.lower()
    if "mfmenu" in txt or "main menu" in txt:
        return True
    # HOME画面 (受注入力初期画面: Order空欄、Sold-To、Order Date等)
    # または "sales order maintenance" タイトル付きの初期画面
    if "order:" in txt and ("sold-to" in txt or "sold to" in txt):
        if ("order date:" in txt or "bill to:" in txt or "purchase order:" in txt or "sales order maintenance" in txt):
            if "line total:" not in txt and "total tax:" not in txt and "sales order line" not in txt:
                return True
    return False


_ACTIVE_SLEEP_RATE_PERCENT: float = 100.0


def get_active_sleep_rate_percent() -> float:
    """現在の受注自動化スリープ倍率（1〜200%）を取得"""
    return _ACTIVE_SLEEP_RATE_PERCENT


def set_active_sleep_rate_percent(val: float | int) -> float:
    """現在の受注自動化スリープ倍率（1〜200%）を設定"""
    global _ACTIVE_SLEEP_RATE_PERCENT
    try:
        val_f = float(val)
        _ACTIVE_SLEEP_RATE_PERCENT = max(1.0, min(200.0, val_f))
    except (ValueError, TypeError):
        _ACTIVE_SLEEP_RATE_PERCENT = 100.0
    return _ACTIVE_SLEEP_RATE_PERCENT


class SalesOrderAutomationController:
    """QAD 99.7.1.1 (Sales Order Maintenance) の同期式・画面検知型自動入力コントローラ。
    画面のプロンプト・ポップアップ・表示変化を待機して、正確なタイミングでキーストロークを送信します。
    """

    is_space_prompt = staticmethod(is_space_prompt)
    is_order_completed = staticmethod(is_order_completed)

    def __init__(
        self,
        session,
        get_screen_text,
        payload,
        status_callback=None,
        logger=None,
        sleep_func=time.sleep,
        default_timeout: float = 12.0,
        sleep_rate_percent: float | None = None,
    ):
        self.session = session
        self.get_screen_text = get_screen_text
        self.payload = payload or {}
        self.status_callback = status_callback
        self.logger = logger
        self._raw_sleep = sleep_func
        self.default_timeout = default_timeout
        self.aborted = False
        self.order_id: str | None = None

        # 1〜200% のSleep倍率（指定がなければ payload またはグローバル設定から取得、デフォルト 100%）
        if sleep_rate_percent is not None:
            rate = float(sleep_rate_percent)
        elif "sleep_rate_percent" in self.payload:
            rate = float(self.payload["sleep_rate_percent"])
        else:
            rate = get_active_sleep_rate_percent()
        self.sleep_rate_percent = max(1.0, min(200.0, rate))

    # サーバー応答待ち: 応答（受信）の開始を待つ上限と、描画が落ち着いたとみなす無受信時間
    RESPONSE_WINDOW = 3.0
    SETTLE_QUIET = 0.08
    SETTLE_POLL = 0.01

    def _effective_rate(self, critical: bool = False) -> float:
        # 設計書2.10: 画面・モード切替の待機は速度設定を下げても基準(100%)未満にしない
        return max(100.0, self.sleep_rate_percent) if critical else self.sleep_rate_percent

    def sleep(self, seconds: float, critical: bool = False):
        """設定されたパーセンテージ（1%〜200%）に応じてスリープ時間をスケーリングして実行"""
        scaled = max(0.001, seconds * (self._effective_rate(critical) / 100.0))
        self._raw_sleep(scaled)

    def _output_generation(self):
        """受信データの通番。対応していないセッション（単体テストのモック等）では None"""
        gen = getattr(self.session, "output_generation", None)
        return gen if isinstance(gen, int) else None

    def _check_alive(self):
        stop_event = getattr(self.session, "stop_event", None)
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("ターミナルセッションが切断・終了されました")
        if self.aborted:
            raise InterruptedError("自動入力がユーザーによって中止されました")

    def send_and_settle(self, data: str, min_wait: float, desc: str = "", critical: bool = False):
        """キーを送信し、サーバーの画面応答が届いて描画が落ち着くまで待つ。

        従来の固定待機 (min_wait × 速度設定) は下限として維持するため、従来より早く次のキーを送らない。
        応答が遅い場合は届くまで待つ（上限 RESPONSE_WINDOW 秒）。応答がない場合は従来どおり続行し、ログに残す。
        """
        gen0 = self._output_generation()
        self.send(data)
        if gen0 is None:
            self.sleep(min_wait, critical=critical)
            return True

        floor = max(0.0, min_wait * self._effective_rate(critical) / 100.0)
        start = time.monotonic()
        last_gen = gen0
        last_change = start
        responded = False
        while True:
            self._check_alive()
            now = time.monotonic()
            gen = self._output_generation()
            if gen != last_gen:
                responded = True
                last_gen = gen
                last_change = now
            elapsed = now - start
            if responded:
                if now - last_change >= self.SETTLE_QUIET and elapsed >= floor:
                    return True
                if elapsed >= self.RESPONSE_WINDOW + self.default_timeout:
                    # 時計表示などで受信が止まらない場合も、待ち続けずに後続の画面判定へ進む
                    return True
            elif elapsed >= max(self.RESPONSE_WINDOW, floor):
                self.log(f"注意: {self.RESPONSE_WINDOW}秒以内に画面応答がありません ({desc or repr(data)})")
                return False
            self._raw_sleep(self.SETTLE_POLL)

    def _has_valid_order_id(self, txt: str) -> bool:
        """画面上に有効な Order ID が採番・表示されているかを判定"""
        m = re.search(r"(?:order|sales order):\s*([a-z0-9]+)", txt, re.IGNORECASE)
        if m:
            val = m.group(1).strip().lower()
            return val not in ("sold", "sold-to", "to", "")
        return False

    def _extract_order_id(self) -> str | None:
        """画面バッファから最新の Order ID (例: SO199402) を抽出して保持"""
        try:
            txt = clean_screen_text(self.get_screen_text())
            m = re.search(r"(?:Order|Sales Order):\s*([A-Za-z0-9]+)", txt, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                if extracted and extracted.lower() not in ("sold", "sold-to", "to") and extracted != self.order_id:
                    self.order_id = extracted
                    self.log(f"Order ID を記録: {self.order_id}")
        except Exception:
            pass
        return self.order_id

    def get_cursor_pos(self) -> tuple[int, int]:
        """現在の仮想端末カーソル座標 (y, x) を安全に取得（0-indexed）。取得不可時は (-1, -1)"""
        try:
            sess = getattr(self, "session", None)
            if sess and hasattr(sess, "screen") and hasattr(sess.screen, "cursor"):
                c = sess.screen.cursor
                return (c.y, c.x)
        except Exception:
            pass
        return (-1, -1)

    def log(self, msg: str):
        if self.logger:
            try:
                self.logger(msg)
            except Exception:
                pass

    def set_status(self, msg: str, status_type: str = "working", clear_delay=None):
        if self.status_callback:
            try:
                try:
                    self.status_callback(msg, status_type, clear_delay=clear_delay)
                except TypeError:
                    try:
                        self.status_callback(msg, status_type, clear_delay)
                    except TypeError:
                        self.status_callback(msg, status_type)
            except Exception:
                pass

    def abort(self):
        self.aborted = True

    def send(self, data: str):
        if self.aborted:
            raise InterruptedError("自動入力がユーザーによって中止されました")
        self.session.send(data)

    def wait_for_screen(self, predicate, timeout: float = None, poll_interval: float = 0.05, desc: str = ""):
        """指定した条件 (predicate(clean_lower_text)) を満たすまで待機する。
        途中、'Press space bar to continue' 等のアクティブな警告・プロンプトが出現した場合は
        最優先で検知し、同一警告に対して重複送信しないよう制御しつつ Space を送信して対処する。
        """
        to = timeout if timeout is not None else self.default_timeout
        start_t = time.monotonic()
        last_handled_warning_sig = None

        while time.monotonic() - start_t < to:
            if getattr(self.session, "stop_event", None) and self.session.stop_event.is_set():
                raise InterruptedError("ターミナルセッションが切断・終了されました")
            if self.aborted:
                raise InterruptedError("自動入力がユーザーによって中止されました")

            raw_txt = self.get_screen_text()
            clean_txt = clean_screen_text(raw_txt).lower()

            # B2: 背景ラベル検知よりも手前のアクティブな警告・Space要求プロンプト検知を最優先する
            # B3: 単なる category= 文字列ではなく、明示的な入力要求プロンプトが伴う場合のみ Space 送信
            if is_space_prompt(clean_txt):
                # 警告行（警告理由・プロンプト文面）のシグネチャを抽出して背景描画揺れや時計更新による誤重複送信を抑止
                warning_lines = [
                    l.strip()
                    for l in clean_txt.splitlines()
                    if is_space_prompt(l) or any(k in l for k in ("warning", "order on hold", "hold:", "category="))
                ]
                warning_sig = tuple(warning_lines) if warning_lines else (clean_txt,)

                # C3: Space送信後、警告が消えるまでの遅延中に同一警告要求へ Space を重複送信しない
                # C4: 警告内容が変化した場合は新たな警告としてSpace送信
                if warning_sig != last_handled_warning_sig:
                    self.log(f"画面待機中 ({desc}): アクティブな警告/Space要求プロンプトを検知。Spaceキーを送信します。")
                    self.send(" ")
                    last_handled_warning_sig = warning_sig
                self.sleep(poll_interval)
                continue

            # 警告プロンプトが画面から消去された場合はハンドラ履歴をリセット
            last_handled_warning_sig = None

            if predicate(clean_txt):
                return clean_txt

            self.sleep(poll_interval)

        curr = clean_screen_text(self.get_screen_text())
        raise TimeoutError(f"画面遷移待機タイムアウト ({to}秒): {desc}\n現在の画面表示:\n{curr}")

    STABLE_QUIET = 0.4

    def wait_for_stable_screen(self, predicate, quiet: float = None, timeout: float = None,
                               poll_interval: float = 0.05, desc: str = ""):
        """predicate を満たし、かつ quiet 秒間画面が変化しない状態まで待つ。

        背景に常駐する見出し（Bill To / Sales Order Line 等）だけで条件が成立し、
        直後に描画される警告やポップアップ（Category警告、Reason Code等）より先に
        次のキーを送ってしまうことを防ぐ。待機中に出た警告は wait_for_screen が Space で解除する。
        """
        quiet = self.STABLE_QUIET if quiet is None else quiet
        to = timeout if timeout is not None else self.default_timeout
        start = time.monotonic()
        last_sig = None
        stable_since = start
        while True:
            remaining = to - (time.monotonic() - start)
            if remaining <= 0:
                curr = clean_screen_text(self.get_screen_text())
                raise TimeoutError(f"画面安定待機タイムアウト ({to}秒): {desc}\n現在の画面表示:\n{curr}")
            txt = self.wait_for_screen(predicate, timeout=remaining, poll_interval=poll_interval, desc=desc)
            now = time.monotonic()
            sig = (self._output_generation(), txt)
            if sig != last_sig:
                last_sig = sig
                stable_since = now
            elif now - stable_since >= quiet:
                return txt
            self._raw_sleep(poll_interval)

    def execute_step6(self, items: list[dict] = None):
        """Step 6.1.0 〜 Step 6.3.0: 明細登録および最終完了までの自動入力"""
        target_items = items if items is not None else self.payload.get("items", [])
        grouped = group_order_items(target_items)
        if not grouped:
            self.log("明細項目が空です。Step 6 の入力を終了します。")
            return

        self.set_status(f"Step 6: 受注明細行入力開始 (全 {len(grouped)} 品番 / {len(target_items)} 明細)", "working")
        self.log(f"=== Step 6 受注明細行入力開始 (全 {len(grouped)} 品番) ===")

        for p_idx, prod in enumerate(grouped, 1):
            p_name = prod["product_name"]
            price_val = prod["price"]
            l_groups = prod["length_groups"]

            self.set_status(f"Step 6 ({p_idx}/{len(grouped)}): 品番 '{p_name}' 入力中...", "working")
            self.log(f"--- [Line {prod['line_no']}] 品番: {p_name} / 単価: {price_val} / 長さグループ: {len(l_groups)}件 ---")

            # 6.1.0 Ln 自動採番
            # 1品目目、または画面に Create WO が出現していない場合のみ Enter で Ln 採番
            # （2品目目以降で、前行の完了直後にすでに画面に Create WO が出ている場合は Enter は不要）
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "create wo:" not in curr_txt and "rework:" not in curr_txt:
                self.wait_for_screen(
                    lambda txt: ("sales order line" in txt or "ln item number" in txt or "create wo:" in txt or "rework:" in txt) and "transaction comments" not in txt,
                    desc=f"6.1.0 Ln入力欄 (Line {prod['line_no']})"
                )
                curr_txt = clean_screen_text(self.get_screen_text()).lower()
                if "create wo:" not in curr_txt and "rework:" not in curr_txt:
                    self.log(f"6.1.0: Enter 送信 (Line {prod['line_no']} 自動採番)")
                    self.send_and_settle("\r", 0.4, critical=True)

            # 6.1.1 MFG/PRO 応答同期: Create WO ポップアップ（または明細行展開）の出現を確実に待機
            # 【重要】静的ヘッダー（'item number'）単体での判定はすり抜けの原因となるため行わない
            def _is_post_ln_ready(txt: str) -> bool:
                if "create wo:" in txt or "rework:" in txt:
                    return True
                if "5=delete" in txt or "5=del" in txt:
                    return True
                return False

            self.wait_for_screen(
                _is_post_ln_ready,
                desc=f"6.1.1 MFG/PRO応答待機 (Line {prod['line_no']} Create WO または 明細行展開)"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "create wo:" in curr_txt or "rework:" in curr_txt:
                self.log(f"6.1.1: F1 送信 (Line {prod['line_no']} Create WO ポップアップ解除)")
                self.send_and_settle(KEY_SEQUENCES["F1"], 0)
                # 【重要】F1 送信後、MFG/PRO がポップアップを閉じて Item Number 欄へ遷移したこと（Create WO 消滅）を確実に待機
                self.wait_for_screen(
                    lambda txt: "create wo:" not in txt and "rework:" not in txt,
                    desc=f"6.1.1 Create WO ポップアップ消滅待ち (Line {prod['line_no']})"
                )
                self.sleep(0.25, critical=True)

            # 6.1.3 Item Number 入力
            self.wait_for_screen(
                lambda txt: "create wo:" not in txt and ("sales order line" in txt or "item number" in txt or "5=delete" in txt),
                desc=f"6.1.3 Item Number 入力欄 (Line {prod['line_no']})"
            )
            self.log(f"6.1.3: 品番 '{p_name}' 送信")
            self.send(f"{p_name}")
            self.sleep(0.2)
            self.log(f"6.1.3: F1 送信 (品番確定)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.25)

            # 6.1.3 Site ポップアップ入力（ハイブリッド・スマートウェイト）
            # 【重要】画面下部の固定枠 "Loc: Site: CB2" に誤爆しないよう、
            # "Loc:" と共存しない行に "Site" が出現したこと（上部ポップアップ枠やモック画面）を判定
            site_val = str(self.payload.get("site", "CB2") or "CB2").strip()

            def _is_site_popup_ready(txt: str) -> bool:
                has_active_site = False
                for line in txt.splitlines():
                    line_l = line.lower()
                    if "loc:" in line_l and "site" in line_l:
                        continue
                    if "site" in line_l:
                        has_active_site = True
                        break

                has_popup_frame = bool(
                    re.search(r"[|│]\s*site\s*[|│]", txt, re.IGNORECASE)
                    or re.search(r"numbe[|│]\s*site", txt, re.IGNORECASE)
                    or "site     │" in txt
                    or "site     |" in txt
                )
                cy, cx = self.get_cursor_pos()
                cursor_ok = (cx >= 15) if cx >= 0 else True
                return (has_active_site or has_popup_frame) and cursor_ok

            self.wait_for_screen(_is_site_popup_ready, desc=f"6.1.3 Site ポップアップ (品番 '{p_name}' 確定後)")
            self.log(f"6.1.3: Site '{site_val}' + F1 送信")
            self.send(site_val)
            self.sleep(0.15)
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.2)

            # 6.1.4 Qty Ordered UM スキップ
            self.wait_for_screen(
                lambda txt: not (re.search(r"[|│]\s*site\s*[|│]", txt) or re.search(r"item\s*numbe.*site", txt)) and
                            ("avail. to allocate" in txt or "on hand:" in txt or "item width(mm):" in txt or "total qty (m2)" in txt or "qty ordered um" in txt),
                desc="6.1.4 Qty Ordered UM または スリット設定画面"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "sl run" not in curr_txt and "cum width" not in curr_txt and "total qty (m2)" not in curr_txt and "item width(mm):" not in curr_txt:
                self.log("6.1.4: F1 送信 (Qty Ordered UM スキップ)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.15)

            # 6.1.4 No1 スリット設定画面 (SL一覧)
            self.wait_for_screen(
                lambda txt: "sl run" in txt or "cum width" in txt or "total qty (m2)" in txt or "item width(mm):" in txt,
                desc="6.1.4 No1 スリット設定画面"
            )

            # 長さ・幅・本数 (スリット設定ループ)
            for l_idx, lg in enumerate(l_groups, 1):
                len_val = lg["length"]
                sl_no = lg["sl"]
                entries = lg["entries"]
                self.log(f"  SL {sl_no}: 長さ '{len_val}'m (明細 {len(entries)}件) 開始")

                # F1 を押して SL 取得 ➔ Enter ➔ Enter で Run を初期値のままスキップして Len(m) 欄へ移動
                self.log(f"  SL {sl_no}: F1 -> Enter -> Enter で Len(m) 欄へ移動")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.15)
                self.send("\r")
                self.sleep(0.12)
                self.send("\r")
                self.sleep(0.15)

                # 6.2.0 Len(m) 長さ入力 (長さ + Enter)
                self.log(f"  6.2.0: 長さ '{len_val}' + Enter 送信")
                self.send(f"{len_val}\r")
                self.sleep(0.2)

                # 6.2.1 ロール明細ポップアップ (Ser T Rolls Width)
                self.wait_for_screen(
                    lambda txt: "rolls width(mm)" in txt or "ser t" in txt or "tot qty(m2)" in txt,
                    desc=f"6.2.1 ロール明細ポップアップ (SL {sl_no})"
                )

                for r_idx, ent in enumerate(entries, 1):
                    r_rolls = ent["rolls"]
                    r_width = ent["width"]
                    self.log(f"    Roll {r_idx}/{len(entries)}: 本数={r_rolls}, 幅={r_width}mm")

                    # Ser スキップ (Enter)
                    self.send("\r")
                    self.sleep(0.12)

                    # Rolls 入力 (本数 + Enter)
                    self.send(f"{r_rolls}\r")
                    self.sleep(0.12)

                    # Width 入力 (幅 + Enter)
                    self.send(f"{r_width}\r")
                    self.sleep(0.15)

                # 当該長さのロール入力完了 -> F4 -> Please confirm update -> F1
                self.log(f"  6.2.1: F4 送信 (長さ '{len_val}'m ロール入力完了)")
                self.send(KEY_SEQUENCES["F4"])
                self.sleep(0.18)

                curr_txt = clean_screen_text(self.get_screen_text()).lower()
                if "confirm update" in curr_txt:
                    self.log("  6.2.1: F1 送信 ('yes' 確定)")
                    self.send(KEY_SEQUENCES["F1"])
                    self.sleep(0.18)
                else:
                    self.wait_for_screen(
                        lambda txt: "please confirm update" in txt,
                        desc=f"6.2.1 Please confirm update プロンプト (SL {sl_no})"
                    )
                    self.log("  6.2.1: F1 送信 ('yes' 確定)")
                    self.send(KEY_SEQUENCES["F1"])
                    self.sleep(0.18)

                # SL一覧画面へ復帰確認 (ロールポップアップを抜けてSL一覧へ戻ったことを検知)
                self.wait_for_screen(
                    lambda txt: ("sl run" in txt or "cum width" in txt or "len(m)" in txt or "item width(mm):" in txt) and "confirm update" not in txt,
                    desc=f"6.1.4 No1 SL一覧復帰 (SL {sl_no})"
                )

            # 当該品番の全長さ入力完了 -> SL一覧画面で F4 -> Please confirm update -> F1
            self.log(f"6.1.4: F4 送信 (品番 '{p_name}' 全スリット設定完了)")
            self.send(KEY_SEQUENCES["F4"])
            self.sleep(0.18)

            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "confirm update" in curr_txt:
                self.log("6.1.4: F1 送信 ('yes' 確定)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)
            else:
                self.wait_for_screen(
                    lambda txt: "please confirm update" in txt,
                    desc=f"6.1.4 全明細 Please confirm update プロンプト (品番 '{p_name}')"
                )
                self.log("6.1.4: F1 送信 ('yes' 確定)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)

            # 6.2.2 ATP Enforcement WARNING / 6.2.3 Orig Order Qty / Pricing Date 画面待機
            self.wait_for_screen(
                lambda txt: "atp enforcement" in txt or "orig order qty:" in txt or "pricing date:" in txt,
                desc="6.2.2 ATP警告 または 6.2.3 Orig Qty / Pricing Date 画面"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "atp enforcement" in curr_txt:
                self.log("6.2.2: ATP Enforcement WARNING 検知 -> F1 送信で承諾・スキップ")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)
                # ATPスキップ後、次画面（Orig Order Qty または Pricing Date）の出現を待機
                self.wait_for_screen(
                    lambda txt: "orig order qty:" in txt or "pricing date:" in txt,
                    desc="6.2.2 ATPスキップ後の次画面 (Orig Qty または Pricing Date)"
                )
                curr_txt = clean_screen_text(self.get_screen_text()).lower()

            if "orig order qty:" in curr_txt:
                self.log("6.2.3: Orig Order Qty スキップ (F1)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)

            # 6.2.3 Pricing Date 画面スキップ
            self.wait_for_screen(
                lambda txt: "pricing date:" in txt and "sales order line" in txt,
                desc="6.2.3 Pricing Date 画面"
            )
            self.log("6.2.3: F1 送信 (Pricing Date スキップ)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.18)

            # 6.2.4 値段入力画面 (List Price スキップ -> Price に単価入力)
            self.wait_for_screen(
                lambda txt: ("list price" in txt or "sales order line" in txt) and "reprice:" not in txt and "orig order qty:" not in txt and "sl run" not in txt and "tax usage:" not in txt,
                desc="6.2.4 値段入力画面"
            )
            self.log("6.2.4: F1 送信 (List Price スキップ)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.15)

            self.log(f"6.2.4: 単価 '{price_val}' + F1 送信 (単価確定)")
            self.send(f"{price_val}")
            self.sleep(0.12)
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.22)

            # 6.2.4-Detail: 明細詳細枠 (Loc: / Sales Acct:) または後続画面の待機
            # 実機では単価確定後に画面中下段の詳細枠 (Desc: / Loc: / Sales Acct: 等) が展開され、
            # カーソルが Loc: に着地するため F1 送信でスキップ・確定する
            self.wait_for_screen(
                lambda txt: (("sales acct:" in txt and "disc acct:" in txt) or "jpy cost:" in txt or ("loc:" in txt and "sales acct:" in txt)) or
                            "tax usage:" in txt or "tax environment:" in txt or "tax class:" in txt or
                            "transaction comments" in txt or "master reference:" in txt or
                            "reason code" in txt or "create wo:" in txt or "rework:" in txt,
                desc="6.2.4 単価確定後 (詳細枠 Loc: または次画面待機)"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if ("sales acct:" in curr_txt and "disc acct:" in curr_txt) or "jpy cost:" in curr_txt or ("loc:" in curr_txt and "sales acct:" in curr_txt):
                self.log("6.2.4: 明細詳細枠 (Loc: / Sales Acct:) 検知 -> F1 送信でスキップ")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)
                # 詳細枠が閉じる（または次画面へ遷移する）のを待機
                self.wait_for_screen(
                    lambda txt: "tax usage:" in txt or "tax environment:" in txt or "tax class:" in txt or
                                "transaction comments" in txt or "master reference:" in txt or
                                "reason code" in txt or "create wo:" in txt or "rework:" in txt,
                    desc="6.2.4 詳細枠スキップ確定待ち"
                )

            # 6.2.5 Tax 画面スキップ (Tax ポップアップまたは後続画面待機)
            self.wait_for_screen(
                lambda txt: (
                    ("tax usage:" in txt or "tax environment:" in txt or "tax class:" in txt)
                    or "transaction comments" in txt
                    or "master reference:" in txt
                    or "reason code" in txt
                    or "create wo:" in txt
                    or "rework:" in txt
                    or ("sales order line" in txt and "list price" not in txt)
                ),
                desc="6.2.5 Tax ポップアップ または 次画面"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if ("tax usage:" in curr_txt or "tax environment:" in curr_txt or "tax class:" in curr_txt) and "transaction comments" not in curr_txt:
                self.log("6.2.5: F1 送信 (Tax スキップ)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.18)

            # 6.2.5 Transaction Comments 画面スキップ (背景の誤検知を防ぎ確実にコメントまたは理由コードを待機)
            self.wait_for_screen(
                lambda txt: (
                    "transaction comments" in txt
                    or "master reference:" in txt
                    or "reason code" in txt
                    or "create wo:" in txt
                    or "rework:" in txt
                    or ("sales order line" in txt and "list price" not in txt)
                ),
                desc="6.2.5 Transaction Comments または 次画面"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "transaction comments" in curr_txt or "master reference:" in curr_txt:
                self.log("6.2.5: F4 送信 (明細行 Transaction Comments 終了 -> Reason Code または 次画面へ)")
                self.send(KEY_SEQUENCES["F4"])
                self.sleep(0.22)

            # 6.2.5-Rsn: Reason Code ポップアップまたは メイン明細画面 (Sales Order Line / Ln Item Number / Create WO) の出現を待機
            # 【重要】Sales Order Line は背景に常駐するため、描画が落ち着くまで待ってから判定する
            # （F4直後の一瞬で「明細一覧に復帰」と誤判定し、後から出る Reason Code 欄に次行の Enter が入るのを防ぐ）
            self.wait_for_stable_screen(
                lambda txt: (
                    "reason code" in txt
                    or "create wo:" in txt
                    or "rework:" in txt
                    or (("sales order line" in txt or "ln item number" in txt) and "transaction comments" not in txt)
                ),
                desc="6.2.5 Reason Code または Sales Order Line 復帰"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "reason code" in curr_txt:
                self.log("6.2.5: Reason Code 検知 (65 -> 28 INTERNAL -> 28 INTERNAL + F1)")
                self.send("65\r")
                self.sleep(0.12)
                self.send("28\r")
                self.sleep(0.12)
                self.send("28\r")
                self.sleep(0.12)
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.22)

            # 6.1.0 メイン明細一覧 (Sales Order Line 空のLn または 次行 Create WO) への復帰待機
            self.wait_for_stable_screen(
                lambda txt: ("sales order line" in txt or "ln item number" in txt or "create wo:" in txt or "rework:" in txt)
                            and "transaction comments" not in txt and "reason code" not in txt,
                desc="6.1.0 メイン明細一覧復帰"
            )

        # -------------------------------------------------------------
        # 6.3.0 最終画面遷移＆注文完了
        # -------------------------------------------------------------
        self.set_status("Step 6.3.0: 最終合計画面へ遷移中...", "working")
        curr_txt = clean_screen_text(self.get_screen_text()).lower()
        if "create wo:" in curr_txt or "rework:" in curr_txt:
            self.log("6.3.0: 次行 Create WO 解除 (F1)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.15)

        self.log("6.3.0: F4 を送信して最終合計画面へ進みます")
        for attempt in range(6):
            curr_txt = clean_screen_text(self.get_screen_text()).lower()
            if "line total:" in curr_txt or "total tax:" in curr_txt or "enter data or press f4" in curr_txt:
                break
            if "create wo:" in curr_txt or "rework:" in curr_txt:
                self.log("6.3.0: 次行 Create WO 解除 (F1)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.15)
                continue
            self.send(KEY_SEQUENCES["F4"])
            self.sleep(0.18)

        self.wait_for_screen(
            lambda txt: "line total:" in txt or "total tax:" in txt or "enter data or press f4" in txt,
            desc="6.3.0 最終合計画面"
        )
        self.log("6.3.0: 最終合計画面の表示を確認しました")
        self._extract_order_id()

        # ユーザー実機検証仕様: F1 x 2回 (警告時は1回) ＋ 必要に応じて Space で注文確定・完了
        self.set_status("Step 6.3.0: 注文確定処理中...", "working")
        self.log("6.3.0: 1回目の F1 送信 (下段フレームへ移動)")
        self.send_and_settle(KEY_SEQUENCES["F1"], 0.3, critical=True)

        curr_txt = clean_screen_text(self.get_screen_text()).lower()
        is_completed = self.is_order_completed

        # C1: Totals画面で1回目のF1送信直後に警告が出現した場合、2回目のF1を送信せず直ちにSpace送信へ分岐する
        if is_space_prompt(curr_txt):
            self.log("6.3.0: 1回目の F1 送信直後に警告/Space要求を検知。2回目 F1 をスキップします。")
        elif not is_completed(curr_txt):
            # C2: 2回目F1送信で警告が出ずにメインメニュー等へ復帰した場合、不要なSpaceを送らず即時正常終了とする
            self.log(f"6.3.0: 2回目の {ORDER_TOTALS_COMMIT_KEY} 送信 (注文データ確定・コミット)")
            self.send_and_settle(KEY_SEQUENCES[ORDER_TOTALS_COMMIT_KEY], 0.3, critical=True)

        # メインメニュー (mfmenu) または初期画面 (HOME画面) 復帰確認（警告があれば自動で Space 送信して解除）
        # C2: 警告が出ずに完了画面へ復帰した場合は不要な Space を送らず即時正常終了
        self.wait_for_screen(
            is_completed,
            desc="受注完了・初期画面復帰"
        )
        self._extract_order_id()
        self.set_status("✅ QAD 99.7.1.1 受注登録が全工程正常に完了しました！", "success", clear_delay=8)
        self.log(f"=== QAD 99.7.1.1 受注入力自動化 全工程完了 (Order ID: {self.order_id or '完了'}) ===")
        return self.order_id

    HEADER_CODES_RE = re.compile(
        r"sold-to:[ \t]*(\S+)[ \t]+bill[ -]to:[ \t]*(\S+)[ \t]+ship-to:[ \t]*(\S+)", re.IGNORECASE)

    @staticmethod
    def _header_field_at_cursor(text, cursor):
        """Identify the input region on the header row; labels alone are insufficient."""
        y, x = cursor
        lines = text.lower().splitlines()
        if not 0 <= y < len(lines):
            return None
        row = lines[y]
        if "sold-to:" in row and re.search(r"bill[ -]to:", row) and "ship-to:" in row:
            labels = list(re.finditer(r"sold-to:|bill[ -]to:|ship-to:", row))
            for index, label in enumerate(labels):
                right = labels[index + 1].start() if index + 1 < len(labels) else len(row)
                if label.end() <= x < right:
                    return ("sold", "bill", "ship")[index]
        match = re.search(r"order date:", row)
        if match and match.end() <= x < match.end() + 12:
            return "date"
        match = re.search(r"remarks:", row)
        if match:
            end = row.find("entered by:", match.end())
            if match.end() <= x < (end if end >= 0 else len(row)):
                return "remarks"
        return None

    @staticmethod
    def _header_values_match(text, fields):
        """Verify the visible edited values before allowing header confirmation."""
        regions = (
            ("order date:", "line pricing:", fields[0]),
            ("required date:", "manual:", fields[1]),
            ("due date:", "channel:", fields[3]),
            ("purchase order:", "reprice:", fields[6]),
            ("remarks:", "entered by:", fields[7]),
        )
        lines = text.splitlines()
        for label, next_label, expected in regions:
            row = next((row for row in lines if label in row.lower()), None)
            if row is None:
                return False
            lower = row.lower()
            start = lower.index(label) + len(label)
            end = lower.find(next_label, start)
            if end < 0:
                return False
            if row[start:end].strip() != expected:
                return False
        return True

    def _wait_header_field(self, expected, confirm_sold=False, after_generation=None, values=None):
        snapshot = getattr(self.session, "automation_snapshot", None)
        if not callable(snapshot):
            raise RuntimeError("入力先を確認できる端末スナップショットがありません。送信を停止しました。")
        last = None
        since = time.monotonic()
        confirmed = False

        def ready(_):
            nonlocal last, since, confirmed
            text, cursor, generation = snapshot()
            lower = text.lower()
            if re.search(r"(?:^|\n)\s*error:", lower):
                raise RuntimeError(f"ヘッダー入力中にQADエラーを検知しました (待機先={expected}, cursor={cursor})\n{text}")
            if is_space_prompt(lower):
                return False
            if after_generation is not None and generation <= after_generation:
                return False
            field = self._header_field_at_cursor(text, cursor)
            values_ready = values is None or self._header_values_match(text, values)
            state = (field, cursor, generation, values_ready)
            now = time.monotonic()
            if state != last:
                self.log(f"Step 2 入力先確認: expected={expected} actual={field or 'UNKNOWN'} cursor={cursor} rx={generation} values_ready={values_ready}")
                last, since = state, now
                return False
            # F1はSold-Toに留まる場合に一度だけ。Bill-Toへ移動済みなら送らない。
            if confirm_sold and not confirmed and field == "sold" and now - since >= 0.4:
                self.log("Step 2: Sold-To欄への滞留を検知、F1を一度送信")
                self.send(KEY_SEQUENCES["F1"])
                confirmed = True
                last = None
                return False
            return field == expected and values_ready and now - since >= self.SETTLE_QUIET

        return self.wait_for_screen(ready, desc=f"Step 2: 入力先 {expected} 確認")

    def _verify_header_codes(self, c_code: str, s_code: str):
        """Do not paste dates when the three displayed codes cannot be verified."""
        txt = self.get_screen_text()
        match = self.HEADER_CODES_RE.search(txt)
        actual = tuple(value.lower() for value in match.groups()) if match else None
        expected = (c_code.lower(), c_code.lower(), s_code.lower())
        if actual != expected:
            raise RuntimeError(
                "ヘッダーの顧客コードを確認できないため停止しました "
                f"(Sold-To/Bill To/Ship-To: 期待={expected} 画面={actual})\n現在の画面表示:\n{txt}"
            )

    def execute_full_order(self):
        """メインメニュー (mfmenu) またはヘッダー画面から全工程 (Step 1 〜 Step 6.3.0) を実行"""
        self.log("=== QAD 99.7.1.1 受注入力自動化 全工程実行開始 ===")
        curr_txt = clean_screen_text(self.get_screen_text()).lower()

        # Step 1: 99.7.1.1 画面への遷移および Order番号新規自動採番 (F1)
        # ケース A: メインメニューにいる場合は 99.7.1.1 を送信して受注画面を開く
        if "mfmenu" in curr_txt or "main menu" in curr_txt:
            self.set_status("Step 1: 99.7.1.1 受注登録画面へ移動中...", "working")
            self.log("Step 1: '99.7.1.1\\r' 送信")
            self.send("99.7.1.1\r")
            self.wait_for_screen(
                lambda txt: "order:" in txt and "sales order maintenance" in txt,
                desc="Step 1: 99.7.1.1 Order入力画面"
            )
            curr_txt = clean_screen_text(self.get_screen_text()).lower()

        # ケース B: 99.7.1.1 の Order: 欄にいる（未採番）場合、空欄のまま F1 を押して自動採番
        if not self._has_valid_order_id(curr_txt) and ("order:" in curr_txt or "sales order maintenance" in curr_txt):
            self.set_status("Step 1: Order番号自動採番中 (F1 送信)...", "working")
            self.log("Step 1: Order番号自動採番 (空欄で F1 送信)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.15)
            # Step 2: Order ID が採番され、Sold-To 欄へ着地したことを確実に検知
            self.wait_for_screen(
                lambda txt: self._has_valid_order_id(txt) and "sold-to" in txt,
                desc="Step 2: 受注ヘッダー画面 (Sold-To 入力待ち)"
            )
        elif not (self._has_valid_order_id(curr_txt) and "sold-to" in curr_txt):
            self.wait_for_screen(
                lambda txt: self._has_valid_order_id(txt) and "sold-to" in txt,
                desc="Step 2: 受注ヘッダー画面 (Sold-To 入力待ち)"
            )
        self._extract_order_id()
        self.set_status("Step 2: 受注ヘッダー項目入力中...", "working")

        c_code = str(self.payload.get("customer_code", "")).strip()
        s_code = str(self.payload.get("ship_to_code", "")).strip()

        if not c_code or not s_code:
            raise ValueError("顧客コードと納品先コードが必要です")
        self._wait_header_field("sold")
        self.log(f"Step 2: Sold-To '{c_code}' 送信")
        generation = self.session.automation_snapshot()[2]
        self.send(f"{c_code}\r")
        self._wait_header_field("bill", confirm_sold=True, after_generation=generation)

        self.log(f"Step 2: Bill-To '{c_code}' 送信")
        generation = self.session.automation_snapshot()[2]
        self.send(f"{c_code}\r")
        self._wait_header_field("ship", after_generation=generation)

        self.log(f"Step 2: Ship-To '{s_code}' 送信")
        generation = self.session.automation_snapshot()[2]
        self.send(f"{s_code}\r")
        self._wait_header_field("date", after_generation=generation)
        self._verify_header_codes(c_code, s_code)

        # 2-5: Order Date からの一括貼り付けバッファ (全8項目を改行で結合して一括送信)
        # Line 1: Order Date (today_qad)
        # Line 2: Required Date (req_qad)
        # Line 3: Promise Date ("" 空Enterスキップ)
        # Line 4: Due Date (due_qad)
        # Line 5: Perform Date ("" 空Enterスキップ)
        # Line 6: Pricing Date ("" 空Enterスキップ ★必須)
        # Line 7: Purchase Order (po_val)
        # Line 8: Remarks (rem_val)
        paste_items = build_order_header_fields(self.payload)
        paste_str = "\r".join(paste_items)
        # 実機運用で安定している8項目一括送信を維持し、送信後は画面応答の描画完了を待つ
        self.log(f"Step 2: Order Dateからの一括貼り付けバッファ送信 ({len(paste_items)} 項目: Order Date〜Remarks)")
        generation = self.session.automation_snapshot()[2]
        self.send_and_settle(paste_str, 0.5, desc="Step 2: ヘッダー8項目一括送信", critical=True)
        self._wait_header_field("remarks", after_generation=generation, values=paste_items)

        # 2-6: ヘッダー確定: F1 送信
        self.log("Step 2: F1 送信 (ヘッダー確定)")
        self.send_and_settle(KEY_SEQUENCES["F1"], 0.5, critical=True)
        text, cursor, generation = self.session.automation_snapshot()
        self.log(f"Step 2 ヘッダー確定後: cursor={cursor} rx={generation} input={self._header_field_at_cursor(text, cursor) or 'UNKNOWN'}")

        # Step 3: Tax Usage ポップアップ または Salesperson画面（警告があれば wait_for_screen が自動解除）
        self.wait_for_screen(
            lambda txt: "tax usage:" in txt or "tax environment:" in txt or "salesperson 1:" in txt,
            desc="Step 3: Tax ポップアップ または Salesperson画面"
        )
        curr_txt = clean_screen_text(self.get_screen_text()).lower()
        if "tax usage:" in curr_txt or "tax environment:" in curr_txt:
            self.set_status("Step 3: Tax ポップアップスキップ中...", "working")
            self.log("Step 3: F1 送信 (Tax スキップ)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.25)

        # Step 4: Salesperson / Freight 画面
        self.wait_for_screen(
            lambda txt: "salesperson 1:" in txt or "freight list:" in txt or "transaction comments" in txt or "sales order line" in txt,
            desc="Step 4: Salesperson画面 または 次画面"
        )
        curr_txt = clean_screen_text(self.get_screen_text()).lower()
        if "salesperson 1:" in curr_txt or "freight list:" in curr_txt:
            self.set_status("Step 4: Salesperson / Freight 画面スキップ中...", "working")
            self.log("Step 4: F1 送信 (Salesperson スキップ)")
            self.send(KEY_SEQUENCES["F1"])
            self.sleep(0.25)

        # Step 5: 特記事項 (Transaction Comments / 案C: 既定コメント全クリア置換)
        self.wait_for_screen(
            lambda txt: "transaction comments" in txt or ("sales order line" in txt and "transaction comments" not in txt),
            desc="Step 5: 特記事項 (Comments) または 明細画面"
        )
        curr_txt = clean_screen_text(self.get_screen_text()).lower()
        if "transaction comments" in curr_txt:
            so_comm = str(self.payload.get("so_comment", "")).strip()
            if so_comm:
                self.set_status("Step 5: 特記事項入力中 (案C: 全クリア置換)...", "working")
                self.log("Step 5: F1 送信 (コメント本文エディタへ移動)")
                self.send(KEY_SEQUENCES["F1"])
                self.sleep(0.15)

                # 案C: 得意先マスター等の既定コメントを全クリア
                self.log("Step 5: 案C実行 - 既定コメントの全クリア (F8: Clear送信)")
                self.send(KEY_SEQUENCES.get("F8", "\x1b[19"))
                self.sleep(0.12)

                # クリア確認ダイアログ（プロンプト）が出現した場合は応答
                check_txt = clean_screen_text(self.get_screen_text()).lower()
                if "clear" in check_txt and any(p in check_txt for p in ("y/n", "yes/no", "confirm", "?")):
                    self.log("Step 5: クリア確認プロンプト検知 -> 'yes' 送信")
                    self.send("y\r")
                    self.sleep(0.12)

                # 万一画面に既定テキストが残っている場合の補完クリア (Ctrl-Z)
                post_clear_txt = clean_screen_text(self.get_screen_text())
                editor_lines = [
                    l.strip() for l in post_clear_txt.splitlines()[5:20]
                    if l.strip() and not l.strip().startswith(("F1=", "Adding", "Master", "Page:", "Type:", "xxsosomt", "lqq", "mqq", "x   ", "│", "┌", "└"))
                ]
                if editor_lines:
                    self.log("Step 5: Ctrl-Z (^z) 送信によるクリア補完")
                    self.send("\x1a")
                    self.sleep(0.12)

                # 新規コメント本文の入力
                self.log(f"Step 5: 新規特記事項本文入力 (全 {len(so_comm.splitlines())} 行)")
                for c_line in so_comm.splitlines():
                    self.send(f"{c_line}\r")
                    self.sleep(0.08)

                self.log("Step 5: F1 送信 (コメント本文確定)")
                self.send(KEY_SEQUENCES["F1"])

                # 'Print On Quote:' ポップアップの出現を最大 2.0 秒待機
                quote_appeared = False
                for _ in range(20):
                    self.sleep(0.1)
                    q_txt = clean_screen_text(self.get_screen_text()).lower()
                    if "print on quote" in q_txt or "print on sales order" in q_txt:
                        quote_appeared = True
                        break
                    if "master reference:" in q_txt and "language:" in q_txt:
                        break

                if quote_appeared:
                    self.log("Step 5: 'Print On Quote:' 検知 -> F1 送信で確定")
                    self.send(KEY_SEQUENCES["F1"])
                    self.sleep(0.15)

                self.log("Step 5: F4 送信 (明細画面へ進む)")
                self.send_and_settle(KEY_SEQUENCES["F4"], 0.5, critical=True)

                # コメント画面残留チェック（抜けるまで最大3回F4）
                for _ in range(3):
                    c_txt = clean_screen_text(self.get_screen_text()).lower()
                    if "transaction comments" in c_txt and "sales order line" not in c_txt:
                        self.log("Step 5: コメント画面残留検知 -> 再度 F4 送信")
                        self.send_and_settle(KEY_SEQUENCES["F4"], 0.35, critical=True)
                    else:
                        break
            else:
                self.set_status("Step 5: 特記事項スキップ中...", "working")
                self.log("Step 5: F4 送信 (コメントなし・明細へ直行)")
                self.send_and_settle(KEY_SEQUENCES["F4"], 0.45, critical=True)

                for _ in range(3):
                    c_txt = clean_screen_text(self.get_screen_text()).lower()
                    if "transaction comments" in c_txt and "sales order line" not in c_txt:
                        self.log("Step 5: コメント画面残留検知 -> 再度 F4 送信")
                        self.send_and_settle(KEY_SEQUENCES["F4"], 0.35, critical=True)
                    else:
                        break

        # Step 6 以降へ進む
        return self.execute_step6(self.payload.get("items", []))


class DoubleControlTap:
    """Only two short, isolated Ctrl presses count; repeats/chords don't."""
    CONTROL_KEYS = {"Control_L", "Control_R"}

    def __init__(self, interval=0.45, max_hold=0.4):
        self.interval = interval
        self.max_hold = max_hold
        self.reset()

    def reset(self):
        self.down = set()
        self.started = None
        self.last_release = None
        self.cancelled = False

    def press(self, key, now, state=0):
        if key not in self.CONTROL_KEYS:
            self.cancelled = True
            self.last_release = None
            return
        if key in self.down:
            return
        if not self.down:
            self.started = now
            self.cancelled = bool(state & 0x1)
        else:
            self.cancelled = True
        self.down.add(key)

    def release(self, key, now):
        if key not in self.down:
            return False
        self.down.remove(key)
        if self.down:
            self.cancelled = True
            return False
        valid = not self.cancelled and self.started is not None and now - self.started <= self.max_hold
        self.started = None
        if not valid:
            self.last_release = None
            return False
        if self.last_release is not None and now - self.last_release <= self.interval:
            self.last_release = None
            return True
        self.last_release = now
        return False


class DateField(ctk.CTkFrame):
    def __init__(self, parent, colors, font_family):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.colors = colors
        self.font_family = font_family
        self.value = date.today()
        self.cursor_date = self.value
        self.variable = tk.StringVar(self, value=format_order_date(self.value))
        self.popup = None
        self._selected_button = None
        self._month_label = None
        self._cell_buttons = []
        self._date_to_button = {}
        self.input_entry = None
        self.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.variable, state="readonly", height=34, width=140,
            font=(font_family, 13), fg_color="#FFFFFF", text_color=colors["text"],
            border_color=colors["border"], corner_radius=7,
        )
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Button-1>", lambda event: self.open_calendar())
        self.entry.bind("<Return>", lambda event: self._on_entry_confirm_or_open())
        self.entry.bind("<KP_Enter>", lambda event: self._on_entry_confirm_or_open())
        self.entry.bind("<space>", lambda event: self._on_entry_confirm_or_open())
        # 日付欄で数字を打ち始めたら、ポップアップを開いて直接入力欄へ引き継ぐ
        self.entry._entry.bind("<KeyPress>", self._on_entry_typed, add="+")
        for key, step in (("<Left>", -1), ("<Right>", 1), ("<Up>", -7), ("<Down>", 7)):
            self.entry._entry.bind(key, lambda event, s=step: self._on_entry_arrow(s), add="+")
        self.button = tk.Button(
            self, text="▾", command=self.open_calendar, font=(font_family, 12),
            bg=colors["button"], fg=colors["text"], activebackground=colors["hover"],
            relief="flat", borderwidth=0, takefocus=True, padx=8,
        )
        self.button.grid(row=0, column=1, padx=(4, 0), sticky="ns")

    def _is_calendar_open(self):
        return self.popup is not None and self.popup.winfo_exists()

    def _on_entry_typed(self, event):
        if event.char and event.char.isdigit() and not (event.state & 0x4):
            self.open_calendar(initial_text=event.char)
            return "break"
        return None

    def _on_entry_confirm_or_open(self):
        picker = getattr(self, "range_picker", None)
        if picker is not None and picker.is_open():
            return picker.commit()
        if self._is_calendar_open():
            return self._confirm_date()
        return self.open_calendar()

    def _on_entry_arrow(self, step):
        picker = getattr(self, "range_picker", None)
        if picker is not None and picker.is_open():
            return picker.move_cursor(step)
        if self._is_calendar_open():
            return self._move_cursor_date(step)
        return None

    def focus_set(self):
        self.entry.focus_set()

    def set_date(self, value):
        self.value = value
        self.cursor_date = value
        self.variable.set(format_order_date(value))
        self.close_calendar()
        self.entry.focus_set()

    def close_calendar(self):
        picker = getattr(self, "range_picker", None)
        if picker is not None:
            picker.close()
            return
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None
        self._selected_button = None
        self._month_label = None
        self._cell_buttons = []
        self._date_to_button = {}
        self.input_entry = None

    def open_calendar(self, initial_text=None):
        picker = getattr(self, "range_picker", None)
        if picker is not None:
            return picker.open(self, initial_text)
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            if initial_text:
                self._start_typing(initial_text)
            return "break"
        self.cursor_date = self.value
        self.month = self.value.replace(day=1)
        self.popup = ctk.CTkToplevel(self)
        self.popup.title("日付選択")
        self.popup.configure(fg_color=self.colors["panel"])
        self.popup.resizable(False, False)
        self.popup.transient(self.winfo_toplevel())
        self.popup.protocol("WM_DELETE_WINDOW", self.close_calendar)
        self.popup.bind("<Escape>", lambda event: self.close_calendar())
        self._bind_calendar_keys(self.popup)
        self._build_date_input()
        self.calendar_body = ctk.CTkFrame(self.popup, fg_color="transparent")
        self.calendar_body.pack(padx=12, pady=(8, 12), fill="both", expand=True)
        self._bind_calendar_keys(self.calendar_body)
        self._build_calendar_widgets()
        self._draw_month()
        self.popup.update_idletasks()
        width, height = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
        x = max(0, min(self.winfo_rootx(), self.winfo_screenwidth() - width - 16))
        y = self.winfo_rooty() + self.winfo_height() + 4
        if y + height > self.winfo_screenheight() - 48:
            y = max(0, self.winfo_rooty() - height - 4)
        self.popup.geometry(f"+{x}+{y}")
        if initial_text:
            self.popup.after(10, lambda: self._start_typing(initial_text))
        else:
            self.popup.after(10, self._focus_calendar)
        return "break"

    def _build_date_input(self):
        """yyyy/mm/dd の直接入力欄。Enterで確定、↓でカレンダーへ移動。"""
        self.input_var = tk.StringVar(self.popup, value=self.value.strftime("%Y/%m/%d"))
        self.input_entry = ctk.CTkEntry(
            self.popup, textvariable=self.input_var, height=32, font=(self.font_family, 13),
            fg_color="#FFFFFF", text_color=self.colors["text"],
            border_color=self.colors["border"], corner_radius=7,
        )
        self.input_entry.pack(padx=12, pady=(12, 0), fill="x")
        inner = self.input_entry._entry
        # カレンダー用のキー割当（ポップアップ全体のバインド）を入力欄では無効にする
        inner.bindtags(tuple(tag for tag in inner.bindtags() if tag != str(self.popup)))
        inner.bind("<Return>", lambda event: self._apply_typed_date())
        inner.bind("<KP_Enter>", lambda event: self._apply_typed_date())
        inner.bind("<Escape>", lambda event: (self.close_calendar(), "break")[1])
        inner.bind("<Down>", lambda event: (self._focus_calendar(), "break")[1])
        inner.bind("<KeyRelease>", lambda event: self._set_input_error(False), add="+")
        self.popup.bind("<KeyPress>", self._on_popup_typed, add="+")

    def _on_popup_typed(self, event):
        # カレンダー操作中に数字を打つと、入力欄へ移って新しく入力を始める
        if self.input_entry is None or event.widget is self.input_entry._entry:
            return None
        if event.char and event.char.isdigit() and not (event.state & 0x4):
            self._start_typing(event.char)
            return "break"
        return None

    def _start_typing(self, text):
        if self.input_entry is None or not self.input_entry.winfo_exists():
            return
        inner = self.input_entry._entry
        inner.delete(0, "end")
        inner.insert(0, text)
        inner.focus_set()
        inner.icursor("end")

    def _set_input_error(self, error):
        if self.input_entry is not None and self.input_entry.winfo_exists():
            color = self.colors.get("danger", "#DC2626") if error else self.colors["border"]
            self.input_entry.configure(border_color=color)

    def _apply_typed_date(self):
        try:
            value = parse_typed_date(self.input_var.get())
        except ValueError:
            self._set_input_error(True)
            return "break"
        self.set_date(value)
        return "break"

    def _sync_input_text(self):
        if self.input_entry is None or not self.input_entry.winfo_exists():
            return
        if self.popup.focus_get() is not self.input_entry._entry:
            self.input_var.set(self.cursor_date.strftime("%Y/%m/%d"))
            self._set_input_error(False)

    def _build_calendar_widgets(self):
        prev_btn = tk.Button(
            self.calendar_body, text="‹", command=lambda: self._move_month(-1),
            width=3, font=(self.font_family, 11), relief="flat", bd=0, highlightthickness=0,
            padx=2, pady=5, bg=self.colors["panel"], fg=self.colors["text"],
            activebackground=self.colors["hover"], takefocus=True,
        )
        self._bind_calendar_keys(prev_btn)
        prev_btn.grid(row=0, column=0)

        self._month_label = ctk.CTkLabel(
            self.calendar_body, text="", font=(self.font_family, 14),
            text_color=self.colors["text"],
        )
        self._month_label.grid(row=0, column=1, columnspan=5)

        next_btn = tk.Button(
            self.calendar_body, text="›", command=lambda: self._move_month(1),
            width=3, font=(self.font_family, 11), relief="flat", bd=0, highlightthickness=0,
            padx=2, pady=5, bg=self.colors["panel"], fg=self.colors["text"],
            activebackground=self.colors["hover"], takefocus=True,
        )
        self._bind_calendar_keys(next_btn)
        next_btn.grid(row=0, column=6)

        for col, text in enumerate(WEEKDAYS):
            ctk.CTkLabel(
                self.calendar_body, text=text, width=34,
                text_color=self.colors["muted"], font=(self.font_family, 12),
            ).grid(row=1, column=col)

        self._cell_buttons = []
        for r in range(6):
            row_btns = []
            for c in range(7):
                btn = tk.Button(
                    self.calendar_body, text="", width=3,
                    font=(self.font_family, 11), relief="flat", bd=0, highlightthickness=0,
                    padx=2, pady=5, bg=self.colors["panel"], fg=self.colors["text"],
                    activebackground=self.colors["hover"], takefocus=True,
                )
                self._bind_calendar_keys(btn)
                btn.grid(row=r + 2, column=c)
                row_btns.append(btn)
            self._cell_buttons.append(row_btns)

        today_btn = tk.Button(
            self.calendar_body, text="今日", command=lambda: self.set_date(date.today()),
            font=(self.font_family, 11), relief="flat", bd=0, highlightthickness=0,
            padx=2, pady=5, bg=self.colors["panel"], fg=self.colors["text"],
            activebackground=self.colors["hover"], takefocus=True,
        )
        self._bind_calendar_keys(today_btn)
        today_btn.grid(row=8, column=0, columnspan=7, sticky="ew", pady=(8, 0))

    def _style_day_button(self, btn, selected):
        btn.configure(
            bg=self.colors["accent"] if selected else self.colors["panel"],
            fg=self.colors["on_accent"] if selected else self.colors["text"],
            activebackground=self.colors["accent_hover"] if selected else self.colors["hover"],
        )

    def _focus_calendar(self):
        if hasattr(self, "_selected_button") and self._selected_button and self._selected_button.winfo_exists():
            self._selected_button.focus_set()
        elif self.popup is not None and self.popup.winfo_exists():
            self.popup.focus_set()

    def _bind_calendar_keys(self, widget):
        widget.bind("<Left>", lambda e: self._move_cursor_date(-1), add="+")
        widget.bind("<Right>", lambda e: self._move_cursor_date(1), add="+")
        widget.bind("<Up>", lambda e: self._move_cursor_date(-7), add="+")
        widget.bind("<Down>", lambda e: self._move_cursor_date(7), add="+")
        widget.bind("<Return>", lambda e: self._confirm_date(), add="+")
        widget.bind("<KP_Enter>", lambda e: self._confirm_date(), add="+")
        widget.bind("<space>", lambda e: self._confirm_date(), add="+")
        widget.bind("<Prior>", lambda e: self._on_page_month(-1), add="+")
        widget.bind("<Next>", lambda e: self._on_page_month(1), add="+")

    def _on_page_month(self, step):
        self._move_month(step)
        return "break"

    def _move_cursor_date(self, days):
        if not self._is_calendar_open():
            return None
        new_date = self.cursor_date + timedelta(days=days)
        if 1 <= new_date.year <= 9999:
            old_date = self.cursor_date
            self.cursor_date = new_date
            new_month = self.cursor_date.replace(day=1)
            if new_month != self.month:
                self.month = new_month
                self._draw_month()
            else:
                old_btn = self._date_to_button.get(old_date)
                if old_btn:
                    self._style_day_button(old_btn, False)
                new_btn = self._date_to_button.get(new_date)
                if new_btn:
                    self._style_day_button(new_btn, True)
                    self._selected_button = new_btn
            self._sync_input_text()
            self._focus_calendar()
        return "break"

    def _confirm_date(self):
        if not self._is_calendar_open():
            return None
        self.set_date(self.cursor_date)
        return "break"

    def _move_month(self, step):
        index = self.month.year * 12 + self.month.month - 1 + step
        year, month = divmod(index, 12)
        if 1 <= year <= 9999:
            self.month = date(year, month + 1, 1)
            max_days = calendar.monthrange(year, month + 1)[1]
            new_day = min(self.cursor_date.day, max_days)
            self.cursor_date = date(year, month + 1, new_day)
            self._draw_month()
            self._focus_calendar()

    def _day_button(self, text, command, selected=False):
        btn = tk.Button(
            self.calendar_body, text=text, command=command, width=3,
            font=(self.font_family, 11), relief="flat", bd=0, highlightthickness=0, padx=2, pady=5,
            bg=self.colors["accent"] if selected else self.colors["panel"],
            fg=self.colors["on_accent"] if selected else self.colors["text"],
            activebackground=self.colors["hover"], takefocus=True,
        )
        self._bind_calendar_keys(btn)
        return btn

    def _draw_month(self):
        if not self._is_calendar_open() or self._month_label is None:
            return
        self._month_label.configure(text=f"{self.month.year}年 {self.month.month}月")
        weeks = calendar.Calendar().monthdayscalendar(self.month.year, self.month.month)
        self._date_to_button = {}
        self._selected_button = None
        current_cursor = getattr(self, "cursor_date", self.value)

        for r in range(6):
            week = weeks[r] if r < len(weeks) else [0] * 7
            for c in range(7):
                day = week[c]
                btn = self._cell_buttons[r][c]
                if day:
                    val = self.month.replace(day=day)
                    selected = (val == current_cursor)
                    btn.configure(
                        text=str(day),
                        state="normal",
                        command=lambda d=val: self.set_date(d),
                    )
                    self._style_day_button(btn, selected)
                    self._date_to_button[val] = btn
                    if selected:
                        self._selected_button = btn
                else:
                    btn.configure(
                        text="",
                        state="disabled",
                        command=lambda: None,
                        bg=self.colors["panel"],
                        fg=self.colors["panel"],
                        activebackground=self.colors["panel"],
                    )
        self._sync_input_text()


class OrderEntryPanel(ctk.CTkFrame):
    def __init__(self, parent, colors, font_family, on_submit, on_close,
                 customers=(), destinations=(), customer_info=None, item_list_data=None, on_log=None):
        super().__init__(parent, width=590, fg_color=colors["panel"],
                         corner_radius=12, border_width=1, border_color=colors["border"])
        self.colors = colors
        self.font_family = font_family
        self.on_submit = on_submit
        self.customer_info = customer_info or read_customer_info_file()
        if not customers and self.customer_info.customer_names:
            customers = self.customer_info.customer_names
        if item_list_data is not None and isinstance(item_list_data, dict):
            self.item_list_data = dict(item_list_data)
        else:
            self.item_list_data = read_item_list_file()
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.fields = {}
        self.item_entries = []
        self.item_desc_entries = []
        self.product_autocompletes = []
        self.error_field = None
        self.customer_ship_tos = dict(self.customer_info.customer_ship_tos)
        if customers and not self.customer_ship_tos:
            self.customer_ship_tos = {c: list(destinations) for c in customers}

        # 閉じるボタンを廃止し、上部マージンを詰めて表示スペースを最大化
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.body.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="nsew")
        self.body.grid_columnconfigure((0, 1), weight=1, uniform="order_header")
        self._label(self.body, "顧客名", 0, 0)
        self._label(self.body, "納品先", 0, 1)

        # 顧客名フレーム (左: ドロップダウン, 右: 顧客コードKey表示)
        cust_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        cust_frame.grid(row=1, column=0, padx=4, pady=(0, 10), sticky="ew")
        cust_frame.grid_columnconfigure(0, weight=1)
        cust_frame.grid_columnconfigure(1, weight=0)

        cust_values = [str(item) for item in customers if str(item).strip()] if isinstance(customers, (list, tuple)) else []
        self.fields["customer_name"] = HighlightComboBox(
            cust_frame, values=cust_values or [""], width=130, height=34,
            font=(font_family, 13), dropdown_font=(font_family, 13),
            fg_color="#FFFFFF", text_color=colors["text"], border_color=colors["border"],
            button_color=colors["button"], button_hover_color=colors["hover"],
            dropdown_fg_color=colors["panel"], dropdown_text_color=colors["text"],
            dropdown_hover_color=colors["hover"], corner_radius=7,
            colors=colors,
            command=self._on_customer_selected,
        )
        self.fields["customer_name"].set("")
        self.fields["customer_name"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.customer_code_entry = ctk.CTkEntry(
            cust_frame, width=95, height=34, font=(FONT_FAMILY, 12, "bold"),
            fg_color="#F8FAFC", text_color=colors["text"], border_width=1,
            border_color=colors["border"], corner_radius=7, state="readonly",
            justify="center", placeholder_text="Code"
        )
        self.customer_code_entry.grid(row=0, column=1, sticky="e")

        # 納品先フレーム (左: ドロップダウン, 右: 納品先コードKey表示)
        ship_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        ship_frame.grid(row=1, column=1, padx=4, pady=(0, 10), sticky="ew")
        ship_frame.grid_columnconfigure(0, weight=1)
        ship_frame.grid_columnconfigure(1, weight=0)

        ship_values = [str(item) for item in destinations if str(item).strip()] if isinstance(destinations, (list, tuple)) else []
        self.fields["ship_to"] = HighlightComboBox(
            ship_frame, values=ship_values or [""], width=130, height=34,
            font=(font_family, 13), dropdown_font=(font_family, 13),
            fg_color="#FFFFFF", text_color=colors["text"], border_color=colors["border"],
            button_color=colors["button"], button_hover_color=colors["hover"],
            dropdown_fg_color=colors["panel"], dropdown_text_color=colors["text"],
            dropdown_hover_color=colors["hover"], corner_radius=7,
            colors=colors,
            command=self._on_ship_to_selected,
        )
        self.fields["ship_to"].set("")
        self.fields["ship_to"].grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.ship_to_code_entry = ctk.CTkEntry(
            ship_frame, width=95, height=34, font=(FONT_FAMILY, 12, "bold"),
            fg_color="#F8FAFC", text_color=colors["text"], border_width=1,
            border_color=colors["border"], corner_radius=7, state="readonly",
            justify="center", placeholder_text="Code"
        )
        self.ship_to_code_entry.grid(row=0, column=1, sticky="e")

        # 手動入力やフォーカス移動時にもリアルタイムでコードを更新
        self.fields["customer_name"]._entry.bind("<KeyRelease>", lambda e: self._update_customer_and_dest_keys(), add="+")
        self.fields["customer_name"]._entry.bind("<FocusOut>", lambda e: self._update_customer_and_dest_keys(), add="+")
        self.fields["ship_to"]._entry.bind("<KeyRelease>", lambda e: self._update_customer_and_dest_keys(), add="+")
        self.fields["ship_to"]._entry.bind("<FocusOut>", lambda e: self._update_customer_and_dest_keys(), add="+")
        self._bind_ctrl_d_delete(self.fields["customer_name"])
        self._bind_ctrl_d_delete(self.fields["ship_to"])

        # 納品先住所表示エリア（左側 col 0 に配置、5行をスクロール無しで表示）
        self._label(self.body, "住所", 2, 0)
        self.address_box = ctk.CTkTextbox(
            self.body, height=115, font=(font_family, 12),
            fg_color="#FFFFFF", text_color=colors["text"], border_width=1,
            border_color=colors["border"], corner_radius=7, wrap="word",
        )
        self.address_box.grid(row=3, column=0, rowspan=3, padx=4, pady=(0, 10), sticky="nsew")
        self.address_box.configure(state="disabled")

        # 右側（col 1）に Required date と Due date を縦2段で配置
        self._label(self.body, "Required date", 2, 1)
        req_field = DateField(self.body, colors, font_family)
        req_field.grid(row=3, column=1, padx=4, pady=(0, 6), sticky="ew")
        self.fields["required_date"] = req_field

        self._label(self.body, "Due date", 4, 1)
        due_field = DateField(self.body, colors, font_family)
        due_field.grid(row=5, column=1, padx=4, pady=(0, 10), sticky="ew")
        self.fields["due_date"] = due_field
        self.date_range_picker = OrderDateRangePicker(
            due_field, req_field, colors, font_family, parse_typed_date, format_order_date)
        self._label(self.body, "Purchase Order", 6, 0, 2)
        self.fields["purchase_order"] = self._entry(self.body)
        self.fields["purchase_order"].grid(row=7, column=0, columnspan=2, padx=4, pady=(0, 10), sticky="ew")
        for col, key, label in ((0, "remarks", "Remarks"), (1, "so_comment", "SO comment")):
            self._label(self.body, label, 8, col)
            field = ctk.CTkTextbox(
                self.body, height=68, width=140, font=(font_family, 13),
                fg_color="#FFFFFF", text_color=colors["text"], border_width=1,
                border_color=colors["border"], corner_radius=7, wrap="word",
            )
            field.grid(row=9, column=col, padx=4, pady=(0, 14), sticky="ew")
            self.fields[key] = field
        self.table = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
        self.table.grid(row=10, column=0, columnspan=2, padx=2, pady=(0, 8), sticky="ew")
        for col, label in enumerate(ITEM_LABELS):
            self.table.grid_columnconfigure(col, weight=3 if col == 0 else 1, minsize=132 if col == 0 else 66)
            self._label(self.table, label, 0, col)

        item_keys = list(self.item_list_data.keys())
        combo_values = item_keys[:100] if len(item_keys) > 100 else item_keys

        for row in range(5):
            entries = {}
            for col, key in enumerate(ITEM_FIELDS):
                if key == "product_name":
                    field = ProductComboBox(
                        self.table, values=combo_values or [""], width=1, height=34,
                        font=(font_family, 13), dropdown_font=(font_family, 13),
                        fg_color="#FFFFFF", text_color=colors["text"], border_color=colors["border"],
                        button_color=colors["button"], button_hover_color=colors["hover"],
                        dropdown_fg_color=colors["panel"], dropdown_text_color=colors["text"],
                        dropdown_hover_color=colors["hover"], corner_radius=7,
                        colors=colors,
                        command=lambda val, r=row: self._on_product_selected(r, val),
                        on_change=lambda val, r=row: self._on_product_selected(r, val),
                    )
                    field.grid(row=row * 2 + 1, column=col, padx=2, pady=3, sticky="ew")

                    # オートコンプリートポップアップをバインド (全件を渡して超高速インクリメンタル検索)
                    ac = AutocompletePopup(
                        field, colors, font_family,
                        on_select=lambda val, r=row: self._on_product_selected(r, val),
                    )
                    ac.set_candidates(item_keys)
                    field.product_autocomplete = ac
                    self.product_autocompletes.append(ac)

                    field._entry.bind("<KeyRelease>", lambda event, r=row: self._on_product_entry_changed(r), add="+")
                    field._entry.bind("<FocusOut>", lambda event, r=row: self._on_product_entry_changed(r), add="+")
                    self._bind_ctrl_d_delete(field)
                else:
                    field = self._entry(self.table, width=1, justify="right")
                    field.grid(row=row * 2 + 1, column=col, padx=2, pady=3, sticky="ew")
                entries[key] = field
                self.fields[(row, key)] = field
            self.item_entries.append(entries)

            # Item Codeの下に一行編集不能の行を入れて、Value (C列+D列の結合値) を表示
            desc_entry = ctk.CTkEntry(
                self.table, height=24, font=(font_family, 11),
                fg_color="#F8FAFC", text_color=colors.get("muted", "#64748B"),
                border_color=colors["border"], corner_radius=5, state="readonly"
            )
            desc_entry.grid(row=row * 2 + 2, column=0, columnspan=5, padx=2, pady=(0, 5), sticky="ew")
            self.item_desc_entries.append(desc_entry)
        self.error_label = ctk.CTkLabel(self, text="", text_color=colors["error"],
                                        font=(font_family, 12), wraplength=540, anchor="w")
        self.error_label.grid(row=1, column=0, padx=20, pady=(4, 0), sticky="ew")
        self.error_label.grid_remove()
        self.send_button = tk.Button(
            self, text="送信", command=self.submit, bg=colors["accent"], fg=colors["on_accent"],
            activebackground=colors["accent_hover"], activeforeground=colors["on_accent"],
            relief="flat", bd=0, font=(font_family, 12), padx=30, pady=9,
        )
        self.send_button.grid(row=2, column=0, padx=20, pady=(8, 14), sticky="e")
        footer_left = tk.Frame(self, bg=colors["panel"])
        footer_left.grid(row=2, column=0, padx=20, pady=(8, 14), sticky="w")
        self.reset_button = tk.Button(
            footer_left, text="リセット", command=self.reset_fields,
            bg="#E2E8F0", fg=colors["text"],
            activebackground="#CBD5E1", activeforeground=colors["text"],
            relief="flat", bd=0, font=(font_family, 12), padx=26, pady=9,
            cursor="hand2",
        )
        self.reset_button.pack(side="left")
        self.log_button = tk.Button(
            footer_left, text="ログ", command=on_log,
            bg="#E2E8F0", fg=colors["text"], activebackground="#CBD5E1",
            relief="flat", bd=0, font=(font_family, 12), padx=22, pady=9, cursor="hand2",
        )
        self.log_button.pack(side="left", padx=(8, 0))
        for field in self.fields.values():
            target = field.entry if isinstance(field, DateField) else field
            target.bind("<FocusIn>", lambda event, widget=field: self._keep_visible(widget), add="+")
        self._bind_arrow_navigation()

        self.customer_autocomplete = AutocompletePopup(
            self.fields["customer_name"], colors, font_family,
            on_select=self._on_customer_selected,
        )
        self.customer_autocomplete.set_candidates(customers)

        self.ship_to_autocomplete = AutocompletePopup(
            self.fields["ship_to"], colors, font_family,
            on_select=self._on_ship_to_selected,
        )
        self.ship_to_autocomplete.set_candidates(destinations)

        self._bind_delete_keys()

    def _bind_delete_keys(self):
        """サイドバー内の全入力欄でDelete / KP_Delete押下時に確実に文字・値を消去するバインドを設定"""
        # 1. 顧客名・納品先
        for f_name in ("customer_name", "ship_to"):
            cb = self.fields.get(f_name)
            if cb and hasattr(cb, "_entry"):
                cb._entry.bind("<Delete>", lambda e: handle_field_delete(e.widget, on_change=self._update_customer_and_dest_keys))
                cb._entry.bind("<KP_Delete>", lambda e: handle_field_delete(e.widget, on_change=self._update_customer_and_dest_keys))

        # 2. Purchase Order
        po = self.fields.get("purchase_order")
        if po and hasattr(po, "_entry"):
            po._entry.bind("<Delete>", lambda e: handle_field_delete(e.widget))
            po._entry.bind("<KP_Delete>", lambda e: handle_field_delete(e.widget))

        # 3. Remarks, SO Comment (Textbox)
        for f_name in ("remarks", "so_comment"):
            tb = self.fields.get(f_name)
            if tb and hasattr(tb, "_textbox"):
                tb._textbox.bind("<Delete>", lambda e: handle_field_delete(e.widget))
                tb._textbox.bind("<KP_Delete>", lambda e: handle_field_delete(e.widget))

        # 4. 明細テーブルの各行（5行）
        for row_idx, entries in enumerate(self.item_entries):
            # product_name (HighlightComboBox)
            p_field = entries.get("product_name")
            if p_field and hasattr(p_field, "_entry"):
                p_field._entry.bind(
                    "<Delete>",
                    lambda e, r=row_idx: handle_field_delete(e.widget, on_change=lambda: self._on_product_entry_changed(r))
                )
                p_field._entry.bind(
                    "<KP_Delete>",
                    lambda e, r=row_idx: handle_field_delete(e.widget, on_change=lambda: self._on_product_entry_changed(r))
                )

            # width, length, quantity, price (CTkEntry)
            for k in ("width", "length", "quantity", "price"):
                item_field = entries.get(k)
                if item_field and hasattr(item_field, "_entry"):
                    item_field._entry.bind("<Delete>", lambda e: handle_field_delete(e.widget))
                    item_field._entry.bind("<KP_Delete>", lambda e: handle_field_delete(e.widget))

    def _bind_arrow_navigation(self):
        for field in self.fields.values():
            inner = self._get_inner_widget(field)
            if inner is None:
                continue
            for key, direction in (("<Up>", "Up"), ("<Down>", "Down"),
                                   ("<Left>", "Left"), ("<Right>", "Right")):
                inner.bind(key, lambda event, d=direction: self._on_arrow_nav(event, d), add="+")

    def _get_inner_widget(self, field):
        if hasattr(field, "entry"):
            return getattr(field.entry, "_entry", field.entry)
        if hasattr(field, "_entry"):
            return field._entry
        if hasattr(field, "_textbox"):
            return field._textbox
        return field

    def _get_nav_items(self):
        items = []
        for key, field in self.fields.items():
            inner = self._get_inner_widget(field)
            if inner is None or not inner.winfo_exists():
                continue
            rx = inner.winfo_rootx()
            ry = inner.winfo_rooty()
            rw = inner.winfo_width()
            rh = inner.winfo_height()
            items.append({
                "key": key,
                "field": field,
                "inner": inner,
                "x1": rx,
                "y1": ry,
                "x2": rx + rw,
                "y2": ry + rh,
                "cx": rx + rw / 2.0,
                "cy": ry + rh / 2.0,
            })
        return items

    def _find_nearest_nav_field(self, current_inner, direction):
        nav_items = self._get_nav_items()
        current_item = next((item for item in nav_items if item["inner"] is current_inner), None)
        if not current_item:
            return None

        cx, cy = current_item["cx"], current_item["cy"]
        try:
            if isinstance(current_inner, tk.Entry):
                caret_bbox = current_inner.bbox(tk.INSERT)
                if caret_bbox:
                    cx = current_inner.winfo_rootx() + caret_bbox[0]
            elif isinstance(current_inner, tk.Text):
                caret_bbox = current_inner.bbox("insert")
                if caret_bbox:
                    cx = current_inner.winfo_rootx() + caret_bbox[0]
                    cy = current_inner.winfo_rooty() + caret_bbox[1]
        except Exception:
            pass

        x1, y1, x2, y2 = current_item["x1"], current_item["y1"], current_item["x2"], current_item["y2"]

        candidates = []
        for cand in nav_items:
            if cand["inner"] is current_inner:
                continue
            tcx, tcy = cand["cx"], cand["cy"]
            tx1, ty1, tx2, ty2 = cand["x1"], cand["y1"], cand["x2"], cand["y2"]

            if direction == "Left":
                if tx2 > x1 + 5:
                    continue
                gap = max(0, x1 - tx2)
                v_overlap = max(0, min(y2, ty2) - max(y1, ty1))
                sec_dist = 0 if v_overlap > 0 else min(abs(y1 - ty2), abs(ty1 - y2))
                score = gap * 10.0 + sec_dist * 50.0 + abs(cy - tcy) * 0.1
                candidates.append((score, cand))

            elif direction == "Right":
                if tx1 < x2 - 5:
                    continue
                gap = max(0, tx1 - x2)
                v_overlap = max(0, min(y2, ty2) - max(y1, ty1))
                sec_dist = 0 if v_overlap > 0 else min(abs(y1 - ty2), abs(ty1 - y2))
                score = gap * 10.0 + sec_dist * 50.0 + abs(cy - tcy) * 0.1
                candidates.append((score, cand))

            elif direction == "Up":
                if ty2 > y1 + 5:
                    continue
                gap = max(0, y1 - ty2)
                h_overlap = max(0, min(x2, tx2) - max(x1, tx1))
                sec_dist = 0 if h_overlap > 0 else min(abs(x1 - tx2), abs(tx1 - x2))
                score = gap * 10.0 + sec_dist * 30.0 + abs(cx - tcx) * 0.5
                candidates.append((score, cand))

            elif direction == "Down":
                if ty1 < y2 - 5:
                    continue
                gap = max(0, ty1 - y2)
                h_overlap = max(0, min(x2, tx2) - max(x1, tx1))
                sec_dist = 0 if h_overlap > 0 else min(abs(x1 - tx2), abs(tx1 - x2))
                score = gap * 10.0 + sec_dist * 30.0 + abs(cx - tcx) * 0.5
                candidates.append((score, cand))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _get_active_autocomplete(self, widget):
        for attr in ("customer_autocomplete", "ship_to_autocomplete"):
            ac = getattr(self, attr, None)
            if ac is not None and getattr(ac, "entry", None) is widget:
                return ac
        for ac in getattr(self, "product_autocompletes", []):
            if ac is not None and getattr(ac, "entry", None) is widget:
                return ac
        return None

    def _on_arrow_nav(self, event, direction):
        widget = event.widget

        # 顧客名・納品先のドロップダウンの候補が出ている時、上下キーで候補を選択
        ac = self._get_active_autocomplete(widget)
        if ac is not None and ac.is_open():
            if direction == "Down":
                ac._on_down_key(event)
                return "break"
            elif direction == "Up":
                ac._on_up_key(event)
                return "break"

        if isinstance(widget, tk.Entry):
            if direction in ("Left", "Right"):
                if str(widget.cget("state")) != "readonly":
                    has_selection = widget.selection_present()
                    text = widget.get()
                    pos = widget.index(tk.INSERT)
                    if not (has_selection or not text or (direction == "Left" and pos == 0) or (direction == "Right" and pos >= len(text))):
                        return None
        elif isinstance(widget, tk.Text):
            if direction == "Up":
                if widget.index("insert").split(".")[0] != "1":
                    return None
            elif direction == "Down":
                cur_line = widget.index("insert").split(".")[0]
                last_line = widget.index("end-1c").split(".")[0]
                if cur_line != last_line:
                    return None
            elif direction == "Left":
                if widget.index("insert") != "1.0":
                    return None
            elif direction == "Right":
                if widget.index("insert") != widget.index("end-1c"):
                    return None

        # 納品先で → を押したら Required date へ移動する（画面配置上の最寄り判定より優先）
        if direction == "Right" and widget is self._get_inner_widget(self.fields["ship_to"]):
            if getattr(self, "ship_to_autocomplete", None) is not None:
                self.ship_to_autocomplete.close()
            req_field = self.fields["required_date"]
            nearest = {"field": req_field, "inner": self._get_inner_widget(req_field)}
        else:
            nearest = self._find_nearest_nav_field(widget, direction)
        if not nearest:
            return "break" if direction in ("Up", "Down") and isinstance(widget, tk.Entry) else None

        target_field = nearest["field"]
        target_inner = nearest["inner"]

        target_inner.focus_set()
        self._keep_visible(target_field)

        if isinstance(target_inner, tk.Entry):
            target_inner.selection_range(0, tk.END)
            target_inner.icursor(tk.END)
        elif isinstance(target_inner, tk.Text):
            if direction in ("Down", "Right"):
                target_inner.mark_set("insert", "1.0")
            else:
                target_inner.mark_set("insert", "end-1c")
            target_inner.see("insert")

        return "break"


    def _keep_visible(self, field):
        canvas = self.body._parent_canvas
        top = field.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + field.winfo_height()
        visible_top = canvas.canvasy(0)
        viewport_height = canvas.winfo_height()
        target = None
        if top < visible_top:
            target = top - 4
        elif bottom > visible_top + viewport_height:
            target = bottom - viewport_height + 4
        if target is not None:
            canvas.yview_moveto(max(0, target) / max(1, self.body.winfo_height()))

    def _label(self, parent, text, row, col, span=1):
        ctk.CTkLabel(parent, text=text, height=22, anchor="w", font=(self.font_family, 12),
                     text_color=self.colors["text"]).grid(row=row, column=col, columnspan=span,
                                                           padx=4, pady=(0, 3), sticky="ew")

    def _bind_ctrl_d_delete(self, widget):
        target = getattr(widget, "_entry", widget)
        def _handle_ctrl_d(event):
            try:
                if target.select_present():
                    first = target.index("sel.first")
                    last = target.index("sel.last")
                    target.delete(first, last)
                else:
                    cur = target.index("insert")
                    if cur < len(target.get()):
                        target.delete(cur, cur + 1)
            except Exception:
                pass
            return "break"

        for seq in ("<Control-d>", "<Control-D>", "<Control-Key-d>", "<Control-Key-D>"):
            try:
                target.bind(seq, _handle_ctrl_d)
                if hasattr(widget, "bind"):
                    widget.bind(seq, _handle_ctrl_d)
            except Exception:
                pass

    def _entry(self, parent, **kwargs):
        e = ctk.CTkEntry(parent, height=34, font=(self.font_family, 13),
                         fg_color="#FFFFFF", text_color=self.colors["text"],
                         border_color=self.colors["border"], corner_radius=6, **kwargs)
        self._bind_ctrl_d_delete(e)
        return e

    def close_popups(self):
        for key in ("required_date", "due_date"):
            self.fields[key].close_calendar()
        if hasattr(self, "customer_autocomplete"):
            self.customer_autocomplete.close()
        if hasattr(self, "ship_to_autocomplete"):
            self.ship_to_autocomplete.close()
        for ac in getattr(self, "product_autocompletes", []):
            ac.close()

    def _on_product_selected(self, row_idx, product_key):
        product_key = str(product_key).strip()
        val = self.item_list_data.get(product_key, "")
        if 0 <= row_idx < len(self.item_desc_entries):
            desc_entry = self.item_desc_entries[row_idx]
            desc_entry.configure(state="normal")
            desc_entry.delete(0, "end")
            if val:
                desc_entry.insert(0, val)
            desc_entry.configure(state="readonly")

    def _on_product_entry_changed(self, row_idx):
        if 0 <= row_idx < len(self.item_entries):
            field = self.item_entries[row_idx].get("product_name")
            if field is not None:
                key = field.get().strip()
                val = self.item_list_data.get(key, "")
                if 0 <= row_idx < len(self.item_desc_entries):
                    desc_entry = self.item_desc_entries[row_idx]
                    desc_entry.configure(state="normal")
                    desc_entry.delete(0, "end")
                    if val:
                        desc_entry.insert(0, val)
                    desc_entry.configure(state="readonly")

    def set_item_list_data(self, item_list_data):
        self.item_list_data = dict(item_list_data) if item_list_data else {}
        keys = list(self.item_list_data.keys())
        combo_values = keys[:100] if len(keys) > 100 else keys
        for row, entries in enumerate(self.item_entries):
            p_field = entries.get("product_name")
            if p_field is not None and hasattr(p_field, "configure"):
                p_field.configure(values=combo_values or [""])
        for ac in getattr(self, "product_autocompletes", []):
            ac.set_candidates(keys)
        for row in range(len(self.item_entries)):
            self._on_product_entry_changed(row)

    def set_choices(self, field, values):
        self.fields[field].configure(values=values or [""])
        if field == "customer_name" and hasattr(self, "customer_autocomplete"):
            self.customer_autocomplete.set_candidates(values or [])
        elif field == "ship_to" and hasattr(self, "ship_to_autocomplete"):
            self.ship_to_autocomplete.set_candidates(values or [])

    def _display_address(self, address_text):
        if hasattr(self, "address_box") and self.address_box.winfo_exists():
            self.address_box.configure(state="normal")
            self.address_box.delete("1.0", "end")
            if address_text:
                self.address_box.insert("1.0", str(address_text).strip())
            self.address_box.configure(state="disabled")

    def set_customer_ship_tos(self, choices, addresses=None):
        self.customer_ship_tos = {str(customer): list(destinations)
                                  for customer, destinations in choices.items()}
        if addresses and hasattr(self, "customer_info"):
            self.customer_info.addresses.update(addresses)
        customers = list(self.customer_ship_tos)
        self.fields["customer_name"].configure(values=customers or [""])
        if hasattr(self, "customer_autocomplete"):
            self.customer_autocomplete.set_candidates(customers)
        current = self.fields["customer_name"].get()
        if current not in self.customer_ship_tos:
            current = ""
            self.fields["customer_name"].set("")
        self._on_customer_selected(current)

    def _on_customer_selected(self, customer):
        customer = str(customer).strip()
        destinations = self.customer_ship_tos.get(customer, [])
        if not destinations and hasattr(self, "customer_info"):
            destinations = self.customer_info.get_destinations(customer)
        field = self.fields["ship_to"]
        field.configure(values=destinations or [""])
        if hasattr(self, "ship_to_autocomplete"):
            self.ship_to_autocomplete.set_candidates(destinations)
        current_ship_to = field.get()
        if destinations:
            if current_ship_to in destinations:
                self._on_ship_to_selected(current_ship_to)
            elif len(destinations) == 1:
                field.set(destinations[0])
                self._on_ship_to_selected(destinations[0])
            else:
                field.set("")
                self._display_address("")
        else:
            field.set("")
            self._display_address("")
        self._update_customer_and_dest_keys()

    def _on_ship_to_selected(self, ship_to):
        customer = self.fields["customer_name"].get()
        addr = ""
        if hasattr(self, "customer_info"):
            addr = self.customer_info.get_address(customer, ship_to)
        self._display_address(addr)
        self._update_customer_and_dest_keys()

    def _update_customer_and_dest_keys(self):
        cname = self.fields["customer_name"].get().strip() if "customer_name" in self.fields else ""
        dname = self.fields["ship_to"].get().strip() if "ship_to" in self.fields else ""

        ckey = ""
        dkey = ""
        if hasattr(self, "customer_info") and self.customer_info:
            ckey = self.customer_info.get_customer_key(cname, dname)
            dkey = self.customer_info.get_destination_key(cname, dname)

        if hasattr(self, "customer_code_entry") and self.customer_code_entry.winfo_exists():
            self.customer_code_entry.configure(state="normal")
            self.customer_code_entry.delete(0, "end")
            if ckey:
                self.customer_code_entry.insert(0, ckey)
            self.customer_code_entry.configure(state="readonly")

        if hasattr(self, "ship_to_code_entry") and self.ship_to_code_entry.winfo_exists():
            self.ship_to_code_entry.configure(state="normal")
            self.ship_to_code_entry.delete(0, "end")
            if dkey:
                self.ship_to_code_entry.insert(0, dkey)
            self.ship_to_code_entry.configure(state="readonly")

    def focus_first(self):
        self.fields["customer_name"].focus_set()

    def submit(self):
        if self.error_field is not None:
            self.error_field.configure(border_color=self.colors["border"])
            self.error_field = None
        header = {}
        for key in ("customer_name", "ship_to", "purchase_order"):
            header[key] = self.fields[key].get()
        if hasattr(self, "customer_code_entry") and self.customer_code_entry.winfo_exists():
            header["customer_code"] = self.customer_code_entry.get().strip()
        if hasattr(self, "ship_to_code_entry") and self.ship_to_code_entry.winfo_exists():
            header["ship_to_code"] = self.ship_to_code_entry.get().strip()
        if hasattr(self, "address_box") and self.address_box.winfo_exists():
            header["address"] = self.address_box.get("1.0", "end-1c").strip()
        for key in ("required_date", "due_date"):
            header[key] = self.fields[key].value
        for key in ("remarks", "so_comment"):
            header[key] = self.fields[key].get("1.0", "end-1c")
        rows = [{key: widget.get() for key, widget in row.items()} for row in self.item_entries]
        try:
            payload = collect_order(header, rows)
        except OrderValidationError as exc:
            self.error_label.configure(text=str(exc))
            self.error_label.grid()
            field = self.fields.get(exc.field)
            if field is not None:
                field.focus_set()
                if not isinstance(field, DateField):
                    self.error_field = field
                    field.configure(border_color=self.colors["error"])
            return
        self.error_label.grid_remove()
        self.on_submit(payload)

    def reset_fields(self):
        """Required Date と Due date 以外のすべての入力欄をクリア・リセット"""
        self.close_popups()

        if self.error_field is not None:
            self.error_field.configure(border_color=self.colors["border"])
            self.error_field = None
        self.error_label.grid_remove()

        # 顧客名
        if "customer_name" in self.fields:
            self.fields["customer_name"].set("")
        if hasattr(self, "customer_code_entry") and self.customer_code_entry.winfo_exists():
            self.customer_code_entry.configure(state="normal")
            self.customer_code_entry.delete(0, "end")
            self.customer_code_entry.configure(state="readonly")

        # 納品先
        if "ship_to" in self.fields:
            self.fields["ship_to"].set("")
            self.fields["ship_to"].configure(values=[""])
        if hasattr(self, "ship_to_code_entry") and self.ship_to_code_entry.winfo_exists():
            self.ship_to_code_entry.configure(state="normal")
            self.ship_to_code_entry.delete(0, "end")
            self.ship_to_code_entry.configure(state="readonly")

        # 住所
        self._display_address("")

        # ※ Required Date と Due date はクリアせずそのまま保持

        # Purchase Order
        if "purchase_order" in self.fields:
            self.fields["purchase_order"].delete(0, "end")

        # Remarks & SO comment
        if "remarks" in self.fields:
            self.fields["remarks"].delete("1.0", "end")
        if "so_comment" in self.fields:
            self.fields["so_comment"].delete("1.0", "end")

        # 明細テーブル（品名、幅、長さ、数量、単価）
        for row in getattr(self, "item_entries", []):
            for key, widget in row.items():
                if key == "product_name":
                    widget.set("")
                else:
                    widget.delete(0, "end")

        # 品名Value表示行
        for desc_entry in getattr(self, "item_desc_entries", []):
            desc_entry.configure(state="normal")
            desc_entry.delete(0, "end")
            desc_entry.configure(state="readonly")

        try:
            self.focus_first()
        except Exception:
            pass


def show_order_output(parent, payload, colors, font_family):
    """Default local output; replace the app's handler when QAD logic is defined."""
    window = ctk.CTkToplevel(parent)
    window.title("注文入力内容")
    window.geometry("640x520")
    window.minsize(480, 360)
    window.transient(parent)
    window.configure(fg_color=colors["panel"])
    text = ctk.CTkTextbox(window, font=(font_family, 14), fg_color=colors["panel"],
                         text_color=colors["text"], wrap="word")
    text.pack(fill="both", expand=True, padx=16, pady=16)
    lines = []
    for key, label in (("customer_name", "顧客名"), ("ship_to", "納品先"),
                       ("required_date", "Required date"), ("due_date", "Due date"),
                       ("purchase_order", "Purchase Order"), ("remarks", "Remarks"),
                       ("so_comment", "SO comment")):
        value = payload[key]
        if key in ("required_date", "due_date"):
            value = format_order_date(date.fromisoformat(value))
        lines.append(f"{label}：{value}")
    for number, item in enumerate(payload["items"], 1):
        lines.append(f"\n{number}. {item['product_name']}")
        lines.append("    " + "   /   ".join(f"{label}：{item[key]}" for key, label in zip(ITEM_FIELDS[1:], ITEM_LABELS[1:])))
    text.insert("1.0", "\n".join(lines))
    text.configure(state="disabled")
    return window


def get_default_demo_payload() -> dict:
    """デモ用の既定注文Payload（Request Date: 今日から2日後、Due Date: 明日）"""
    today = date.today()
    due_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    req_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    return {
        "customer_name": "TOPPANインフォメディア株式会社",
        "ship_to": "TOPPANインフォメディア(株)福島工場",
        "purchase_order": "test",
        "customer_code": "20000600",
        "ship_to_code": "20000601",
        "address": "960-8201\nTOPPANインフォメディア(株)福島工場\n福島県福島市岡島字宮田30-2\n\n\n024-536-6111",
        "remarks": "test",
        "so_comment": "test",
        "required_date": req_date,
        "due_date": due_date,
        "items": [
            {
                "product_name": "BW0100D",
                "width": "200",
                "length": "600",
                "quantity": 1,
                "price": "200",
            },
            {
                "product_name": "BW0116Q3-2",
                "width": "200",
                "length": "600",
                "quantity": 1,
                "price": "200",
            },
        ],
    }


_ACTIVE_DEMO_PAYLOAD = None


def get_active_demo_payload() -> dict:
    """現在アクティブなデモPayload（未設定時は既定値を初期化して返却）"""
    global _ACTIVE_DEMO_PAYLOAD
    if _ACTIVE_DEMO_PAYLOAD is None:
        _ACTIVE_DEMO_PAYLOAD = get_default_demo_payload()
    return _ACTIVE_DEMO_PAYLOAD


def set_active_demo_payload(payload: dict):
    """アクティブなデモPayloadを更新"""
    global _ACTIVE_DEMO_PAYLOAD
    if isinstance(payload, dict):
        _ACTIVE_DEMO_PAYLOAD = dict(payload)


class DemoPayloadDialog(ctk.CTkToplevel):
    """デモ用注文送信データ（JSON）の設定・編集ダイアログ"""

    def __init__(self, master=None, current_payload=None, on_save=None, on_execute=None):
        super().__init__(master)
        self.title("⚙️ デモ注文送信データの設定・編集")
        self.geometry("640x580")
        self.minsize(520, 440)
        self.on_save = on_save
        self.on_execute = on_execute

        # モーダル化
        self.transient(master)
        self.grab_set()

        payload = current_payload or get_active_demo_payload()
        self._initial_payload = payload

        # 上部説明
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="デモ注文Payloadの編集",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            anchor="w",
        )
        title_lbl.pack(fill="x")

        desc_lbl = ctk.CTkLabel(
            header_frame,
            text="デモ送信でQADに送るJSONデータを編集できます。\n[📅 日付を今日基準に更新] を押すと、Due Date(明日)・Request Date(2日後)に自動設定されます。",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="#94A3B8",
            justify="left",
            anchor="w",
        )
        desc_lbl.pack(fill="x", pady=(2, 0))

        # アクションバー
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=4)

        btn_date = ctk.CTkButton(
            action_bar,
            text="📅 日付を更新 (Due:明日, Req:2日後)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            height=28,
            command=self._update_dates_to_relative,
        )
        btn_date.pack(side="left", padx=(0, 6))

        btn_reset = ctk.CTkButton(
            action_bar,
            text="🔄 既定値に戻す",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color="#475569",
            hover_color="#334155",
            height=28,
            command=self._reset_to_default,
        )
        btn_reset.pack(side="left", padx=(0, 6))

        btn_format = ctk.CTkButton(
            action_bar,
            text="🪄 JSON整形",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color="#475569",
            hover_color="#334155",
            height=28,
            command=self._format_json,
        )
        btn_format.pack(side="left", padx=(0, 6))

        # JSONテキストエディタ
        self.text_editor = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            wrap="none",
            border_width=1,
            corner_radius=6,
        )
        self.text_editor.pack(fill="both", expand=True, padx=16, pady=6)
        self.text_editor.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))

        # 下部ボタンバー
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=16, pady=(6, 12))

        btn_cancel = ctk.CTkButton(
            bottom_bar,
            text="キャンセル",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color="#64748B",
            hover_color="#475569",
            width=90,
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=(6, 0))

        btn_save = ctk.CTkButton(
            bottom_bar,
            text="💾 保存して閉じる",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            width=130,
            command=self._on_save_clicked,
        )
        btn_save.pack(side="right", padx=(6, 0))

        btn_send = ctk.CTkButton(
            bottom_bar,
            text="🚀 保存してデモ送信",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color="#4F46E5",
            hover_color="#4338CA",
            width=150,
            command=self._on_send_clicked,
        )
        btn_send.pack(side="right", padx=(6, 0))

    def _get_payload_from_editor(self) -> dict:
        raw_text = self.text_editor.get("1.0", "end-1c").strip()
        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError("JSONのルートはオブジェクト({})である必要があります")
            return data
        except Exception as e:
            messagebox.showerror("JSONエラー", f"JSONの解析に失敗しました:\n{e}", parent=self)
            return None

    def _update_dates_to_relative(self):
        data = self._get_payload_from_editor()
        if not data:
            return
        today = date.today()
        data["due_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        data["required_date"] = (today + timedelta(days=2)).strftime("%Y-%m-%d")
        self.text_editor.delete("1.0", "end")
        self.text_editor.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

    def _reset_to_default(self):
        def_data = get_default_demo_payload()
        self.text_editor.delete("1.0", "end")
        self.text_editor.insert("1.0", json.dumps(def_data, ensure_ascii=False, indent=2))

    def _format_json(self):
        data = self._get_payload_from_editor()
        if not data:
            return
        self.text_editor.delete("1.0", "end")
        self.text_editor.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

    def _on_save_clicked(self):
        data = self._get_payload_from_editor()
        if not data:
            return
        set_active_demo_payload(data)
        if callable(self.on_save):
            self.on_save(data)
        messagebox.showinfo("保存完了", "デモ注文データを更新しました。", parent=self)
        self.destroy()

    def _on_send_clicked(self):
        data = self._get_payload_from_editor()
        if not data:
            return
        set_active_demo_payload(data)
        if callable(self.on_save):
            self.on_save(data)
        if callable(self.on_execute):
            self.on_execute(data)
        self.destroy()


class SleepRateDialog(ctk.CTkToplevel):
    """受注自動化のSleep時間倍率（1%〜200%）を設定・調整するダイアログ"""

    def __init__(self, master=None, current_rate=None, on_save=None):
        super().__init__(master)
        self.title("⏱️ 受注Sleep時間の調整 (1%〜200%)")
        self.geometry("520x460")
        self.minsize(460, 400)
        self.on_save = on_save

        # モーダル化
        self.transient(master)
        self.grab_set()

        initial_val = current_rate if current_rate is not None else get_active_sleep_rate_percent()
        try:
            self._current_val = int(round(float(initial_val)))
        except (ValueError, TypeError):
            self._current_val = 100
        self._current_val = max(1, min(200, self._current_val))

        # ウィンドウを親の中央に配置
        try:
            if master:
                px = master.winfo_rootx()
                py = master.winfo_rooty()
                pw = master.winfo_width()
                ph = master.winfo_height()
                x = px + max(0, (pw - 520) // 2)
                y = py + max(0, (ph - 460) // 2)
                self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        # 上部ヘッダー
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            header,
            text="⚡ 受注Sleep時間の調整",
            font=ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
            anchor="w",
        ).pack(fill="x")

        desc_text = (
            "現在の設定（限界見極めテスト用待機時間）を 100%（基準）として、\n"
            "全工程のSleep時間を 1% 〜 200% の範囲で自在に調整できます。\n"
            "（例: 50% ➔ 待機時間半減・約2倍速 / 200% ➔ 待機時間2倍・安全モード）"
        )
        ctk.CTkLabel(
            header,
            text=desc_text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#94A3B8",
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        # メインカード枠
        card = ctk.CTkFrame(self, fg_color=("#F1F5F9", "#1E293B"), corner_radius=10)
        card.pack(fill="both", expand=True, padx=20, pady=8)

        # 現在値の大型表示枠
        rate_display_frame = ctk.CTkFrame(card, fg_color="transparent")
        rate_display_frame.pack(fill="x", padx=16, pady=(14, 4))

        self.lbl_rate_big = ctk.CTkLabel(
            rate_display_frame,
            text=f"{self._current_val} %",
            font=ctk.CTkFont(family=FONT_FAMILY, size=30, weight="bold"),
            text_color="#38BDF8",
        )
        self.lbl_rate_big.pack(side="left")

        self.lbl_speed_ratio = ctk.CTkLabel(
            rate_display_frame,
            text=self._calc_speed_text(self._current_val),
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color="#10B981",
        )
        self.lbl_speed_ratio.pack(side="left", padx=12, pady=(6, 0))

        # スライダー枠
        slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(6, 8))

        ctk.CTkLabel(slider_frame, text="1%", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color="#64748B").pack(side="left")

        self.slider = ctk.CTkSlider(
            slider_frame,
            from_=1,
            to=200,
            number_of_steps=199,
            command=self._on_slider_change,
        )
        self.slider.set(self._current_val)
        self.slider.pack(side="left", fill="x", expand=True, padx=8)

        ctk.CTkLabel(slider_frame, text="200%", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color="#64748B").pack(side="left")

        # プリセットボタン枠
        presets_frame = ctk.CTkFrame(card, fg_color="transparent")
        presets_frame.pack(fill="x", padx=16, pady=(4, 8))

        ctk.CTkLabel(
            presets_frame,
            text="ワンクリックプリセット:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="#94A3B8",
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        btn_row1 = ctk.CTkFrame(presets_frame, fg_color="transparent")
        btn_row1.pack(fill="x", pady=2)

        presets = [
            ("10% (超超特急)", 10, "#EF4444"),
            ("25% (4倍速)", 25, "#F59E0B"),
            ("50% (2倍速)", 50, "#3B82F6"),
            ("75% (高速)", 75, "#06B6D4"),
            ("100% (基準)", 100, "#10B981"),
            ("150% (安定)", 150, "#8B5CF6"),
            ("200% (超安全)", 200, "#64748B"),
        ]

        for text, val, col in presets:
            btn = ctk.CTkButton(
                btn_row1,
                text=text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
                height=26,
                fg_color=col,
                hover_color="#1E293B",
                command=lambda v=val: self._apply_preset(v),
            )
            btn.pack(side="left", padx=2, expand=True, fill="x")

        # 目安プレビュー枠
        preview_box = ctk.CTkFrame(card, fg_color=("#E2E8F0", "#0F172A"), corner_radius=6)
        preview_box.pack(fill="x", padx=16, pady=(6, 12))

        self.lbl_preview = ctk.CTkLabel(
            preview_box,
            text=self._calc_preview_text(self._current_val),
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color="#E2E8F0",
            justify="left",
            anchor="w",
        )
        self.lbl_preview.pack(fill="x", padx=10, pady=8)

        # 下部アクションボタン
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(8, 16))

        btn_save = ctk.CTkButton(
            footer,
            text="💾 保存して閉じる",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            height=34,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._on_save_clicked,
        )
        btn_save.pack(side="right", padx=(6, 0))

        btn_cancel = ctk.CTkButton(
            footer,
            text="キャンセル",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            height=34,
            fg_color="#64748B",
            hover_color="#475569",
            command=self.destroy,
        )
        btn_cancel.pack(side="right", padx=6)

        btn_reset = ctk.CTkButton(
            footer,
            text="↺ 100% (基準値) に戻す",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            height=34,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=lambda: self._apply_preset(100),
        )
        btn_reset.pack(side="left")

    def _calc_speed_text(self, val: int) -> str:
        if val == 100:
            return "（基準速度 1.0倍）"
        elif val < 100:
            speed = 100.0 / max(1, val)
            return f"（約 {speed:.1f} 倍速・短縮）"
        else:
            slow = val / 100.0
            return f"（約 {slow:.1f} 倍待機・安全）"

    def _calc_preview_text(self, val: int) -> str:
        scale = val / 100.0
        return (
            f"主要待機時間の目安 [Sleep {val}%]:\n"
            f"  ・Step 5➔6 明細画面遷移: {0.35 * scale:.3f}秒 (基準: 0.35s)\n"
            f"  ・ロール明細入力 (Ser/幅): {0.12 * scale:.3f}秒 (基準: 0.12s)\n"
            f"  ・ヘッダー確定/一括貼付:  {0.35 * scale:.3f}秒 (基準: 0.35s)\n"
            f"  ・最終コミット (Totals):   {0.30 * scale:.3f}秒 (基準: 0.30s)"
        )

    def _on_slider_change(self, val):
        self._current_val = int(round(float(val)))
        self._update_ui()

    def _apply_preset(self, val: int):
        self._current_val = max(1, min(200, int(val)))
        self.slider.set(self._current_val)
        self._update_ui()

    def _update_ui(self):
        self.lbl_rate_big.configure(text=f"{self._current_val} %")
        self.lbl_speed_ratio.configure(text=self._calc_speed_text(self._current_val))
        self.lbl_preview.configure(text=self._calc_preview_text(self._current_val))

    def _on_save_clicked(self):
        set_active_sleep_rate_percent(self._current_val)
        if callable(self.on_save):
            self.on_save(self._current_val)
        self.destroy()


class OrderOutputTerminalWindow(ctk.CTkToplevel):
    """F3で表示される注文送信チェック用シークレットターミナル"""

    def __init__(self, parent, colors=None, font_family=None, on_close=None):
        super().__init__(parent)
        self.parent = parent
        self.on_close = on_close
        self.submission_count = 0
        self.font_family = font_family or FONT_FAMILY

        # ターミナル風カラーパレット
        self.term_bg = "#0A0E17"
        self.term_card_bg = "#111827"
        self.term_fg = "#E2E8F0"
        self.term_border = "#1F2937"
        self.term_cyan = "#38BDF8"
        self.term_green = "#34D399"
        self.term_yellow = "#FBBF24"
        self.term_dim = "#64748B"
        self.term_purple = "#C084FC"
        self.last_payload = None

        self.title("QAD 送信出力チェック ターミナル [F3]")
        self.geometry("880x620")
        self.minsize(580, 400)
        self.configure(fg_color=self.term_bg)
        self.transient(parent)

        # ウィンドウを画面中央付近に配置
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = max(20, px + (pw - 880) // 2)
            y = max(20, py + (ph - 620) // 2)
            self.geometry(f"880x620+{x}+{y}")
        except Exception:
            pass

        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        # 上部ステータスバー（ターミナル風プロンプト）
        top_bar = ctk.CTkFrame(self, fg_color=self.term_card_bg, corner_radius=0, height=36)
        top_bar.pack(fill="x", side="top")
        top_bar.pack_propagate(False)

        self.title_label = ctk.CTkLabel(
            top_bar,
            text=" >_ OUTPUT CHECK TERMINAL [F3 SECRET MODE]",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=self.term_cyan,
            anchor="w",
        )
        self.title_label.pack(side="left", padx=12, pady=6)

        self.count_label = ctk.CTkLabel(
            top_bar,
            text="Submissions: 0",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=self.term_dim,
            anchor="e",
        )
        self.count_label.pack(side="right", padx=12, pady=6)

        self.execute_btn = ctk.CTkButton(
            top_bar,
            text="🚀 QAD自動入力を実行",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            text_color="#FFFFFF",
            height=26,
            corner_radius=5,
            command=self._on_execute_clicked,
        )
        self.execute_btn.pack(side="right", padx=(4, 8), pady=5)

        self.demo_btn = ctk.CTkButton(
            top_bar,
            text="🧪 デモ注文送信 (2製品)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            fg_color="#4F46E5",
            hover_color="#4338CA",
            text_color="#FFFFFF",
            height=26,
            corner_radius=5,
            command=self._on_demo_clicked,
        )
        self.demo_btn.pack(side="right", padx=(4, 4), pady=5)

        self.demo_cfg_btn = ctk.CTkButton(
            top_bar,
            text="⚙️ デモ設定",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color="#374151",
            hover_color="#4B5563",
            text_color="#FFFFFF",
            width=75,
            height=26,
            corner_radius=5,
            command=self._on_demo_cfg_clicked,
        )
        self.demo_cfg_btn.pack(side="right", padx=(4, 6), pady=5)

        # 下部キーガイドバー
        bottom_bar = ctk.CTkFrame(self, fg_color=self.term_card_bg, corner_radius=0, height=28)
        bottom_bar.pack(fill="x", side="bottom")
        bottom_bar.pack_propagate(False)

        guide_label = ctk.CTkLabel(
            bottom_bar,
            text=" [F3 / Esc]: 閉じる   [Ctrl+A]: 全選択   [Ctrl+C]: コピー   [Ctrl+L]: ログクリア",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=self.term_dim,
            anchor="w",
        )
        guide_label.pack(side="left", padx=10, pady=4)

        # メインテキストボックス（ターミナル風）
        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            fg_color=self.term_bg,
            text_color=self.term_fg,
            wrap="none",
            corner_radius=0,
            border_width=0,
        )
        self.textbox.pack(fill="both", expand=True, padx=4, pady=4)

        # Tkinter Text タグ設定（シンタックスハイライト）
        tb = self.textbox._textbox
        tb.tag_config("term_header", foreground=self.term_cyan, font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_section", foreground=self.term_yellow, font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_label", foreground=self.term_green, font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_val", foreground=self.term_fg, font=(FONT_FAMILY, 12))
        tb.tag_config("term_dim", foreground=self.term_dim, font=(FONT_FAMILY, 12))
        tb.tag_config("term_json", foreground=self.term_purple, font=(FONT_FAMILY, 11))
        tb.tag_config("term_item_title", foreground="#38BDF8", font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_item_desc", foreground="#FCD34D", font=(FONT_FAMILY, 12))
        tb.tag_config("term_step", foreground="#38BDF8", font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_key", foreground="#F59E0B", font=(FONT_FAMILY, 12, "bold"))
        tb.tag_config("term_paste", foreground="#34D399", font=(FONT_FAMILY, 12))
        tb.tag_config("term_comment", foreground="#94A3B8", font=(FONT_FAMILY, 11))

    def _on_demo_clicked(self):
        """設定済みのデモPayload（日付が過去なら今日基準に自動補正）で送信ボタン押下時と同一の挙動を実行"""
        demo_payload = get_active_demo_payload()
        # 日付が過去日の場合は自動的に今日基準（Due:明日, Req:2日後）に更新
        today = date.today()
        try:
            curr_due = datetime.strptime(str(demo_payload.get("due_date", "")).strip(), "%Y-%m-%d").date()
            if curr_due <= today:
                demo_payload["due_date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                demo_payload["required_date"] = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                set_active_demo_payload(demo_payload)
        except Exception:
            pass

        target_parent = getattr(self, "parent", None) or getattr(self, "master", None)
        items_data = None
        if hasattr(target_parent, "order_panel") and target_parent.order_panel is not None:
            items_data = getattr(target_parent.order_panel, "item_list_data", None)

        # ターミナル画面上にデモ注文内容を表示・記録
        self.append_submission(demo_payload, item_list_data=items_data)

        # サイドバー送信ボタン押下時と同一の挙動（履歴記録＆自動入力実行）
        if hasattr(target_parent, "_process_order_submission"):
            target_parent._process_order_submission(demo_payload)
        elif hasattr(target_parent, "run_sales_order_automation"):
            target_parent.run_sales_order_automation(demo_payload)
        else:
            messagebox.showwarning("警告", "メインアプリに注文送信機能が見つかりません。", parent=self)

    def _on_demo_cfg_clicked(self):
        """デモ注文データ編集ダイアログを開く"""
        target_parent = getattr(self, "parent", None) or getattr(self, "master", None)
        DemoPayloadDialog(
            master=self,
            current_payload=get_active_demo_payload(),
            on_save=lambda p: getattr(target_parent, "save_demo_payload", lambda x: None)(p),
            on_execute=lambda p: self._on_demo_clicked(),
        )

    def _on_execute_clicked(self):
        if not self.last_payload:
            messagebox.showinfo("案内", "送信された注文データがありません。サイドバーで注文を入力してから実行するか、[🧪 デモ注文送信] を押してください。", parent=self)
            return
        target_parent = getattr(self, "parent", None) or getattr(self, "master", None)
        if hasattr(target_parent, "run_sales_order_automation"):
            target_parent.run_sales_order_automation(self.last_payload)
        else:
            messagebox.showwarning("警告", "メインアプリに注文自動入力機能が見つかりません。", parent=self)

    def _bind_keys(self):
        self.bind("<KeyPress-F3>", lambda e: self.close())
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Control-l>", lambda e: self.clear_terminal())
        self.bind("<Control-L>", lambda e: self.clear_terminal())
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-A>", self._select_all)

    def _select_all(self, event=None):
        try:
            self.textbox._textbox.tag_add("sel", "1.0", "end")
            return "break"
        except Exception:
            pass

    def show_empty_message(self):
        tb = self.textbox._textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.insert("end", "=" * 80 + "\n", "term_dim")
        tb.insert("end", " QAD ORDER OUTPUT CHECK TERMINAL  [SECRET DEBUG MODE]\n", "term_header")
        tb.insert("end", "=" * 80 + "\n\n", "term_dim")
        tb.insert("end", " [INFO] まだ送信された注文データはありません。\n\n", "term_label")
        tb.insert("end", " ・F2キーで注文入力サイドバーを開き、注文内容を入力して「送信」ボタンを押してください。\n", "term_val")
        tb.insert("end", " ・送信が実行されると、ここに出力内容（ヘッダー・明細・RAW JSON）が自動的に表示されます。\n", "term_val")
        tb.insert("end", " ・この画面は [F3] キーまたは [Esc] キーでいつでも開閉できます。\n\n", "term_dim")
        tb.insert("end", "-" * 80 + "\n", "term_dim")
        tb.configure(state="disabled")

    def append_submission(self, payload, item_list_data=None):
        self.submission_count += 1
        self.last_payload = payload
        self.count_label.configure(text=f"Submissions: {self.submission_count}")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tb = self.textbox._textbox
        tb.configure(state="normal")

        # 最初の1件目の場合、初期メッセージを消去
        if self.submission_count == 1:
            tb.delete("1.0", "end")

        sep = "=" * 80 + "\n"
        sub_sep = "-" * 80 + "\n"

        tb.insert("end", sep, "term_dim")
        tb.insert("end", f" [SUBMISSION #{self.submission_count}]  Timestamp: {now_str}\n", "term_header")
        tb.insert("end", sep, "term_dim")

        # ヘッダー項目
        tb.insert("end", "\n [HEADER FIELDS]\n", "term_section")
        header_map = [
            ("customer_name", "Customer Name (顧客名)   "),
            ("customer_code", "Customer Code (顧客コード) "),
            ("ship_to",       "Ship To       (納品先)   "),
            ("ship_to_code",  "Ship To Code  (納品先コード)"),
            ("address",       "Address       (住所)     "),
            ("required_date", "Required Date (要求納期) "),
            ("due_date",      "Due Date      (回答納期) "),
            ("purchase_order","Purchase Order(注文番号) "),
            ("remarks",       "Remarks       (備考)     "),
            ("so_comment",    "SO Comment    (特記事項) "),
        ]
        for key, label in header_map:
            val = payload.get(key, "")
            if key in ("required_date", "due_date") and val:
                try:
                    val = f"{val} ({format_order_date(date.fromisoformat(str(val)))})"
                except Exception:
                    pass
            tb.insert("end", f"   {label}: ", "term_label")
            tb.insert("end", f"{val}\n", "term_val")

        # -------------------------------------------------------------
        # QAD 99.7.1.1 キーストローク＆貼り付けシミュレーション（Step 1 〜 Step 5）
        # -------------------------------------------------------------
        tb.insert("end", "\n [QAD 99.7.1.1 AUTOMATION SCRIPT / KEYSTROKE SIMULATION (STEP 1 - STEP 5)]\n", "term_section")
        tb.insert("end", " " + "-" * 78 + "\n", "term_dim")
        tb.insert("end", " ※この表示は送信予定の説明で、サーバー応答や登録結果の検証ではありません。\n", "term_comment")
        tb.insert("end", " ※注文入力の「送信」およびこの画面の実行ボタンは、サーバーへ実送信します。\n", "term_comment")
        tb.insert("end", " " + "-" * 78 + "\n\n", "term_dim")

        c_code = str(payload.get("customer_code", "")).strip()
        s_code = str(payload.get("ship_to_code", "")).strip()
        so_comm = str(payload.get("so_comment", "")).strip()

        # Step 1
        tb.insert("end", " >> [STEP 1] メインメニュー -> 99.7.1.1 遷移 ＆ 新規Order番号自動採番\n", "term_step")
        tb.insert("end", "   1-1. メインメニューから画面遷移: ", "term_label")
        tb.insert("end", "99.7.1.1 + <Enter>\n", "term_key")
        tb.insert("end", "        コメント: QADメインメニュー(mfmenu)から 99.7.1.1 を送信して受注登録画面へ移動\n", "term_comment")
        tb.insert("end", "   1-2. Order番号入力欄: ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 【指標A】Order欄は空のまま F1 を押して最新のOrder IDを自動採番\n", "term_comment")
        tb.insert("end", "        動作確認: 採番完了後、カーソルは自動的に Sold-To 欄(Row 3, Col 29)へ移動\n\n", "term_comment")

        # Step 2
        tb.insert("end", " >> [STEP 2] 受注ヘッダー項目入力（Sold-To/Bill-To/Ship-To 個別入力 ＋ Order Date から一括貼り付け）\n", "term_step")
        tb.insert("end", "   2-1. Sold-To 順次入力: ", "term_label")
        tb.insert("end", f"{c_code} + <Enter> ➔ <F1>\n", "term_key")
        tb.insert("end", "        注意点  : F1送信後に 'Category=... Press space bar' 警告が出た場合は <Space> で続行し Bill-To をアクティブ化\n", "term_comment")
        tb.insert("end", "   2-2. Bill-To 順次入力: ", "term_label")
        tb.insert("end", f"{c_code} + <Enter>\n", "term_key")
        tb.insert("end", "        コメント: Sold-To と同一の顧客コードを入力\n", "term_comment")
        tb.insert("end", "   2-3. Ship-To 順次入力: ", "term_label")
        tb.insert("end", f"{s_code} + <Enter>\n", "term_key")
        tb.insert("end", "        動作確認: 送信後、カーソルが Order Date 欄へ着地したことを確認\n\n", "term_comment")

        tb.insert("end", "   2-4. 一括貼り付けバッファ（Order Date 入力欄から一括ペースト・全8項目）:\n", "term_label")

        # 貼り付けバッファの構築 (Order Date からの全8項目)
        paste_items = list(zip(build_order_header_fields(payload), [
            "Line 1 : Order Date (当日日付 MM/dd/yy)",
            "Line 2 : Required Date (要求納期 MM/dd/yy)",
            "Line 3 : Promise Date (Enterでスキップ)",
            "Line 4 : Due Date (回答納期 MM/dd/yy)",
            "Line 5 : Perform Date (Enterでスキップ)",
            "Line 6 : Pricing Date (Enterでスキップ ★必須)",
            "Line 7 : Purchase Order (注文番号)",
            "Line 8 : Remarks (備考)",
        ]))
        paste_raw = "\n".join(val for val, _ in paste_items)

        tb.insert("end", "   +" + "-" * 68 + "+\n", "term_dim")
        for val, desc in paste_items:
            disp_val = f'"{val}"' if val else '(空行: Enterスキップ)'
            tb.insert("end", f"   | {desc:<52} -> ", "term_dim")
            tb.insert("end", f"{disp_val}\n", "term_paste")
        tb.insert("end", "   +" + "-" * 68 + "+\n\n", "term_dim")

        tb.insert("end", "   2-5. 【手動テスト用】一括貼り付けRAWテキスト (改行区切り):\n", "term_label")
        tb.insert("end", "        (表示用はLF区切り。実送信はCR区切りで、末尾のEnterは追加せずF1で確定します)\n", "term_comment")
        tb.insert("end", "   ```\n" + paste_raw + "\n   ```\n\n", "term_json")

        tb.insert("end", "   2-6. ヘッダー画面確定キー送信: ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 一括貼り付け完了後、F1キー(Go)を押してヘッダーを確定\n", "term_comment")
        tb.insert("end", "        注意点  : 画面下に 'Category=... Press space bar to continue.' が出た場合は <Space> で続行\n\n", "term_comment")

        # Step 3
        tb.insert("end", " >> [STEP 3] 税金設定ポップアップ (Tax Information)\n", "term_step")
        tb.insert("end", "   3-1. ポップアップ通過キー送信: ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 【指標C】Tax Usage等のポップアップは何も変更せず F1 でスキップ\n\n", "term_comment")

        # Step 4
        tb.insert("end", " >> [STEP 4] ヘッダー追加画面 (Salesperson / Freight 等)\n", "term_step")
        tb.insert("end", "   4-1. 追加画面通過キー送信: ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 【指標C】Salesperson / Freight 画面は何も変更せず F1 でスキップ\n\n", "term_comment")

        # Step 5
        tb.insert("end", " >> [STEP 5] 特記事項 (Transaction Comments / 案C: 全クリア置換)\n", "term_step")
        if so_comm:
            comm_lines = so_comm.splitlines()
            tb.insert("end", f"   5-1. コメント入力欄に入る: ", "term_label")
            tb.insert("end", "<F1>\n", "term_key")
            tb.insert("end", "        コメント: F1を押してコメント本文エディタへ移動（カーソル: Row 6, Col 3）\n", "term_comment")
            tb.insert("end", f"   5-2. 既定コメントの全クリア (案C): ", "term_label")
            tb.insert("end", "<F8> (Clear)\n", "term_key")
            tb.insert("end", "        コメント: 得意先マスターの既定コメントを全消去して新規コメントのみに置換\n", "term_comment")
            tb.insert("end", f"   5-3. 新規特記事項本文を入力 (全 {len(comm_lines)} 行):\n", "term_label")
            for idx, c_line in enumerate(comm_lines, 1):
                tb.insert("end", f"        Line {idx:02d}: ", "term_dim")
                tb.insert("end", f"{c_line}\n", "term_val")
            tb.insert("end", "   5-4. コメント確定キー送信: ", "term_label")
            tb.insert("end", "<F1>\n", "term_key")
            tb.insert("end", "        コメント: F1を押すと帳票印字ポップアップ ('Print On Quote:') が表示される\n", "term_comment")
            tb.insert("end", "   5-5. 'Print On Quote:' 確定キー送信: ", "term_label")
            tb.insert("end", "<F1>\n", "term_key")
            tb.insert("end", "        コメント: 何も入力せずにF1を押す（最初の入力欄にカーソルが復帰）\n", "term_comment")
            tb.insert("end", "   5-6. 次のステップ（明細）へ進む: ", "term_label")
            tb.insert("end", "<F4>\n", "term_key")
            tb.insert("end", "        コメント: F4キーを押して次のステップ（明細画面）へ進む\n\n", "term_comment")
        else:
            tb.insert("end", "   5-1. コメントなし（スキップ）: ", "term_label")
            tb.insert("end", "<F4>\n", "term_key")
            tb.insert("end", "        コメント: 特記事項がないため、F4キーを押してそのまま次のステップへ進む\n\n", "term_comment")

        # Step 6
        items = payload.get("items", [])
        grouped_products = group_order_items(items)

        if not grouped_products:
            tb.insert("end", " >> [STEP 6] 受注明細行 (Line Items / 明細データなし)\n", "term_step")
            tb.insert("end", "   コメント: 明細データが存在しないため明細入力をスキップします。\n\n", "term_comment")
        else:
            tb.insert("end", f" >> [STEP 6] 受注明細行入力 (Line Items / 6.1.0 〜 6.2.5 全 {len(grouped_products)} 品番・{len(items)} 明細)\n", "term_step")
            tb.insert("end", "   コメント: 品番ごとにLnを自動採番し、長さ・スリット幅・本数を階層的に登録後、単価を入力します。\n", "term_comment")
            tb.insert("end", "   動作要件: 各工程で画面の表示変化（プロンプト/ポップアップ）を検知して確実にキー送信を行います。\n\n", "term_comment")

            for p_idx, prod in enumerate(grouped_products, 1):
                p_name = prod["product_name"]
                price_val = prod["price"]
                l_groups = prod["length_groups"]

                tb.insert("end", f"   +{'-' * 68}+\n", "term_dim")
                tb.insert("end", f"   | 【品番 {p_idx}/{len(grouped_products)}: {p_name}】 (Line {prod['line_no']})  単価: {price_val} 円\n", "term_item_title")
                tb.insert("end", f"   +{'-' * 68}+\n", "term_dim")

                # 6.1.0 メインメニュー (Ln 採番)
                tb.insert("end", f"   6.1.0-1. Ln 自動採番: ", "term_label")
                tb.insert("end", "<Enter>\n", "term_key")
                tb.insert("end", f"        コメント: Ln欄がアクティブ（ブランク）の状態で Enter を送信し、行番号 ({prod['line_no']}) を自動採番\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Create WO: Y Rework: Y' ポップアップ出現を検知\n", "term_comment")

                # 6.1.1 子メニューNo1
                tb.insert("end", f"   6.1.1-1. Create WO ポップアップ通過: ", "term_label")
                tb.insert("end", "<F1>\n", "term_key")
                tb.insert("end", f"        コメント: 'Create WO: Y Rework: Y Exact: Y' ポップアップを F1 でスキップ\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Item Number' 入力欄がアクティブになるのを検知\n", "term_comment")

                # 6.1.3 子メニューNo3
                tb.insert("end", f"   6.1.3-1. Item Number (品番) 入力: ", "term_label")
                tb.insert("end", f'"{p_name}" + <F1>\n', "term_key")
                tb.insert("end", f"        コメント: 品番 '{p_name}' を入力し、F1キーを押して Site ポップアップを開く\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Site' 入力ポップアップ出現を検知\n", "term_comment")

                tb.insert("end", f"   6.1.3-2. Site (出荷拠点) 入力: ", "term_label")
                tb.insert("end", '"CB2" + <F1>\n', "term_key")
                tb.insert("end", f"        コメント: 出荷拠点 'CB2' を入力し、F1キーで確定して次へ進む\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Qty Ordered UM' がアクティブになるのを検知\n", "term_comment")

                # 6.1.4 子メニューNo4
                tb.insert("end", f"   6.1.4-1. Qty Ordered UM スキップ: ", "term_label")
                tb.insert("end", "<F1>\n", "term_key")
                tb.insert("end", f"        コメント: 平米数は後工程（幅×長さ×本数）から自動計算されるため F1 でスキップ\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Item Width(mm)' / 'SL' スリット設定画面の表示を検知\n\n", "term_comment")

                # スリット設定ループ (Length groups)
                for l_idx, lg in enumerate(l_groups, 1):
                    length_val = lg["length"]
                    sl_no = lg["sl"]
                    entries = lg["entries"]

                    tb.insert("end", f"     [スリット設定 {l_idx}/{len(l_groups)}] 長さ: {length_val}m (サブライン SL {sl_no} / {len(entries)}明細)\n", "term_step")
                    tb.insert("end", f"     6.1.4-SL{sl_no}. サブライン (SL) 取得: ", "term_label")
                    tb.insert("end", "<F1>\n", "term_key")
                    tb.insert("end", f"          コメント: F1キーを押してサブライン (SL {sl_no}) を採番\n", "term_comment")
                    tb.insert("end", f"          画面待機: 'Len(m)' 入力欄がアクティブになるのを検知\n", "term_comment")

                    # 6.2.0 長さ入力
                    tb.insert("end", f"     6.2.0-1. Len(m) (長さ) 入力: ", "term_label")
                    tb.insert("end", f'"{length_val}" + <F1>\n', "term_key")
                    tb.insert("end", f"          コメント: 製品長さ '{length_val}' を入力し、F1キーで次へ進む\n", "term_comment")
                    tb.insert("end", f"          画面待機: 'Ser T Rolls Width(mm)' 入力ポップアップの出現を検知\n", "term_comment")

                    # 6.2.1 ロール（本数・幅）入力
                    for r_idx, ent in enumerate(entries, 1):
                        r_rolls = ent["rolls"]
                        r_width = ent["width"]
                        tb.insert("end", f"     6.2.1-R{r_idx}.1. Ser スキップ: ", "term_label")
                        tb.insert("end", "<F1>\n", "term_key")
                        tb.insert("end", f"          コメント: Ser (連番) は自動採番されるため F1 でスキップして Rolls 欄へ\n", "term_comment")

                        tb.insert("end", f"     6.2.1-R{r_idx}.2. Rolls (本数) 入力: ", "term_label")
                        tb.insert("end", f'"{r_rolls}" + <Enter>\n', "term_key")
                        tb.insert("end", f"          コメント: 本数 '{r_rolls}' を入力して Enter (Width欄へ移動)\n", "term_comment")

                        tb.insert("end", f"     6.2.1-R{r_idx}.3. Width (幅mm) 入力: ", "term_label")
                        tb.insert("end", f'"{r_width}" + <Enter>\n', "term_key")
                        tb.insert("end", f"          コメント: 幅 '{r_width} mm' を入力して Enter (次行のSerへ移動)\n", "term_comment")

                    # ロール入力完了 -> F4 -> Please confirm update -> F1
                    tb.insert("end", f"     6.2.1-End. 長さ {length_val}m ロール入力完了: ", "term_label")
                    tb.insert("end", "<F4>\n", "term_key")
                    tb.insert("end", f"          コメント: 次行のSerがアクティブの状態で F4 を押し、当該長さのロール入力を終了\n", "term_comment")
                    tb.insert("end", f"          画面待機: 'Please confirm update' 確認プロンプトの出現を検知\n", "term_comment")

                    tb.insert("end", f"     6.2.1-Conf. 長さ {length_val}m 更新確定: ", "term_label")
                    tb.insert("end", "<F1>\n", "term_key")
                    tb.insert("end", f"          コメント: 'Please confirm update' に対し初期値 'yes' を F1 で確定\n", "term_comment")
                    tb.insert("end", f"          画面待機: SL一覧画面 (Item Code登録メニューNo1) への復帰を検知\n\n", "term_comment")

                # 全長さ完了 -> F4 -> Please confirm update -> Enter
                tb.insert("end", f"   6.1.4-Done. 品番 '{p_name}' の全スリット設定完了: ", "term_label")
                tb.insert("end", "<F4>\n", "term_key")
                tb.insert("end", f"        コメント: 当該Item Codeの全長さ入力が完了したため SL一覧画面で F4 を送信\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Please confirm update' 確認プロンプトの出現を検知\n", "term_comment")

                tb.insert("end", f"   6.1.4-Conf. スリット明細確定: ", "term_label")
                tb.insert("end", "<Enter>\n", "term_key")
                tb.insert("end", f"        コメント: 'Please confirm update' を Enter (または F1) で確定\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Pricing Date' 画面の表示を検知\n\n", "term_comment")

                # 6.2.3 Pricing Date
                tb.insert("end", f"   6.2.3-1. Pricing Date 画面スキップ: ", "term_label")
                tb.insert("end", "<F1>\n", "term_key")
                tb.insert("end", f"        コメント: Pricing Date ポップアップは何も変更せず F1 でスキップ\n", "term_comment")
                tb.insert("end", f"        画面待機: 'List Price' / 'Price' 値段入力画面の表示を検知\n", "term_comment")

                # 6.2.4 値段入力
                tb.insert("end", f"   6.2.4-1. List Price スキップ: ", "term_label")
                tb.insert("end", "<F1>\n", "term_key")
                tb.insert("end", f"        コメント: List Price がアクティブの状態で F1 を押し、Price 欄へ移動\n", "term_comment")

                tb.insert("end", f"   6.2.4-2. Price (単価) 入力: ", "term_label")
                tb.insert("end", f'"{price_val}" + <F1>\n', "term_key")
                tb.insert("end", f"        コメント: 単価 '{price_val} 円' を入力し、F1キーで確定して次へ進む\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Tax Usage' 税金設定ポップアップの表示を検知\n", "term_comment")

                # 6.2.5 Tax
                tb.insert("end", f"   6.2.5-1. Tax 画面スキップ: ", "term_label")
                tb.insert("end", "<F1>\n", "term_key")
                tb.insert("end", f"        コメント: Tax 設定ポップアップは何も変更せず F1 でスキップ\n", "term_comment")
                tb.insert("end", f"        画面待機: 'Transaction Comments' (明細コメント画面) の表示を検知\n", "term_comment")

                # 6.2.5 コメント
                tb.insert("end", f"   6.2.5-2. Transaction Comments 画面スキップ: ", "term_label")
                tb.insert("end", "<F4>\n", "term_key")
                tb.insert("end", f"        コメント: 明細行コメントは何も入力せず F4 (またはF1) でスキップし、次へ進む\n", "term_comment")

                # Reason Code 対応
                tb.insert("end", f"   6.2.5-3. Reason Code ポップアップ検知・入力 (価格・納期差異時): ", "term_label")
                tb.insert("end", '"65" -> "28" -> "28" + <F1>\n', "term_key")
                tb.insert("end", f"        コメント: 定価差異時は List Price '65'、納期差異時は Req/Promise Date '28'(INTERNAL) を入力し F1 で確定\n\n", "term_comment")

        # -------------------------------------------------------------
        # Step 6.3.0: 最終合計画面遷移＆注文完了
        # -------------------------------------------------------------
        tb.insert("end", " >> [STEP 6.3.0] 受注最終合計画面 (Order Totals) ＆ 注文確定\n", "term_step")
        tb.insert("end", "   6.3.0-1. 次行 Create WO ポップアップ解除 (出現時): ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 新規行で 'Create WO' ポップアップが出現した場合は F1 でスキップ\n", "term_comment")

        tb.insert("end", "   6.3.0-2. 明細脱出シーケンス (Ln -> Ln Format S/M -> Totals 画面): ", "term_label")
        tb.insert("end", "<F4> -> <F4>\n", "term_key")
        tb.insert("end", "        コメント: 空のLn欄で F4 を押して 'Ln Format S/M' 欄へ移動し、再度 F4 を押して Totals 画面へ進む\n", "term_comment")
        tb.insert("end", "        画面待機: 'Line Total:' / 'Total Tax:' / 'Enter data or press F4 to end.' の表示を検知\n", "term_comment")

        tb.insert("end", "   6.3.0-3. 合計画面下段展開 (Frame 2+): ", "term_label")
        tb.insert("end", "<F1>\n", "term_key")
        tb.insert("end", "        コメント: 最終合計画面で F1 を送信し、下段フレーム (Frame 2+) を展開\n", "term_comment")

        tb.insert("end", "   6.3.0-4. 注文コミット＆与信/延滞チェック実行: ", "term_label")
        tb.insert("end", f"<{ORDER_TOTALS_COMMIT_KEY}>\n", "term_key")
        tb.insert("end", f"        コメント: 現行実装は2回目に {ORDER_TOTALS_COMMIT_KEY} を送信。過去ログの F4 手順との差は未解消\n", "term_comment")
        tb.insert("end", "        現行実装: <Space> を1回送信し、追加警告が表示された場合も <Space> で解除\n", "term_comment")

        tb.insert("end", "   6.3.0-5. 初期画面への安全復帰 (全工程完了): ", "term_label")
        tb.insert("end", "合計画面に残っている場合のみ <F4>\n", "term_key")
        tb.insert("end", "        コメント: 初期画面またはメインメニューへの復帰を待機。登録値の照合は別途必要\n\n", "term_comment")

        # 明細項目
        tb.insert("end", f"\n [ORDER ITEMS] (Total: {len(items)} items)\n", "term_section")
        for idx, item in enumerate(items, 1):
            tb.insert("end", sub_sep, "term_dim")
            p_name = item.get("product_name", "")
            desc = ""
            if item_list_data and p_name in item_list_data:
                desc = item_list_data[p_name]

            tb.insert("end", f"  Line {idx:02d} | Product: ", "term_item_title")
            tb.insert("end", f"{p_name}\n", "term_val")
            if desc:
                tb.insert("end", f"          | Description: ", "term_dim")
                tb.insert("end", f"{desc}\n", "term_item_desc")

            details = [
                f"Width: {item.get('width', '')} mm",
                f"Length: {item.get('length', '')} m",
                f"Qty: {item.get('quantity', '')} 本",
                f"Price: {item.get('price', '')} 円",
            ]
            tb.insert("end", "          | " + "   /   ".join(details) + "\n", "term_dim")
        tb.insert("end", sub_sep, "term_dim")

        # RAW JSON
        tb.insert("end", "\n [RAW JSON PAYLOAD]\n", "term_section")
        try:
            json_text = json.dumps(payload, ensure_ascii=False, indent=2)
            tb.insert("end", json_text + "\n", "term_json")
        except Exception as e:
            tb.insert("end", f"JSON Serialize Error: {e}\n", "term_dim")

        tb.insert("end", "\n" + sep + "\n\n", "term_dim")

        tb.configure(state="disabled")
        tb.see("end")

    def clear_terminal(self):
        self.submission_count = 0
        self.count_label.configure(text="Submissions: 0")
        self.show_empty_message()

    def close(self):
        try:
            if self.on_close:
                self.on_close()
            self.destroy()
        except Exception:
            pass

