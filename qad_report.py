"""Report extraction over an independent QAD SSH shell and GAS forwarding helpers.

The key sequences and waits used by each report are defined by the add-ons. This
module supplies the shared, tested primitives: 32prn decoding, report parsing,
screen waits on a raw shell, and browser based GAS posting.
"""
import base64
import codecs
import datetime
import gzip
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger("ModernTerminal")

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
PRN_BEGIN = b"begin 0 32PRINTER"
PRN_END_ESC = b"\x1b[4i"
# While receiving, the terminator must be followed by a byte. When decoding the
# complete buffer, the end of the data is also accepted.
PRN_STREAM_END_RE = re.compile(rb"\nend(?:\r|\n|\x1b)")
PRN_DATA_END_RE = re.compile(rb"\nend(?:\r|\n|\x1b|$)")
MAIN_MENU_TEXT = "Please select a function"
SPACE_PROMPTS = ("Press space bar", "Pausing")
GAS_TEMP_PREFIX = "gas_submit_"
GAS_TEMP_MAX_AGE = 3600
KEY_F1 = "\x1bOP"
KEY_CTRL_F = "\x06"


def decode_32prn_stream(stream_bytes) -> str:
    """Decode a 32prn stream (uuencoded gzip) into CP932 report text."""
    stream_bytes = bytes(stream_bytes)
    b_start = stream_bytes.find(PRN_BEGIN)
    if b_start == -1:
        raise ValueError("32prn ヘッダー (begin 0 32PRINTER) が見つかりませんでした。")
    end_match = PRN_DATA_END_RE.search(stream_bytes, b_start)
    if not end_match:
        raise ValueError("32prn フッター (end) が見つかりませんでした。")
    # Keep exactly "\nend" and terminate it, so a following ESC is not decoded.
    uu_data = stream_bytes[b_start:end_match.start() + 4] + b"\n"
    uu_clean = uu_data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    compressed = codecs.decode(uu_clean, "uu")
    return gzip.decompress(compressed).decode("cp932", errors="replace")


def clean_printer_data(text: str) -> str:
    """Remove ANSI escape sequences and NUL characters."""
    return ANSI_ESCAPE_RE.sub("", text).replace("\x00", "")


def convert_date_format(date_str: str) -> str:
    """Convert QAD mm/dd/yy to YYYY/MM/DD; return other values unchanged."""
    try:
        return datetime.datetime.strptime(date_str, "%m/%d/%y").strftime("%Y/%m/%d")
    except ValueError:
        return date_str


def parse_report_to_rows(input_text: str) -> list:
    """Parse a fixed width QAD report using its dashed header line."""
    lines = input_text.splitlines()
    slices = []
    parsing_data = False
    all_rows = []

    for i, line in enumerate(lines):
        if "End of Report" in line or "レポート終了" in line:
            break
        if ".p" in line.lower() or line.lstrip().startswith("Page:") or "Date:" in line or line.lstrip().startswith("Item Number"):
            continue

        if line.lstrip().startswith("---") and "--- " in line:
            if not slices:
                header_line = lines[i - 1]
                parts = line.split()
                current_idx = line.find(parts[0])
                for j, part in enumerate(parts):
                    start = line.find(part, current_idx)
                    if j < len(parts) - 1:
                        end = line.find(parts[j + 1], start + len(part))
                    else:
                        end = 9999
                    slices.append((start, end))
                    current_idx = start + len(part)
                b_header = header_line.encode("cp932", errors="replace")
                all_rows.append([b_header[s:e].decode("cp932", errors="ignore").strip() for s, e in slices])
            parsing_data = True
            continue

        if parsing_data:
            if not line.strip():
                continue
            row = []
            b_line = line.encode("cp932", errors="replace")
            for s, e in slices:
                val = b_line[s:e].decode("cp932", errors="ignore").strip() if s < len(b_line) else ""
                if len(val) == 8 and val[2] == "/" and val[5] == "/":
                    val = convert_date_format(val)
                row.append(val)
            if any(row):
                all_rows.append(row)

    return all_rows


def cleanup_gas_temp_files(directory=None, max_age=GAS_TEMP_MAX_AGE, now=None):
    """Delete old forwarding pages. They contain the transmitted report data."""
    folder = Path(directory or tempfile.gettempdir())
    limit = (now if now is not None else time.time()) - max_age
    removed = 0
    for path in folder.glob(f"{GAS_TEMP_PREFIX}*.html"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def build_gas_page(rows_or_payload, gas_url: str, title: str) -> str:
    json_str = json.dumps(rows_or_payload, ensure_ascii=False)
    b64_data = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    data_size_kb = len(b64_data) / 1024
    if isinstance(rows_or_payload, dict):
        raw_data = rows_or_payload.get("data", [])
    else:
        raw_data = rows_or_payload
    row_count = len(raw_data) - 1 if len(raw_data) > 1 else len(raw_data)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script>
        function updateStatus(msg, color) {{
            const el = document.getElementById('statusMsg');
            if (el) {{
                el.innerHTML = msg;
                el.style.color = color;
            }}
        }}

        function send() {{
            updateStatus("🚀 ステップ1: ブラウザがデータを受け取りました。GASへ送信を開始します...", "#2563EB");
            document.getElementById('postForm').submit();

            setTimeout(function() {{
                updateStatus("✅ ステップ2: GASへのデータ転送要求が完了しました。<br>※このタブは数秒後に自動的に閉じます。", "#059669");
            }}, 1000);

            setTimeout(function() {{
                window.opener = null;
                window.open('', '_self');
                window.close();
            }}, 4000);
        }}
    </script>
</head>
<body onload="send()">
    <div style="font-family: sans-serif; padding: 30px; text-align: center;">
        <h2>{title}</h2>
        <p>データ件数: {row_count:,} 件 / データサイズ: {data_size_kb:.1f} KB</p>
        <h3 id="statusMsg" style="color: #D97706;">⏳ 初期化中...</h3>
        <p>エラーが発生した場合は、この画面のまま止まります。成功すれば自動で閉じます。</p>
    </div>
    <iframe name="hidden_iframe" style="display:none;"></iframe>
    <form id="postForm" method="POST" action="{gas_url}" target="hidden_iframe">
        <input type="hidden" name="data" value="{b64_data}">
    </form>
</body>
</html>"""


def _launch_in_background(target_path):
    """Open the page in an existing browser while keeping the current window focused."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        prev_hwnd = user32.GetForegroundWindow()
        lsfw_lock, lsfw_unlock = 1, 2
        user32.LockSetForegroundWindow(lsfw_lock)

        def _focus_keeper(orig_hwnd, duration=1.5):
            start = time.time()
            while time.time() - start < duration:
                fg = user32.GetForegroundWindow()
                if orig_hwnd and fg != orig_hwnd and fg != 0:
                    try:
                        cur_tid = kernel32.GetCurrentThreadId()
                        fg_tid = user32.GetWindowThreadProcessId(fg, None)
                        user32.AttachThreadInput(cur_tid, fg_tid, True)
                        user32.SetForegroundWindow(orig_hwnd)
                        user32.BringWindowToTop(orig_hwnd)
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
                    except Exception:
                        pass
                time.sleep(0.05)
            try:
                user32.LockSetForegroundWindow(lsfw_unlock)
            except Exception:
                pass

        if prev_hwnd and prev_hwnd != 0:
            threading.Thread(target=_focus_keeper, args=(prev_hwnd,), daemon=True).start()
    except Exception:
        pass

    try:
        subprocess.Popen(f'start "" /min chrome "{target_path}"', shell=True)
    except Exception:
        try:
            subprocess.Popen(f'start "" /min msedge "{target_path}"', shell=True)
        except Exception:
            try:
                subprocess.Popen(f'start "" /min "{target_path}"', shell=True)
            except Exception as exc:
                logger.error(f"ブラウザ起動エラー: {exc}")


def send_to_gas_via_browser(rows_or_payload, gas_url: str, title: str = "Google Sheets へ送信中", launcher=None):
    """Write a self submitting page and open it in the browser (SSO is handled there)."""
    cleanup_gas_temp_files()
    if isinstance(rows_or_payload, dict):
        menu_tag = str(rows_or_payload.get("menu", "data")).replace(".", "_")
    else:
        menu_tag = "data"
    unique_id = f"{menu_tag}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    path = os.path.join(tempfile.gettempdir(), f"{GAS_TEMP_PREFIX}{unique_id}.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_gas_page(rows_or_payload, gas_url, title))
    (launcher or _launch_in_background)(path)
    return path


class ShellWaitTimeout(TimeoutError):
    pass


class ReportShell:
    """One QAD login on its own SSH channel, independent of terminal tabs."""

    def __init__(self, host, port, user, password, *, client_factory=None,
                 clock=time.monotonic, sleep=time.sleep):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.client_factory = client_factory
        self.clock = clock
        self.sleep = sleep
        self.client = None
        self.shell = None

    def open(self, width, height):
        if self.client_factory is None:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            client = self.client_factory()
        self.client = client
        client.connect(self.host, port=self.port, username=self.user, password=self.password, timeout=15)
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        self.shell = client.invoke_shell(term="vt100", width=width, height=height)
        self.shell.settimeout(10.0)
        return self

    def close(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def send(self, data):
        self.shell.send(data)

    def pause(self, seconds):
        self.sleep(seconds)

    def clear(self):
        """Discard pending output, including echoed keystrokes."""
        while self.shell.recv_ready():
            self.shell.recv(65535)
            self.sleep(0.05)

    def wait_text(self, target_text, timeout=12.0, raise_error=True):
        """Wait until the text appears. CP932 bytes split across packets are kept."""
        decoder = codecs.getincrementaldecoder("cp932")(errors="ignore")
        end_time = self.clock() + timeout
        buffer = ""
        while self.clock() < end_time:
            if self.shell.recv_ready():
                buffer += decoder.decode(self.shell.recv(65535))
                if target_text in clean_printer_data(buffer):
                    return True
            self.sleep(0.1)
        if raise_error:
            raise ShellWaitTimeout(f"画面遷移タイムアウト: '{target_text}' が表示されませんでした。")
        return False

    def wait_main_menu(self, timeout=15.0):
        """Answer pause prompts with Space and stop unless the main menu appears."""
        decoder = codecs.getincrementaldecoder("cp932")(errors="ignore")
        end_time = self.clock() + timeout
        buffer = ""
        while self.clock() < end_time:
            if self.shell.recv_ready():
                text = decoder.decode(self.shell.recv(4096))
                # Same rule as the proven login loop: one Space per packet showing a prompt.
                if any(prompt in text for prompt in SPACE_PROMPTS):
                    self.shell.send(" ")
                # The menu text is searched in all output, so a split packet is still found.
                buffer += text
                if MAIN_MENU_TEXT in buffer:
                    return True
            self.sleep(0.1)
        raise ShellWaitTimeout("QADのメインメニューを確認できないため、レポート操作を中止しました。")

    def login(self, after_select_text, after_select_timeout):
        """Common login path: 2 -> environment text -> 1 -> main menu."""
        self.pause(2)
        self.clear()
        self.send("2\r")
        self.wait_text(after_select_text, timeout=after_select_timeout)
        self.clear()
        self.send("1\r")
        self.wait_main_menu(timeout=15)

    def receive_32prn(self, max_wait=300, on_progress=None):
        """Receive a 32prn stream. End markers are searched only after the header."""
        start = self.clock()
        buffer = bytearray()
        begin = -1
        scanned = 0
        last_report = 0
        while self.clock() - start < max_wait:
            if self.shell.recv_ready():
                chunk = self.shell.recv(65535)
                if chunk:
                    buffer.extend(chunk)
                    if begin < 0:
                        begin = buffer.find(PRN_BEGIN, max(0, scanned - len(PRN_BEGIN)))
                        if begin >= 0:
                            scanned = begin
                            if on_progress:
                                on_progress("capturing", int(self.clock() - start))
                    if begin >= 0:
                        # Search only bytes not checked yet, with overlap for split markers.
                        position = max(begin, scanned - 6)
                        if PRN_STREAM_END_RE.search(buffer, position) or buffer.find(PRN_END_ESC, position) != -1:
                            return bytes(buffer), self.clock() - start
                    scanned = len(buffer)
            self.sleep(0.05)
            elapsed = int(self.clock() - start)
            if begin < 0 and elapsed > 0 and elapsed % 4 == 0 and elapsed != last_report:
                last_report = elapsed
                if on_progress:
                    on_progress("waiting", elapsed)
        raise ShellWaitTimeout("32prn ストリームの受信がタイムアウトしました。")

    def receive_rows(self, max_wait=300, on_progress=None):
        data, elapsed = self.receive_32prn(max_wait, on_progress)
        rows = parse_report_to_rows(clean_printer_data(decode_32prn_stream(data)))
        return rows, elapsed, len(data)
