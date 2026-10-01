"""Shared Due/Required date editor using tkcalendar and CustomTkinter."""
from datetime import date
import tkinter as tk
import customtkinter as ctk
from tkcalendar import Calendar


def visible_interval(due, required, month, year):
    """Only decorate visible cells, even for intervals spanning many years."""
    first = date(year, month, 1)
    start = max(date.min.toordinal(), first.toordinal() - first.weekday())
    finish = min(date.max.toordinal(), start + 41)
    low, high = sorted((due.toordinal(), required.toordinal()))
    return [date.fromordinal(day) for day in range(max(start, low), min(finish, high) + 1)]


class OrderDateRangePicker:
    KEYS = ('due_date', 'required_date')
    LABELS = {'due_date': 'Due Date', 'required_date': 'Required Date'}

    def __init__(self, due_field, required_field, colors, font_family, parse_date, format_date):
        self.fields = dict(due_date=due_field, required_date=required_field)
        self.colors = colors
        self.font_family = font_family
        self.parse_date = parse_date
        self.format_date = format_date
        self.window = None
        self.calendar = None
        self.entries = {}
        self.variables = {}
        self.buttons = {}
        self.draft = {}
        self.active = 'required_date'
        for field in self.fields.values():
            field.range_picker = self

    def is_open(self):
        return self.window is not None and self.window.winfo_exists()

    def open(self, anchor, initial_text=None):
        key = next(key for key, field in self.fields.items() if field is anchor)
        if self.is_open():
            self.set_active(key)
            self.window.lift()
            if initial_text:
                self.start_typing(initial_text)
            return 'break'
        self.anchor = anchor
        self.draft = {name: field.value for name, field in self.fields.items()}
        self.window = ctk.CTkToplevel(anchor.winfo_toplevel())
        self.window.title('Due Date / Required Date')
        self.window.configure(fg_color=self.colors['panel'])
        self.window.resizable(False, False)
        self.window.transient(anchor.winfo_toplevel())
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Escape>', lambda event: self.close())
        header = ctk.CTkFrame(self.window, fg_color='transparent')
        header.pack(fill='x', padx=18, pady=(18, 12))
        for col, name in enumerate(self.KEYS):
            header.grid_columnconfigure(col, weight=1)
            self.buttons[name] = ctk.CTkButton(
                header, text=self.LABELS[name], height=32, corner_radius=9,
                font=(self.font_family, 12), command=lambda name=name: self.set_active(name))
            self.buttons[name].grid(row=0, column=col, padx=4, sticky='ew')
            self.variables[name] = tk.StringVar(self.window, value=self.draft[name].strftime('%Y/%m/%d'))
            entry = ctk.CTkEntry(header, textvariable=self.variables[name], height=38,
                font=(self.font_family, 14), fg_color='#FFFFFF', text_color=self.colors['text'],
                border_color=self.colors['border'], corner_radius=9, justify='center')
            entry.grid(row=1, column=col, padx=4, pady=(7, 0), sticky='ew')
            self.entries[name] = entry
            inner = entry._entry
            inner.bindtags(tuple(tag for tag in inner.bindtags() if tag != str(self.window)))
            inner.bind('<FocusIn>', lambda event, name=name: self.set_active(name, move_view=False))
            inner.bind('<Return>', lambda event, name=name: self.apply_input(name))
            inner.bind('<KP_Enter>', lambda event, name=name: self.apply_input(name))
            inner.bind('<Escape>', lambda event: self.close())
            inner.bind('<Down>', lambda event, name=name: self.focus_calendar_from_input(name))
            inner.bind('<KeyRelease>', lambda event, name=name: self.input_changed(name))
        shell = ctk.CTkFrame(self.window, fg_color='#FFFFFF', corner_radius=12,
                            border_width=1, border_color=self.colors['border'])
        shell.pack(fill='both', expand=True, padx=18, pady=(0, 14))
        navigation = ctk.CTkFrame(shell, fg_color='transparent')
        navigation.pack(fill='x', padx=12, pady=(10, 4))
        ctk.CTkButton(navigation, text='‹', width=34, height=32, corner_radius=9,
            fg_color='#EDF2F8', hover_color=self.colors['hover'], text_color=self.colors['text'],
            font=(self.font_family, 19), command=lambda: self.move_month(-1)).pack(side='left')
        ctk.CTkButton(navigation, text='›', width=34, height=32, corner_radius=9,
            fg_color='#EDF2F8', hover_color=self.colors['hover'], text_color=self.colors['text'],
            font=(self.font_family, 19), command=lambda: self.move_month(1)).pack(side='right')
        self.month_label = ctk.CTkLabel(navigation, text='', font=(self.font_family, 15, 'bold'),
                                      text_color=self.colors['text'])
        self.month_label.pack(fill='x', expand=True)
        selected = self.draft[key]
        self.calendar = Calendar(shell, year=selected.year, month=selected.month, day=selected.day,
            locale='ja_JP', date_pattern='yyyy/mm/dd', firstweekday='monday', showweeknumbers=False,
            showothermonthdays=True, font=(self.font_family, 13), borderwidth=0,
            background='#FFFFFF', foreground=self.colors['text'], bordercolor='#FFFFFF',
            headersbackground='#FFFFFF', headersforeground=self.colors.get('muted', '#64748B'),
            normalbackground='#FFFFFF', normalforeground=self.colors['text'],
            weekendbackground='#FFFFFF', weekendforeground=self.colors.get('muted', '#64748B'),
            othermonthbackground='#FFFFFF', othermonthforeground='#A4ACB7',
            othermonthwebackground='#FFFFFF', othermonthweforeground='#A4ACB7',
            selectbackground=self.colors['accent'], selectforeground=self.colors['on_accent'])
        self.calendar.pack(fill='both', expand=True, padx=12, pady=12)
        # The pinned tkcalendar 1.6.1 header is replaced with CTk month controls.
        self.calendar._header.pack_forget()
        self.calendar.tag_config('interval', background='#E7EFFA', foreground=self.colors['text'])
        self.calendar.tag_config('endpoint', background=self.colors['accent'], foreground=self.colors['on_accent'])
        self.calendar.bind('<<CalendarSelected>>', self.choose_date)
        self.calendar.bind('<<CalendarMonthChanged>>', lambda event: self.paint_interval())
        footer = ctk.CTkFrame(self.window, fg_color='transparent')
        footer.pack(fill='x', padx=22, pady=(0, 18))
        ctk.CTkButton(footer, text='今日', width=70, fg_color=self.colors['button'],
            hover_color=self.colors['hover'], text_color=self.colors['text'],
            command=self.choose_today).pack(side='left')
        ctk.CTkButton(footer, text='キャンセル', width=100, fg_color=self.colors['button'],
            hover_color=self.colors['hover'], text_color=self.colors['text'],
            command=self.close).pack(side='right', padx=(8, 0))
        ctk.CTkButton(footer, text='決定', width=90, fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'], text_color=self.colors['on_accent'],
            command=self.commit).pack(side='right')
        for sequence, days in (('<Left>', -1), ('<Right>', 1), ('<Up>', -7), ('<Down>', 7)):
            self.window.bind(sequence, lambda event, days=days: self.move_cursor(days))
        self.window.bind('<Return>', self.choose_date)
        self.window.bind('<KP_Enter>', self.choose_date)
        self.window.bind('<Control-Return>', lambda event: self.commit())
        self.window.bind('<Prior>', lambda event: self.move_month(-1))
        self.window.bind('<Next>', lambda event: self.move_month(1))
        self.window.bind('<KeyPress>', self.on_typed, add='+')
        for field in self.fields.values():
            field.popup = self.window
        self.set_active(key)
        self.paint_interval()
        self.window.update_idletasks()
        width, height = max(390, self.window.winfo_reqwidth()), self.window.winfo_reqheight()
        x = max(0, min(anchor.winfo_rootx(), anchor.winfo_screenwidth() - width - 16))
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        if y + height > anchor.winfo_screenheight() - 48:
            y = max(0, anchor.winfo_rooty() - height - 4)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.window.lift()
        if initial_text:
            self.start_typing(initial_text)
        else:
            self.calendar.focus_set()
        return 'break'

    def set_active(self, key, move_view=True):
        self.active = key
        for name, button in self.buttons.items():
            selected = name == key
            button.configure(fg_color=self.colors['accent'] if selected else '#EDF2F8',
                text_color=self.colors['on_accent'] if selected else self.colors['text'],
                hover_color=self.colors['accent_hover'] if selected else self.colors['hover'])
        if self.calendar is not None and move_view:
            self.calendar.selection_set(self.draft[key])
            self.calendar.see(self.draft[key])
            self.paint_interval()

    def paint_interval(self):
        if not self.is_open() or self.calendar is None:
            return
        self.calendar.calevent_remove('all')
        month, year = self.calendar.get_displayed_month()
        self.month_label.configure(text=f'{year}年 {month}月')
        endpoints = set(self.draft.values())
        for day in visible_interval(self.draft['due_date'], self.draft['required_date'], month, year):
            self.calendar.calevent_create(day, '', tags='endpoint' if day in endpoints else 'interval')

    def choose_date(self, event=None):
        self.draft[self.active] = self.calendar.selection_get()
        self.variables[self.active].set(self.draft[self.active].strftime('%Y/%m/%d'))
        other = 'required_date' if self.active == 'due_date' else 'due_date'
        self.set_active(other, move_view=False)
        self.paint_interval()
        return 'break'

    def choose_today(self):
        self.calendar.selection_set(date.today())
        self.calendar.see(date.today())
        self.choose_date()

    def apply_input(self, name):
        try:
            value = self.parse_date(self.variables[name].get())
        except ValueError:
            self.entries[name].configure(border_color=self.colors.get('error', '#EF4444'))
            return 'break'
        self.draft[name] = value
        self.variables[name].set(value.strftime('%Y/%m/%d'))
        self.set_active(name)
        return 'break'

    def input_changed(self, name):
        self.entries[name].configure(border_color=self.colors['border'])
        try:
            value = self.parse_date(self.variables[name].get())
        except ValueError:
            return
        self.draft[name] = value
        self.paint_interval()

    def focus_calendar_from_input(self, name):
        self.apply_input(name)
        self.calendar.focus_set()
        return 'break'

    def start_typing(self, text):
        entry = self.entries[self.active]._entry
        entry.delete(0, 'end')
        entry.insert(0, text)
        entry.focus_set()
        entry.icursor('end')

    def on_typed(self, event):
        if event.char and event.char.isdigit() and not event.state & 0x4:
            self.start_typing(event.char)
            return 'break'

    def move_cursor(self, days):
        current = self.calendar.selection_get()
        ordinal = max(date.min.toordinal(), min(date.max.toordinal(), current.toordinal() + days))
        target = date.fromordinal(ordinal)
        self.calendar.selection_set(target)
        self.calendar.see(target)
        self.paint_interval()
        self.calendar.focus_set()
        return 'break'

    def move_month(self, step):
        month, year = self.calendar.get_displayed_month()
        index = (year - 1) * 12 + month - 1 + step
        if 0 <= index < 9999 * 12:
            year, month = divmod(index, 12)
            self.calendar.see(date(year + 1, month + 1, 1))
            self.paint_interval()
        return 'break'

    def commit(self):
        parsed = {}
        for name in self.KEYS:
            try:
                parsed[name] = self.parse_date(self.variables[name].get())
            except ValueError:
                self.entries[name].configure(border_color=self.colors.get('error', '#EF4444'))
                self.entries[name].focus_set()
                return 'break'
        # Commit both fields only after both dates validate; preserve their business roles.
        for name, value in parsed.items():
            field = self.fields[name]
            field.value = value
            field.cursor_date = value
            field.variable.set(self.format_date(value))
        anchor = self.anchor
        self.close()
        anchor.entry.focus_set()
        return 'break'

    def close(self):
        window = self.window
        self.window = None
        if window is not None and window.winfo_exists():
            window.destroy()
        for field in self.fields.values():
            field.popup = None
        self.calendar = None
        self.entries.clear()
        self.variables.clear()
        self.buttons.clear()
        return 'break'
