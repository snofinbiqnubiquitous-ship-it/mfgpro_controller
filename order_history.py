"""Local completed-order history and user-editable text templates."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

DEFAULT_TEMPLATE = "${顧客名}\n${Order ID}\n${ItemCode}  ${幅} x ${長さ} x ${本数} @${価格}\n${Required Date} ${納品先}着 で手配しました。"
HEADER_FIELDS = {
    "顧客名": "customer_name", "納品先": "ship_to", "顧客コード": "customer_code",
    "納品先コード": "ship_to_code", "Purchase Order": "purchase_order",
    "Remarks": "remarks", "SO comment": "so_comment", "住所": "address",
}
ITEM_FIELDS = {
    "ItemCode": "product_name", "Item Code": "product_name", "Item code": "product_name",
    "製品名": "product_name", "幅": "width", "巾": "width", "長さ": "length", "本数": "quantity", "価格": "price"
}
DATE_FIELDS = {
    "Required Date": "required_date", "Require Date": "required_date", "Required date": "required_date",
    "Due date": "due_date", "Due Date": "due_date", "due date": "due_date"
}
ORDER_FIELDS = {"Order ID", "処理した注文のOrder ID"}
TOKENS = set(HEADER_FIELDS) | set(ITEM_FIELDS) | set(DATE_FIELDS) | ORDER_FIELDS
TOKEN_RE = re.compile(r"\$\{([^{}]+)\}")


def validate_template(template):
    if not template.strip():
        raise ValueError("出力形式を入力してください。")
    unknown = set(TOKEN_RE.findall(template)) - TOKENS
    if unknown:
        raise ValueError("未対応の変数: " + "、".join(sorted(unknown)))
    if "${" in TOKEN_RE.sub("", template):
        raise ValueError("変数は ${顧客名} のように指定してください。")


def japanese_date(value):
    if not value:
        return ""
    day = date.fromisoformat(str(value))
    return f"{day.year}年{day.month}月{day.day}日 ({'月火水木金土日'[day.weekday()]})"


def resolve_header_value(payload, key):
    val = payload.get(key)
    if val:
        return str(val).strip()

    if key == "ship_to":
        for alt in ("destination", "ship_to_name", "shipto"):
            if payload.get(alt):
                return str(payload[alt]).strip()
        addr = str(payload.get("address", "")).strip()
        if addr:
            lines = [l.strip() for l in addr.splitlines() if l.strip()]
            name_lines = [l for l in lines if not re.match(r"^\d{3}-\d{4}$", l) and not re.match(r"^\d{2,4}-\d{2,4}-\d{4}$", l)]
            if name_lines:
                return name_lines[0]
        if payload.get("ship_to_code"):
            return str(payload["ship_to_code"]).strip()
    elif key == "customer_name":
        for alt in ("customer", "cust_name", "customer_text"):
            if payload.get(alt):
                return str(payload[alt]).strip()
        if str(payload.get("customer_code", "")).strip() == "20000600":
            return "TOPPANインフォメディア株式会社"
        if payload.get("customer_code"):
            return str(payload["customer_code"]).strip()
    return ""


def render_order(payload, order_id, template=DEFAULT_TEMPLATE):
    validate_template(template)
    values = {name: resolve_header_value(payload, key) for name, key in HEADER_FIELDS.items()}
    values.update({name: japanese_date(payload.get(key)) for name, key in DATE_FIELDS.items()})
    values.update({name: order_id or "未取得" for name in ORDER_FIELDS})
    result = []
    for line in template.split("\n"):
        # Lines containing an item variable repeat once per original sidebar row.
        items = payload.get("items", []) if set(TOKEN_RE.findall(line)) & set(ITEM_FIELDS) else [None]
        last_product = None
        for item in items:
            row = dict(values)
            if item is not None:
                row.update({name: str(item.get(key, "")) for name, key in ITEM_FIELDS.items()})
                curr_product = str(item.get("product_name", "")).strip()
                if curr_product and curr_product == last_product:
                    row["ItemCode"] = ""
                    row["Item Code"] = ""
                    row["Item code"] = ""
                    row["製品名"] = ""
                elif curr_product:
                    last_product = curr_product
            result.append(TOKEN_RE.sub(lambda m: row[m[1]], line))
    return "\n".join(result)


class OrderHistory:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, created TEXT NOT NULL, order_id TEXT, customer TEXT NOT NULL, payload TEXT NOT NULL)")
                yield db
        finally:
            db.close()

    def append(self, payload, order_id):
        customer = resolve_header_value(payload, "customer_name") or payload.get("customer_code", "")
        with self.connect() as db:
            db.execute("INSERT INTO orders(created, order_id, customer, payload) VALUES (?, ?, ?, ?)",
                       (datetime.now().isoformat(timespec="seconds"), order_id or "", customer, json.dumps(payload, ensure_ascii=False)))

    def page(self, offset=0):
        with self.connect() as db:
            return db.execute("SELECT id, created, order_id, customer FROM orders ORDER BY id DESC LIMIT 100 OFFSET ?", (offset,)).fetchall()

    def get(self, record_id):
        with self.connect() as db:
            row = db.execute("SELECT order_id, payload FROM orders WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise ValueError("履歴が見つかりません。")
        return row[0], json.loads(row[1])


def show_history(parent, store, template, colors, font):
    import tkinter as tk
    from tkinter import messagebox
    import customtkinter as ctk
    window = ctk.CTkToplevel(parent)
    window.title("注文ログ")
    window.geometry("800x600")
    window.minsize(560, 420)
    window.transient(parent)
    window.configure(fg_color=colors["panel"])
    listing = tk.Listbox(window, height=7, font=(font, 12), exportselection=False,
                         bg=colors["panel"], fg=colors["text"], relief="flat")
    listing.pack(fill="x", padx=16, pady=(16, 8))
    output = ctk.CTkTextbox(window, font=(font, 14), wrap="word")
    output.pack(fill="both", expand=True, padx=16, pady=8)
    output.configure(state="disabled")
    controls = ctk.CTkFrame(window, fg_color="transparent")
    controls.pack(fill="x", padx=16, pady=(0, 16))
    rows, offset = [], [0]

    def select(event=None):
        if not listing.curselection():
            return
        try:
            order_id, payload = store.get(rows[listing.curselection()[0]][0])
            text = render_order(payload, order_id, template())
        except (OSError, sqlite3.Error, ValueError) as exc:
            messagebox.showerror("注文ログ", str(exc), parent=window)
            return
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", text)
        output.configure(state="disabled")

    def refresh(delta=0):
        try:
            new_offset = max(0, offset[0] + delta)
            data = store.page(new_offset)
        except (OSError, sqlite3.Error) as exc:
            messagebox.showerror("注文ログ", str(exc), parent=window)
            return
        if not data and new_offset > 0:
            following.configure(state="disabled")
            return
        offset[0] = new_offset
        rows[:] = data
        listing.delete(0, "end")
        for _, created, order_id, customer in rows:
            listing.insert("end", f"{created.replace('T', ' ')}  {order_id or '未取得'}  {customer}")
        previous.configure(state="normal" if offset[0] else "disabled")
        following.configure(state="normal" if len(rows) == 100 else "disabled")
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.configure(state="disabled")
        if rows:
            listing.selection_set(0)
            select()

    def copy_text():
        text = output.get("1.0", "end-1c")
        if text:
            window.clipboard_clear()
            window.clipboard_append(text)

    previous = ctk.CTkButton(controls, text="新しい100件", width=110, command=lambda: refresh(-100))
    previous.pack(side="left")
    following = ctk.CTkButton(controls, text="古い100件", width=110, command=lambda: refresh(100))
    following.pack(side="left", padx=8)
    ctk.CTkButton(controls, text="更新", width=70, command=refresh).pack(side="left")
    ctk.CTkButton(controls, text="コピー", width=90, command=copy_text).pack(side="right")
    window.refresh_history = refresh
    listing.bind("<<ListboxSelect>>", select)
    refresh()
    window.after(80, window.lift)
    return window


def show_template_editor(parent, current, save, colors, font):
    import customtkinter as ctk
    from tkinter import messagebox
    window = ctk.CTkToplevel(parent)
    window.title("注文ログの出力形式")
    window.geometry("680x480")
    window.transient(parent)
    window.configure(fg_color=colors["panel"])
    editor = ctk.CTkTextbox(window, font=(font, 14), wrap="word")
    editor.pack(fill="both", expand=True, padx=16, pady=16)
    editor.insert("1.0", current)
    controls = ctk.CTkFrame(window, fg_color="transparent")
    controls.pack(fill="x", padx=16, pady=(0, 16))
    choices = ["${" + name + "}" for name in [*HEADER_FIELDS, "Order ID", "Required Date", "Due date", "ItemCode", "幅", "長さ", "本数", "価格"]]
    variable = ctk.CTkComboBox(controls, values=choices, width=170, state="readonly")
    variable.set(choices[0])
    variable.pack(side="left")
    ctk.CTkButton(controls, text="挿入", width=60, command=lambda: editor.insert("insert", variable.get())).pack(side="left", padx=8)

    def reset():
        editor.delete("1.0", "end")
        editor.insert("1.0", DEFAULT_TEMPLATE)

    def apply():
        text = editor.get("1.0", "end-1c")
        try:
            validate_template(text)
            save(text)
        except (ValueError, OSError) as exc:
            messagebox.showerror("出力形式", str(exc), parent=window)
            return
        window.destroy()

    ctk.CTkButton(controls, text="初期形式", width=90, command=reset).pack(side="left")
    ctk.CTkButton(controls, text="保存", width=90, command=apply).pack(side="right")
    window.after(80, window.lift)
    return window
