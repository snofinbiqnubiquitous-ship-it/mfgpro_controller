"""Order entry UI and validation; no network or QAD side effects."""

import calendar
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path
import re
import tkinter as tk

import customtkinter as ctk


WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
ITEM_FIELDS = ("product_name", "width", "length", "quantity", "price")
ITEM_LABELS = ("製品名", "巾", "長さ", "本数", "価格")
SHORTCUT_MODIFIERS = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift"}
SHORTCUT_RESERVED = {"Alt+F4", "Alt+Tab", "Alt+Esc", "Alt+Space", "Ctrl+Shift+Esc",
                     "Ctrl+A", "Ctrl+C", "Ctrl+D", "Ctrl+E", "Ctrl+H",
                     "Ctrl+T", "Ctrl+V", "Ctrl+W", "Ctrl+Tab", "Ctrl+Shift+C",
                     "Ctrl+Shift+Tab", "Shift+Tab", "Ctrl+PageUp", "Ctrl+PageDown"}


def normalize_shortcut(shortcut):
    """Return a canonical modified key, or reject unsafe/system-reserved keys."""
    parts = [part.strip() for part in str(shortcut).replace("Control", "Ctrl").split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError("Shift、Ctrl、Altのいずれかを含むショートカットを設定してください。")
    modifiers = []
    key = None
    for part in parts:
        modifier = SHORTCUT_MODIFIERS.get(part.lower())
        if modifier:
            if modifier in modifiers:
                raise ValueError("同じ修飾キーを重複して指定できません。")
            modifiers.append(modifier)
        elif key is None:
            key = part
        else:
            raise ValueError("割り当てるキーは1つ指定してください。")
    if key is None or not modifiers:
        raise ValueError("Shift、Ctrl、Altのいずれかを含むショートカットを設定してください。")
    aliases = {"return": "Enter", "kp_enter": "Enter", "spacebar": "Space",
               "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
               "prior": "PageUp", "next": "PageDown", "pageup": "PageUp",
               "pagedown": "PageDown", "left": "Left", "right": "Right",
               "up": "Up", "down": "Down", "tab": "Tab"}
    lowered = key.lower()
    if re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", lowered):
        key = lowered.upper()
    elif len(key) == 1:
        key = key.upper()
    else:
        key = aliases.get(lowered, key)
    if not re.fullmatch(r"[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|Enter|Space|Esc|Backspace|Delete|PageUp|PageDown|Left|Right|Up|Down|Tab", key):
        raise ValueError("文字、数字、Fキー、矢印キー、Enter、Space、Tabのいずれかを指定してください。")
    ordered = [modifier for modifier in ("Ctrl", "Alt", "Shift") if modifier in modifiers]
    result = "+".join((*ordered, key))
    if result in SHORTCUT_RESERVED:
        raise ValueError("Windowsまたはターミナルの標準ショートカットは変更できません。")
    return result


def shortcut_from_key_event(event):
    """Read modifiers from Tk's platform-independent key event state."""
    state = event.state
    modifiers = [name for bit, name in ((0x4, "Ctrl"), (0x8, "Alt"), (0x1, "Shift")) if state & bit]
    if not modifiers:
        return None
    aliases = {"return": "Enter", "kp_enter": "Enter", "space": "Space",
               "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
               "prior": "PageUp", "next": "PageDown"}
    key = event.keysym
    key = aliases.get(key.lower(), key.upper() if len(key) == 1 else key)
    try:
        return normalize_shortcut("+".join((*modifiers, key)))
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
        shortcut = shortcut_from_key_event(event)
        if shortcut is None:
            self.error_label.configure(text="Shift、Ctrl、Altのいずれかと組み合わせてください。")
            return "break"
        self.key_entry.configure(state="normal")
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, shortcut)
        self.key_entry.configure(state="readonly")
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
            self.cancelled = bool(state & (0x1 | 0x8))
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
        self.variable = tk.StringVar(self, value=format_order_date(self.value))
        self.popup = None
        self.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.variable, state="readonly", height=34, width=140,
            font=(font_family, 13), fg_color="#FFFFFF", text_color=colors["text"],
            border_color=colors["border"], corner_radius=7,
        )
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Button-1>", lambda event: self.open_calendar())
        self.entry.bind("<Return>", lambda event: self.open_calendar())
        self.entry.bind("<space>", lambda event: self.open_calendar())
        self.button = tk.Button(
            self, text="▾", command=self.open_calendar, font=(font_family, 12),
            bg=colors["button"], fg=colors["text"], activebackground=colors["hover"],
            relief="flat", borderwidth=0, takefocus=True, padx=8,
        )
        self.button.grid(row=0, column=1, padx=(4, 0), sticky="ns")

    def focus_set(self):
        self.entry.focus_set()

    def set_date(self, value):
        self.value = value
        self.variable.set(format_order_date(value))
        self.close_calendar()
        self.entry.focus_set()

    def close_calendar(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None

    def open_calendar(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            return "break"
        self.month = self.value.replace(day=1)
        self.popup = ctk.CTkToplevel(self)
        self.popup.title("日付選択")
        self.popup.configure(fg_color=self.colors["panel"])
        self.popup.resizable(False, False)
        self.popup.transient(self.winfo_toplevel())
        self.popup.protocol("WM_DELETE_WINDOW", self.close_calendar)
        self.popup.bind("<Escape>", lambda event: self.close_calendar())
        self.calendar_body = ctk.CTkFrame(self.popup, fg_color="transparent")
        self.calendar_body.pack(padx=12, pady=12, fill="both", expand=True)
        self._draw_month()
        self.popup.update_idletasks()
        width, height = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
        x = max(0, min(self.winfo_rootx(), self.winfo_screenwidth() - width - 16))
        y = self.winfo_rooty() + self.winfo_height() + 4
        if y + height > self.winfo_screenheight() - 48:
            y = max(0, self.winfo_rooty() - height - 4)
        self.popup.geometry(f"+{x}+{y}")
        self.popup.after(10, self.popup.focus_set)
        return "break"

    def _move_month(self, step):
        index = self.month.year * 12 + self.month.month - 1 + step
        year, month = divmod(index, 12)
        if 1 <= year <= 9999:
            self.month = date(year, month + 1, 1)
            self._draw_month()

    def _day_button(self, text, command, selected=False):
        return tk.Button(
            self.calendar_body, text=text, command=command, width=3,
            font=(self.font_family, 11), relief="flat", bd=0, padx=2, pady=5,
            bg=self.colors["accent"] if selected else self.colors["panel"],
            fg=self.colors["on_accent"] if selected else self.colors["text"],
            activebackground=self.colors["hover"], takefocus=True,
        )

    def _draw_month(self):
        for child in self.calendar_body.winfo_children():
            child.destroy()
        self._day_button("‹", lambda: self._move_month(-1)).grid(row=0, column=0)
        ctk.CTkLabel(self.calendar_body, text=f"{self.month.year}年 {self.month.month}月",
                     font=(self.font_family, 14), text_color=self.colors["text"]).grid(
                         row=0, column=1, columnspan=5)
        self._day_button("›", lambda: self._move_month(1)).grid(row=0, column=6)
        for col, text in enumerate(WEEKDAYS):
            ctk.CTkLabel(self.calendar_body, text=text, width=34,
                         text_color=self.colors["muted"], font=(self.font_family, 12)).grid(row=1, column=col)
        for row, week in enumerate(calendar.Calendar().monthdayscalendar(self.month.year, self.month.month), 2):
            for col, day in enumerate(week):
                if day:
                    value = self.month.replace(day=day)
                    self._day_button(str(day), lambda d=value: self.set_date(d), value == self.value).grid(row=row, column=col)
        self._day_button("今日", lambda: self.set_date(date.today())).grid(row=8, column=0, columnspan=7, sticky="ew", pady=(8, 0))


class OrderEntryPanel(ctk.CTkFrame):
    def __init__(self, parent, colors, font_family, on_submit, on_close,
                 customers=(), destinations=()):
        super().__init__(parent, width=590, fg_color=colors["panel"],
                         corner_radius=12, border_width=1, border_color=colors["border"])
        self.colors = colors
        self.font_family = font_family
        self.on_submit = on_submit
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.fields = {}
        self.item_entries = []
        self.error_field = None
        self.customer_ship_tos = {}
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
                command=self._on_customer_selected if key == "customer_name" else None,
            )
            field.set("")
            field.grid(row=1, column=col, padx=4, pady=(0, 10), sticky="ew")
            self.fields[key] = field
        for col, key, label in ((0, "required_date", "Required date"), (1, "due_date", "due date")):
            self._label(self.body, label, 2, col)
            field = DateField(self.body, colors, font_family)
            field.grid(row=3, column=col, padx=4, pady=(0, 10), sticky="ew")
            self.fields[key] = field
        self._label(self.body, "Purchase Order", 4, 0, 2)
        self.fields["purchase_order"] = self._entry(self.body)
        self.fields["purchase_order"].grid(row=5, column=0, columnspan=2, padx=4, pady=(0, 10), sticky="ew")
        for col, key, label in ((0, "remarks", "Remarks"), (1, "so_comment", "SO comment")):
            self._label(self.body, label, 6, col)
            field = ctk.CTkTextbox(
                self.body, height=68, width=140, font=(font_family, 13),
                fg_color="#FFFFFF", text_color=colors["text"], border_width=1,
                border_color=colors["border"], corner_radius=7, wrap="word",
            )
            field.grid(row=7, column=col, padx=4, pady=(0, 14), sticky="ew")
            self.fields[key] = field
        self.table = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
        self.table.grid(row=8, column=0, columnspan=2, padx=2, pady=(0, 8), sticky="ew")
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

    def set_choices(self, field, values):
        self.fields[field].configure(values=values or [""])

    def set_customer_ship_tos(self, choices):
        self.customer_ship_tos = {str(customer): list(destinations)
                                  for customer, destinations in choices.items()}
        customers = list(self.customer_ship_tos)
        self.fields["customer_name"].configure(values=customers or [""])
        current = self.fields["customer_name"].get()
        if current not in self.customer_ship_tos:
            current = ""
            self.fields["customer_name"].set("")
        self._on_customer_selected(current)

    def _on_customer_selected(self, customer):
        destinations = self.customer_ship_tos.get(customer, [])
        field = self.fields["ship_to"]
        field.configure(values=destinations or [""])
        if field.get() not in destinations:
            field.set("")

    def focus_first(self):
        self.fields["customer_name"].focus_set()

    def submit(self):
        if self.error_field is not None:
            self.error_field.configure(border_color=self.colors["border"])
            self.error_field = None
        header = {}
        for key in ("customer_name", "ship_to", "purchase_order"):
            header[key] = self.fields[key].get()
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
