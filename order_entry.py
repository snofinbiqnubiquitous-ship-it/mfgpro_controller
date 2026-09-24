"""Order entry UI and validation; no network or QAD side effects."""

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import difflib
import io
import json
from pathlib import Path
import re
import tkinter as tk
import unicodedata

import customtkinter as ctk


WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
ITEM_FIELDS = ("product_name", "width", "length", "quantity", "price")
ITEM_LABELS = ("製品名", "巾", "長さ", "本数", "価格")
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
        self.customer_names = []
        self.customer_ship_tos = {}
        self.addresses = {}
        if raw_data:
            self.load(raw_data)

    def load(self, data):
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


def to_katakana(text):
    """ひらがなを全角カタカナに変換"""
    return "".join(chr(ord(c) + 0x60) if "\u3041" <= c <= "\u3096" else c for c in text)


def normalize_for_search(text):
    """NFKC正規化＋全角カタカナ統一＋小文字化で表記揺れを完全吸収"""
    return to_katakana(unicodedata.normalize("NFKC", str(text)).strip().lower())


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
            sim = difflib.SequenceMatcher(None, nq, nc).ratio()
            if sim >= 0.4:
                fuzzy.append((sim, c))

    prefix.sort(key=lambda x: x[0])
    substr.sort(key=lambda x: (x[0], x[1]))
    fuzzy.sort(key=lambda x: -x[0])

    res = exact + [x[1] for x in prefix] + [x[2] for x in substr] + [x[1] for x in fuzzy]
    return list(dict.fromkeys(res))[:limit]


class AutocompletePopup:
    """入力欄（CTkComboBox/Entry）の直下に候補リストを自動ポップアップするコントローラ"""

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

    def set_candidates(self, candidates):
        self.all_candidates = [str(c).strip() for c in candidates if str(c).strip()]

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
        self._show_popup(hits)

    def _show_popup(self, items):
        self._ensure_popup()
        self.filtered_candidates = items
        self.listbox.delete(0, "end")
        for item in items:
            self.listbox.insert("end", f" {item}")
        self._selected_index = -1

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
            new_idx = (self._selected_index + 1) % len(self.filtered_candidates)
            self._apply_selection(new_idx)
            return "break"
        return None

    def _on_up_key(self, event=None):
        if self.is_open() and self.filtered_candidates:
            if self._selected_index <= 0:
                new_idx = len(self.filtered_candidates) - 1
            else:
                new_idx = self._selected_index - 1
            self._apply_selection(new_idx)
            return "break"
        return None

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


class OrderValidationError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def collect_order(header, rows):
    """Dates use ISO, dimensions/prices use decimal strings, counts use ints."""
    result = {key: str(header.get(key, "")).strip() for key in
              ("customer_name", "ship_to", "purchase_order")}
    result.update({key: str(header.get(key, "")) for key in ("remarks", "so_comment")})
    for key, label in (("customer_name", "顧客名"), ("ship_to", "納品先")):
        if not result[key]:
            raise OrderValidationError(key, f"{label}を入力してください。")
    for key, label in (("required_date", "Required date"), ("due_date", "due date")):
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

    def _on_entry_confirm_or_open(self):
        if self._is_calendar_open():
            return self._confirm_date()
        return self.open_calendar()

    def _on_entry_arrow(self, step):
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
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None
        self._selected_button = None
        self._month_label = None
        self._cell_buttons = []
        self._date_to_button = {}

    def open_calendar(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
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
        self.calendar_body = ctk.CTkFrame(self.popup, fg_color="transparent")
        self.calendar_body.pack(padx=12, pady=12, fill="both", expand=True)
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
        self.popup.after(10, self._focus_calendar)
        return "break"

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


class OrderEntryPanel(ctk.CTkFrame):
    def __init__(self, parent, colors, font_family, on_submit, on_close,
                 customers=(), destinations=(), customer_info=None):
        super().__init__(parent, width=590, fg_color=colors["panel"],
                         corner_radius=12, border_width=1, border_color=colors["border"])
        self.colors = colors
        self.font_family = font_family
        self.on_submit = on_submit
        self.customer_info = customer_info or read_customer_info_file()
        if not customers and self.customer_info.customer_names:
            customers = self.customer_info.customer_names
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.fields = {}
        self.item_entries = []
        self.error_field = None
        self.customer_ship_tos = dict(self.customer_info.customer_ship_tos)
        if customers and not self.customer_ship_tos:
            self.customer_ship_tos = {c: list(destinations) for c in customers}
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=16, pady=(10, 0), sticky="ew")
        close = tk.Button(top, text="閉じる", command=on_close, relief="flat", bd=0,
                          bg=colors["panel"], fg=colors["muted"], activebackground=colors["hover"],
                          font=(font_family, 11), padx=6, pady=4)
        close.pack(side="right")
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.body.grid(row=1, column=0, padx=12, pady=4, sticky="nsew")
        self.body.grid_columnconfigure((0, 1), weight=1, uniform="order_header")
        self._label(self.body, "顧客名", 0, 0)
        self._label(self.body, "納品先", 0, 1)
        for col, key, options in ((0, "customer_name", customers), (1, "ship_to", destinations)):
            values = [str(item) for item in options if str(item).strip()] if isinstance(options, (list, tuple)) else []
            field = ctk.CTkComboBox(
                self.body, values=values or [""], width=140, height=34,
                font=(font_family, 13), dropdown_font=(font_family, 13),
                fg_color="#FFFFFF", text_color=colors["text"], border_color=colors["border"],
                button_color=colors["button"], button_hover_color=colors["hover"],
                dropdown_fg_color=colors["panel"], dropdown_text_color=colors["text"],
                dropdown_hover_color=colors["hover"], corner_radius=7,
                command=self._on_customer_selected if key == "customer_name" else self._on_ship_to_selected,
            )
            field.set("")
            field.grid(row=1, column=col, padx=4, pady=(0, 10), sticky="ew")
            self.fields[key] = field

        # 納品先住所表示エリア（顧客名・納品先とRequired dateの間に1行配置）
        self._label(self.body, "住所", 2, 0, span=2)
        self.address_box = ctk.CTkTextbox(
            self.body, height=72, font=(font_family, 12),
            fg_color="#FFFFFF", text_color=colors["text"], border_width=1,
            border_color=colors["border"], corner_radius=7, wrap="word",
        )
        self.address_box.grid(row=3, column=0, columnspan=2, padx=4, pady=(0, 10), sticky="ew")
        self.address_box.configure(state="disabled")

        for col, key, label in ((0, "required_date", "Required date"), (1, "due_date", "due date")):
            self._label(self.body, label, 4, col)
            field = DateField(self.body, colors, font_family)
            field.grid(row=5, column=col, padx=4, pady=(0, 10), sticky="ew")
            self.fields[key] = field
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
        for row in range(5):
            entries = {}
            for col, key in enumerate(ITEM_FIELDS):
                field = self._entry(self.table, width=1, justify="left" if col == 0 else "right")
                field.grid(row=row + 1, column=col, padx=2, pady=3, sticky="ew")
                entries[key] = field
                self.fields[(row, key)] = field
            self.item_entries.append(entries)
        self.error_label = ctk.CTkLabel(self, text="", text_color=colors["error"],
                                        font=(font_family, 12), wraplength=540, anchor="w")
        self.error_label.grid(row=2, column=0, padx=20, pady=(4, 0), sticky="ew")
        self.error_label.grid_remove()
        self.send_button = tk.Button(
            self, text="送信", command=self.submit, bg=colors["accent"], fg=colors["on_accent"],
            activebackground=colors["accent_hover"], activeforeground=colors["on_accent"],
            relief="flat", bd=0, font=(font_family, 12), padx=30, pady=9,
        )
        self.send_button.grid(row=3, column=0, padx=20, pady=(10, 16), sticky="e")
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

    def _entry(self, parent, **kwargs):
        return ctk.CTkEntry(parent, height=34, font=(self.font_family, 13),
                           fg_color="#FFFFFF", text_color=self.colors["text"],
                           border_color=self.colors["border"], corner_radius=6, **kwargs)

    def close_popups(self):
        for key in ("required_date", "due_date"):
            self.fields[key].close_calendar()
        if hasattr(self, "customer_autocomplete"):
            self.customer_autocomplete.close()
        if hasattr(self, "ship_to_autocomplete"):
            self.ship_to_autocomplete.close()

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

    def _on_ship_to_selected(self, ship_to):
        customer = self.fields["customer_name"].get()
        addr = ""
        if hasattr(self, "customer_info"):
            addr = self.customer_info.get_address(customer, ship_to)
        self._display_address(addr)

    def focus_first(self):
        self.fields["customer_name"].focus_set()

    def submit(self):
        if self.error_field is not None:
            self.error_field.configure(border_color=self.colors["border"])
            self.error_field = None
        header = {}
        for key in ("customer_name", "ship_to", "purchase_order"):
            header[key] = self.fields[key].get()
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
                       ("required_date", "Required date"), ("due_date", "due date"),
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
