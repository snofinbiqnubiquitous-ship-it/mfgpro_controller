"""QAD terminal transport. This module never touches Tk widgets."""

import codecs
import queue
import socket
import threading

import paramiko
import pyte
from wcwidth import wcwidth


ENCODING = "cp932"
# 設計書準拠: データ欠落・折り返し防止のためSSH通信および仮想端末は132桁を確保
COLS, ROWS = 132, 24
KEY_SEQUENCES = {
    "Return": "\r", "KP_Enter": "\r", "space": " ",
    "BackSpace": "\b", "Tab": "\t", "Escape": "\x1b",
    "F1": "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
    "Up": "\x1b[A", "Down": "\x1b[B", "Right": "\x1b[C", "Left": "\x1b[D",
    "Ctrl+F": "\x06",
}

# ボタン名とキーの対応。QADの画面ごとに意味が違うキーは機能名を付けない。
TOOLBAR_GROUPS = (
    ("ファンクション", (("F1  実行", "F1"), ("F2", "F2"),
                          ("F3", "F3"), ("F4", "F4"))),
    ("入力・操作", (("Enter  決定", "Return"), ("Space  次頁", "space"),
                     ("Esc", "Escape"), ("Ctrl + F", "Ctrl+F"),
                     ("Tab", "Tab"), ("Backspace", "BackSpace"))),
    ("カーソル移動", (("↑  上", "Up"), ("↓  下", "Down"),
                       ("←  左", "Left"), ("→  右", "Right"))),
)


def key_sequence(keysym, char="", state=0):
    """Keyboard and toolbar use the same VT100 mappings."""
    if state & 0x4 and keysym.lower() == "f":
        return KEY_SEQUENCES["Ctrl+F"]
    return KEY_SEQUENCES.get(keysym, char)


def extract_row_data(line, cols):
    """pyteの1行分のbufferからUnicodeテキストとスタイルスパン (start, end, tags) を抽出する。
    全角文字（wcwidth==2）のスタブをスキップし、TkinterのUnicode文字インデックスに合致させる。
    """
    chars = []
    spans = []
    is_wide_char = False
    current_tags = ()
    span_start = 0

    for x in range(cols):
        if is_wide_char:
            is_wide_char = False
            continue
        c = line[x]
        data = c.data
        if not data:
            continue
        is_wide_char = (len(data) > 0 and wcwidth(data[0]) == 2)

        tags = []
        if c.reverse:
            tags.append("reverse")
        if c.underscore:
            tags.append("underline")
        if c.bold:
            tags.append("bold")
        tags = tuple(sorted(tags))

        idx = len(chars)
        if tags != current_tags:
            if current_tags:
                spans.append((span_start, idx, current_tags))
            current_tags = tags
            span_start = idx
        chars.append(data)

    if current_tags:
        spans.append((span_start, len(chars), current_tags))

    return "".join(chars), spans


class TerminalSession:
    """One worker owns the SSH connection, decoder, and virtual screen.

    The GUI consumes dirty rows under a lock; outgoing keystrokes are queued
    so a blocked network never blocks Tk. Each connection gets fresh state.
    """

    def __init__(self, host, port, username, password, events):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.events = events
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        # DEC Special Character and Line Drawing Set（罫線文字）を有効化
        self.stream.use_utf8 = False
        self.decoder = codecs.getincrementaldecoder(ENCODING)(errors="replace")
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.outgoing = queue.Queue(maxsize=256)
        self.last_cursor = None

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="qad-ssh").start()

    def stop(self):
        self.stop_event.set()

    def send(self, text):
        # Strict encoding prevents silently submitting a different value to QAD.
        self.outgoing.put_nowait(text.encode(ENCODING))

    def feed(self, data, final=False):
        with self.lock:
            self.stream.feed(self.decoder.decode(data, final=final))

    def snapshot(self):
        """Return only changed rows with text and style spans; idle calls return None."""
        with self.lock:
            cursor = self.screen.cursor
            cursor_state = (cursor.y, cursor.x, cursor.hidden)
            dirty = self.screen.dirty
            if not dirty and cursor_state == self.last_cursor:
                return None
            cols = self.screen.columns
            rows = self.screen.lines

            # 80列を超える文字が存在するか判定（通常画面なら80桁にフィットして描画幅を最大化）
            has_wide = False
            for r in range(rows):
                buf = self.screen.buffer[r]
                for c in range(80, cols):
                    if buf[c].data != " ":
                        has_wide = True
                        break
                if has_wide:
                    break

            active_cols = cols if has_wide else 80

            offset = sum(len(self.screen.buffer[cursor.y][col].data)
                         for col in range(min(cursor.x, active_cols - 1)))
            position = None if cursor.hidden else (cursor.y, offset)
            changed = {}
            if dirty:
                for row in sorted(dirty):
                    if 0 <= row < rows:
                        changed[row] = extract_row_data(self.screen.buffer[row], active_cols)
                dirty.clear()
            self.last_cursor = cursor_state
            return changed, position, active_cols

    def _run(self):
        ssh = paramiko.SSHClient()
        shell = None
        error = None
        try:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, port=self.port, username=self.username,
                        password=self.password, timeout=10,
                        banner_timeout=10, auth_timeout=10)
            if self.stop_event.is_set():
                return
            shell = ssh.invoke_shell(term="vt100", width=COLS, height=ROWS)
            shell.settimeout(0.05)
            if self.stop_event.is_set():
                return
            self.events.put((self, "connected", None))
            while not self.stop_event.is_set():
                # Bound each batch so key repeat cannot starve reception.
                for _ in range(16):
                    if self.stop_event.is_set():
                        break
                    try:
                        data = self.outgoing.get_nowait()
                    except queue.Empty:
                        break
                    shell.sendall(data)
                if self.stop_event.is_set():
                    break
                try:
                    chunk = shell.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:  # EOF, including orderly remote disconnect.
                    self.feed(b"", final=True)
                    break
                self.feed(chunk)
        except Exception as exc:
            if not self.stop_event.is_set():
                error = str(exc)
        finally:
            try:
                if shell is not None:
                    shell.close()
            finally:
                try:
                    ssh.close()
                finally:
                    self.events.put((self, "closed", error))
