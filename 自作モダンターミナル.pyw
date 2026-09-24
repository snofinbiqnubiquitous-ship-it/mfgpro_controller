import base64
import codecs
import csv
import datetime
import gzip
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time
import subprocess
import configparser
import logging
from logging.handlers import RotatingFileHandler
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# プロジェクト本体ディレクトリ（PROJECT_ROOT）の動的探索・解決
# （デスクトップ等、外部フォルダから直接スクリプトが起動された場合でも完全動作を保証）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_CANDIDATES = [
    _SCRIPT_DIR,
    Path(r"C:\Users\0138018\.antigravity\mfgpro_controller"),
    Path.home() / ".antigravity" / "mfgpro_controller",
]

PROJECT_ROOT = _SCRIPT_DIR
for _candidate in _CANDIDATES:
    if (_candidate / "terminal_core.py").is_file():
        PROJECT_ROOT = _candidate
        break

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- デバッグログ設定 (terminal_debug.log) ---
LOG_FILE = PROJECT_ROOT / "terminal_debug.log"
logger = logging.getLogger("ModernTerminal")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    try:
        rfh = RotatingFileHandler(str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
        rfh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(rfh)
    except Exception as _log_e:
        pass

def log_debug(msg):
    logger.debug(msg)

def log_info(msg):
    logger.info(msg)

def log_warning(msg):
    logger.warning(msg)

def log_error(msg, exc_info=False):
    logger.error(msg, exc_info=exc_info)

log_info("=" * 70)
log_info(f"QAD Modern Terminal 起動 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log_info(f"Python: {sys.version} | 実行パス: {sys.executable}")
log_info(f"PROJECT_ROOT: {PROJECT_ROOT}")
log_info("=" * 70)

# Explorerの関連付けは通常、ライブラリ未導入の標準Pythonを使用する。
# このプロジェクトの仮想環境があれば、GUIのimportより先に切り替える（pythonwを優先）。
if __name__ == "__main__":
    local_env = PROJECT_ROOT / ".venv"
    local_python = local_env / "Scripts" / "pythonw.exe"
    if not local_python.is_file():
        local_python = local_env / "Scripts" / "python.exe"
    if local_python.is_file() and Path(sys.prefix).resolve() != local_env.resolve():
        target_script = PROJECT_ROOT / "自作モダンターミナル.pyw"
        if not target_script.is_file():
            target_script = Path(__file__).resolve()
        os.execv(str(local_python), [str(local_python), str(target_script), *sys.argv[1:]])

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

try:
    import paramiko
    from dateutil import parser as date_parser
    from dateutil.relativedelta import relativedelta
    from PIL import Image, ImageDraw, ImageTk
    import customtkinter as ctk
    from terminal_core import COLS, ROWS, KEY_SEQUENCES, TOOLBAR_GROUPS, TerminalSession, key_sequence
    from order_entry import (
        OrderEntryPanel, DoubleControlTap, ShortcutSettingsDialog,
        normalize_shortcut, shortcut_from_key_event, read_customer_ship_to_csv,
        show_order_output,
    )
except ImportError as exc:
    if __name__ != "__main__":
        raise
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "起動に必要なファイル・ライブラリがありません",
        f"{exc}\n\nREADME.mdの導入手順を確認してください。\n"
        "terminal_core.pyはこのファイルと同じフォルダに置いてください。\n\n"
        f"使用中のPython: {sys.executable}",
        parent=root,
    )
    root.destroy()
    raise SystemExit(1)

try:
    from ctkdateentry import CTkDateEntry
    HAS_CTK_DATE_ENTRY = True
except ImportError:
    HAS_CTK_DATE_ENTRY = False


# --- 設定管理 (terminal_config.json) ---
CONFIG_FILE = PROJECT_ROOT / "terminal_config.json"

DEFAULT_DATA_TRANSMISSION_NAMES = {
    "inventory": "📦 在庫レポートGAS送信 (99.3.6.1)",
    "complaint": "📑 Complaint送信 (99.3.21.4)",
    "parallel": "⚡ 受注残＆売上 並行送信 (99.7.6.20 & 99.7.5.11)",
}

DEFAULT_CONFIG = {
    "host": "mfg03",
    "port": 22,
    "user": "takehik",
    "pass_b64": base64.b64encode(b"nhy7mju8").decode("ascii"),
    "theme": "light",
    "custom_terminal_bg": None,
    "custom_terminal_fg": None,
    "enable_windows_shortcuts": True,
    "block_server_shortcuts": True,
    "auto_excel_export": True,
    "auto_login_main_menu": True,
    "auto_winprint_on_f1": True,
    "shortcuts": [
        {"name": "在庫スナップショット", "code": "99.3.6.1"},
        {"name": "在庫移動明細", "code": "99.3.21.4"},
    ],
    "tab_aliases": {},
    "data_transmission_names": dict(DEFAULT_DATA_TRANSMISSION_NAMES),
}


def load_config():
    """設定ファイルを読み込み、存在しない場合はデフォルト値を返す"""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    if "shortcuts" not in cfg or not isinstance(cfg["shortcuts"], list):
        cfg["shortcuts"] = list(DEFAULT_CONFIG["shortcuts"])
    if "tab_aliases" not in cfg or not isinstance(cfg["tab_aliases"], dict):
        cfg["tab_aliases"] = dict(DEFAULT_CONFIG.get("tab_aliases", {}))
    if "data_transmission_names" not in cfg or not isinstance(cfg["data_transmission_names"], dict):
        cfg["data_transmission_names"] = dict(DEFAULT_DATA_TRANSMISSION_NAMES)
    if "enable_windows_shortcuts" not in cfg:
        cfg["enable_windows_shortcuts"] = True
    if "block_server_shortcuts" not in cfg:
        cfg["block_server_shortcuts"] = True
    if "auto_excel_export" not in cfg:
        cfg["auto_excel_export"] = True
    if "auto_login_main_menu" not in cfg:
        cfg["auto_login_main_menu"] = True
    if "auto_winprint_on_f1" not in cfg:
        cfg["auto_winprint_on_f1"] = True
    if not isinstance(cfg.get("shortcut_assignments"), dict):
        cfg["shortcut_assignments"] = {}
    return cfg


def save_config(cfg):
    """設定ファイルに書き込む"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"設定保存エラー: {exc}", file=sys.stderr)


# --- GAS連携用設定・共通処理 ---
INVENTORY_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbwS6dZ9umUKP71NGieiW_tDffygGtAFHKOAxyAo7cWDe3T_xMxlISSdmXoNlK6TaENfkA/exec"
COMPLAINT_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbyEwl3D8kjtbkk34V_9aJGrlgt39B480O_W3zCI6JiSC4glpS4XNj6JSC4ZiyMNKA/exec"
PARALLEL_GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbxkUsNnoE0mPLRt-6XNwEP4ns9hqSzeWKsu4i_BXSrfcPvdye2rRDp_RBvOLeTvKje-/exec"
CONFIG_INI_DIR = os.path.join(os.path.expanduser("~"), "Documents", "QAD_Tools")
CONFIG_INI_PATH = os.path.join(CONFIG_INI_DIR, "config.ini")

def decode_32prn_stream(stream_bytes: bytes) -> str:
    """32prnストリーム(uuencode + gzip)からテキストを高速解凍・復元"""
    b_start = stream_bytes.find(b"begin 0 32PRINTER")
    if b_start == -1:
        raise ValueError("32prn ヘッダー (begin 0 32PRINTER) が見つかりませんでした。")

    end_match = re.search(rb'\nend(\r|\n|$)', stream_bytes[b_start:])
    if not end_match:
        raise ValueError("32prn フッター (end) が見つかりませんでした。")

    b_end = b_start + end_match.end()
    uu_data = stream_bytes[b_start:b_end]

    uu_clean = uu_data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    compressed = codecs.decode(uu_clean, 'uu')
    raw_bytes = gzip.decompress(compressed)
    return raw_bytes.decode('cp932', errors='replace')

def clean_printer_data(text: str) -> str:
    """ANSIエスケープシーケンスおよびNULL文字を除去"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', text)
    return cleaned.replace('\x00', '')

def convert_date_format(date_str: str) -> str:
    """mm/dd/yy を YYYY/MM/DD に変換"""
    try:
        dt = datetime.datetime.strptime(date_str, "%m/%d/%y")
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return date_str

def parse_report_to_rows(input_text: str) -> list:
    """QADレポートテキスト（winPrint等）から破線(---)ヘッダーを基準に列データを二次元配列として抽出"""
    lines = input_text.splitlines()
    slices = []
    parsing_data = False
    all_rows = []

    for i, line in enumerate(lines):
        if "End of Report" in line:
            break
        if ".p" in line.lower() or line.lstrip().startswith("Page:") or "Date:" in line or line.lstrip().startswith("Item Number"):
            continue

        if line.lstrip().startswith("---") and "--- " in line:
            if not slices:
                header_line = lines[i - 1]
                parts = line.split()
                current_idx = line.find(parts[0])
                for j, p in enumerate(parts):
                    start = line.find(p, current_idx)
                    if j < len(parts) - 1:
                        next_start = line.find(parts[j + 1], start + len(p))
                        end = next_start
                    else:
                        end = 9999
                    slices.append((start, end))
                    current_idx = start + len(p)

                b_header = header_line.encode('cp932', errors='replace')
                headers = [b_header[s:e].decode('cp932', errors='ignore').strip() for s, e in slices]
                all_rows.append(headers)
            parsing_data = True
            continue

        if parsing_data:
            if not line.strip():
                continue
            row = []
            b_line = line.encode('cp932', errors='replace')
            for s, e in slices:
                if s < len(b_line):
                    val = b_line[s:e].decode('cp932', errors='ignore').strip()
                else:
                    val = ""
                if len(val) == 8 and val[2] == '/' and val[5] == '/':
                    val = convert_date_format(val)
            if any(row):
                # 2ページ目以降の改ページヘッダー行の重複混入を除外
                if all_rows and (row == all_rows[0] or (len(row) > 0 and row[0] == all_rows[0][0])):
                    continue
                all_rows.append(row)

    return all_rows

def send_to_gas_via_browser(rows_or_payload, gas_url: str, title: str = "Google Sheets へ送信中"):
    """JSONデータをbase64化し、一時HTMLからブラウザ経由でGASへPOST送信する（衝突防止UUID付き）"""
    json_str = json.dumps(rows_or_payload, ensure_ascii=False)
    b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    data_size_kb = len(b64_data) / 1024

    if isinstance(rows_or_payload, dict):
        raw_data = rows_or_payload.get("data", [])
        row_count = len(raw_data) - 1 if len(raw_data) > 1 else len(raw_data)
        menu_tag = rows_or_payload.get("menu", "data").replace(".", "_")
    else:
        row_count = len(rows_or_payload) - 1 if len(rows_or_payload) > 1 else len(rows_or_payload)
        menu_tag = "data"

    html_content = f"""<!DOCTYPE html>
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

    unique_id = f"{menu_tag}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, f"gas_submit_{unique_id}.html")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    def _launch_in_background(target_path):
        """ブラウザを既存タブで非アクティブ起動し、作業中ウィンドウのフォーカスを維持する"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            prev_hwnd = user32.GetForegroundWindow()

            LSFW_LOCK = 1
            LSFW_UNLOCK = 2
            user32.LockSetForegroundWindow(LSFW_LOCK)

            def _focus_keeper(orig_hwnd, duration=1.5):
                """ブラウザ起動直後にフォアグラウンドを元の作業中ウィンドウに維持・復帰させる"""
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
                    user32.LockSetForegroundWindow(LSFW_UNLOCK)
                except Exception:
                    pass

            if prev_hwnd and prev_hwnd != 0:
                threading.Thread(target=_focus_keeper, args=(prev_hwnd,), daemon=True).start()
        except Exception:
            pass

        # start /min で非アクティブ（最小化）として既存ブラウザにタブを開かせる
        try:
            subprocess.Popen(f'start "" /min chrome "{target_path}"', shell=True)
        except Exception:
            try:
                subprocess.Popen(f'start "" /min msedge "{target_path}"', shell=True)
            except Exception:
                try:
                    subprocess.Popen(f'start "" /min "{target_path}"', shell=True)
                except Exception as _e:
                    log_error(f"ブラウザ起動エラー: {_e}")

    _launch_in_background(path)

def wait_and_download_winprint(sftp, remote_path: str, local_temp: str, max_wait: int = 600, status_callback=None) -> int:
    """サーバー側でのファイル出力完了を監視し、ローカルにダウンロードする"""
    last_size = -1
    stable_count = 0
    wait_time = 0.0
    start_time = time.time()

    while wait_time < max_wait:
        try:
            stat = sftp.stat(remote_path)
            current_size = stat.st_size
            if current_size > 0:
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 4:  # 2秒間サイズ変化なしで出力完了と判定
                        break
                else:
                    stable_count = 0
                    last_size = current_size
        except IOError:
            pass

        time.sleep(0.5)
        wait_time += 0.5
        if status_callback and int(wait_time) % 4 == 0 and wait_time == int(wait_time):
            elapsed = int(time.time() - start_time)
            status_callback(f"サーバーでクエリ実行中... ({elapsed}秒経過)")

    if wait_time >= max_wait or last_size <= 0:
        raise TimeoutError(f"サーバー側でのレポート生成がタイムアウトしました ({int(max_wait / 60)}分)。")

    sftp.get(remote_path, local_temp)
    return last_size

def _clear_shell_buffer(shell):
    """Paramikoシェルバッファを空にする"""
    while shell.recv_ready():
        shell.recv(65535)
        time.sleep(0.05)

def _wait_shell_text(shell, target_text: str, timeout: float = 12.0, raise_error: bool = True) -> bool:
    """指定文字列がシェル出力に含まれるまで待機"""
    end_time = time.time() + timeout
    buffer = ""
    while time.time() < end_time:
        if shell.recv_ready():
            chunk_bytes = shell.recv(65535)
            chunk = chunk_bytes.decode('cp932', errors='ignore')
            buffer += chunk
            clean_buf = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', buffer).replace('\x00', '')
            if target_text in clean_buf:
                return True
        time.sleep(0.1)
    if raise_error:
        raise TimeoutError(f"画面遷移タイムアウト: '{target_text}' が表示されませんでした。")
    return False


class InputField:
    """画面上の入力欄（下線部）の位置情報を表す軽量クラス"""
    __slots__ = ("row", "start_col", "end_col")

    def __init__(self, row: int, start_col: int, end_col: int):
        self.row = row
        self.start_col = start_col
        self.end_col = end_col

    def __repr__(self):
        return f"InputField(row={self.row}, cols={self.start_col}..{self.end_col})"


# --- カラーテーマ定義 ---
COLOR_THEMES = {
    "light": {
        "name": "ライト（標準グレー）",
        "appearance_mode": "light",
        "background": "#F1F5F9",
        "panel": "#F8FAFC",
        "terminal": "#E2E8F0",
        "button": "#E2E8F0",
        "hover": "#CBD5E1",
        "accent": "#356BC4",
        "accent_hover": "#285BAF",
        "focus": "#6187C7",
        "text": "#0F172A",
        "muted": "#64748B",
        "success": "#16A34A",
        "warning": "#D97706",
        "error": "#DC2626",
        "border": "#CBD5E1",
        "cursor": "#3B82F6",
        "on_accent": "#FFFFFF",
        "disabled": "#94A3B8",
        "disabled_bg": "#E2E8F0",
        "scrollbar": "#CBD5E1",
        "scrollbar_hover": "#94A3B8",
        "reverse_bg": "#0F172A",
        "reverse_fg": "#F8FAFC",
        "menu_highlight_bg": "#0F172A",
        "menu_highlight_fg": "#F8FAFC",
        "underline_fg": "#2563EB",
    },
    "dark": {
        "name": "ダークスレート",
        "appearance_mode": "dark",
        "background": "#0F172A",
        "panel": "#1E293B",
        "terminal": "#1E293B",
        "button": "#334155",
        "hover": "#475569",
        "accent": "#38BDF8",
        "accent_hover": "#0EA5E9",
        "focus": "#38BDF8",
        "text": "#F8FAFC",
        "muted": "#94A3B8",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "error": "#EF4444",
        "border": "#334155",
        "cursor": "#38BDF8",
        "on_accent": "#0F172A",
        "disabled": "#64748B",
        "disabled_bg": "#1E293B",
        "scrollbar": "#334155",
        "scrollbar_hover": "#475569",
        "reverse_bg": "#F8FAFC",
        "reverse_fg": "#0F172A",
        "menu_highlight_bg": "#38BDF8",
        "menu_highlight_fg": "#0F172A",
        "underline_fg": "#38BDF8",
    },
    "classic_green": {
        "name": "クラシックグリーン (VT100)",
        "appearance_mode": "dark",
        "background": "#050806",
        "panel": "#0D1310",
        "terminal": "#0A0F0D",
        "button": "#1A2E22",
        "hover": "#254232",
        "accent": "#00FF66",
        "accent_hover": "#00DD55",
        "focus": "#00FF66",
        "text": "#00FF66",
        "muted": "#4B7A5E",
        "success": "#00FF66",
        "warning": "#FFD700",
        "error": "#FF4444",
        "border": "#1A2E22",
        "cursor": "#00FF66",
        "on_accent": "#050806",
        "disabled": "#2E4D3B",
        "disabled_bg": "#0D1310",
        "scrollbar": "#1A2E22",
        "scrollbar_hover": "#254232",
        "reverse_bg": "#00FF66",
        "reverse_fg": "#050806",
        "menu_highlight_bg": "#00FF66",
        "menu_highlight_fg": "#050806",
        "underline_fg": "#00E5FF",
    },
    "amber": {
        "name": "アンバー（琥珀色）",
        "appearance_mode": "dark",
        "background": "#0D0A05",
        "panel": "#1A140A",
        "terminal": "#120E07",
        "button": "#2E200F",
        "hover": "#422E16",
        "accent": "#FFB000",
        "accent_hover": "#E69E00",
        "focus": "#FFB000",
        "text": "#FFB000",
        "muted": "#8C6A38",
        "success": "#FFB000",
        "warning": "#FFD700",
        "error": "#FF4444",
        "border": "#2E200F",
        "cursor": "#FFB000",
        "on_accent": "#0D0A05",
        "disabled": "#422E16",
        "disabled_bg": "#1A140A",
        "scrollbar": "#2E200F",
        "scrollbar_hover": "#422E16",
        "reverse_bg": "#FFB000",
        "reverse_fg": "#0D0A05",
        "menu_highlight_bg": "#FFB000",
        "menu_highlight_fg": "#0D0A05",
        "underline_fg": "#38BDF8",
    },
}

# パレット用の代表的なプリセットカラー（タイル選択用）
PALETTE_BG_PRESETS = [
    ("#E2E8F0", "薄グレー"),
    ("#F8FAFC", "オフホワイト"),
    ("#FFFFFF", "ピュアホワイト"),
    ("#1E293B", "スレートダーク"),
    ("#0F172A", "ミッドナイト"),
    ("#0A0F0D", "漆黒 (グリーン用)"),
    ("#120E07", "ダークアンバー"),
    ("#18181B", "チャコール"),
]

PALETTE_FG_PRESETS = [
    ("#0F172A", "ダークネイビー"),
    ("#1E293B", "スレート"),
    ("#000000", "ブラック"),
    ("#F8FAFC", "オフホワイト"),
    ("#00FF66", "蛍光グリーン"),
    ("#38BDF8", "シアン"),
    ("#FFB000", "アンバー"),
    ("#FBBF24", "ゴールド"),
]


# --- フォント設定 ---
PREFERRED_UI_FONTS = (
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "ヒラギノ角ゴシック",
    "Hiragino Kaku Gothic Pro",
    "Yu Gothic UI",
    "游ゴシック",
    "Segoe UI",
    "sans-serif",
)

PREFERRED_TERMINAL_FONTS = (
    "Consolas",       # Windows標準 等幅（罫線の上下隙間ゼロ・完全シームレス結合）
    "Cascadia Mono",  # Windows 11/10標準 等幅
    "Cascadia Code",
    "Courier New",
    "Source Code Pro",
    "BIZ UDゴシック",
    "MS Gothic",
    "ＭＳ ゴシック",
    "monospace",
)


def find_first_available_font(candidates, fallback="sans-serif"):
    """利用可能なフォントファミリから最初に見つかったものを返す"""
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families())
        for f in candidates:
            if f in available:
                return f
    except Exception:
        pass
    return candidates[0] if candidates else fallback


def convert_date_format(date_str):
    """QADの MM/DD/YY 形式の日付を YYYY/MM/DD に変換"""
    try:
        dt = datetime.datetime.strptime(date_str, "%m/%d/%y")
        return dt.strftime("%Y/%m/%d")
    except ValueError:
        return date_str


def clean_printer_data(text):
    """プリンタデータ内のANSIエスケープシーケンスやNULL文字を除去"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', text)
    cleaned = cleaned.replace('\x00', '')
    return cleaned


def parse_report_to_rows(input_text):
    """QAD winPrint 形式のワイドレポートテキストを高精度固定長パース"""
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
                for j, p in enumerate(parts):
                    start = line.find(p, current_idx)
                    if j < len(parts) - 1:
                        next_start = line.find(parts[j+1], start + len(p))
                        end = next_start
                    else:
                        end = 9999
                    slices.append((start, end))
                    current_idx = start + len(p)

                b_header = header_line.encode('cp932', errors='replace')
                headers = [b_header[s:e].decode('cp932', errors='ignore').strip() for s, e in slices]
                all_rows.append(headers)
            parsing_data = True
            continue

        if parsing_data:
            if not line.strip():
                continue
            row = []
            b_line = line.encode('cp932', errors='replace')
            for s, e in slices:
                if s < len(b_line):
                    val = b_line[s:e].decode('cp932', errors='ignore').strip()
                else:
                    val = ""

                if len(val) == 8 and val[2] == '/' and val[5] == '/':
                    val = convert_date_format(val)
                row.append(val)
            if any(row):
                all_rows.append(row)

    return all_rows


def parse_report_text_to_table(text, deduplicate=False):
    """QADのレポート画面テキスト（固定長ハイフン区切りまたは汎用空白区切り）を2次元配列にパース"""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        log_debug("parse_report_text_to_table: 入力行が空です")
        return []

    log_debug(f"parse_report_text_to_table: 開始 (入力行数={len(lines)})")

    # 1. '--- --- ---' 形式のヘッダー区切り線を検出 (全行から探索)
    sep_idx = -1
    sep_pattern = re.compile(r'[-─]{2,}\s+[-─]{2,}')
    for i, line in enumerate(lines):
        clean = line.replace("│", " ").strip()
        if sep_pattern.search(clean) or clean.count("---") >= 2 or (clean.startswith("---") and len(clean) >= 15):
            if not any(c in line for c in ("┌", "┐", "└", "┘", "├", "┤")):
                sep_idx = i
                log_debug(f"parse_report_text_to_table: 区切り線行を検出 (行インデックス={i}): {clean[:60]}")
                break

    if sep_idx > 0:
        header_line = lines[sep_idx - 1].replace("│", " ")
        sep_line = lines[sep_idx].replace("│", " ")

        # ハイフンのブロックからカラムの開始・終了バイト位置を算出（CP932バイト幅対応）
        b_sep = sep_line.encode("cp932", errors="replace")
        parts = [p for p in re.finditer(r"[-─]+", sep_line)]
        slices = []
        for j, p in enumerate(parts):
            start = p.start()
            end = parts[j + 1].start() if j + 1 < len(parts) else len(b_sep)
            slices.append((start, end))

        b_header = header_line.encode("cp932", errors="replace")
        headers = [b_header[s:e].decode("cp932", errors="ignore").strip() for s, e in slices]
        rows = [headers]
        seen_rows = set()

        for line in lines[sep_idx + 1:]:
            clean_l = line.strip().strip("│┌┐└┘├┤─").strip()
            if not clean_l:
                continue
            clean_lower = clean_l.lower()
            if "end of report" in clean_lower or "レポート終了" in clean_l:
                break

            # 1. 罫線文字を含む行（2ページ目以降のヘッダー枠線など）
            if any(c in line for c in ("┌", "┐", "└", "┘", "├", "┤", "─")):
                continue

            # 2. 画面タイトル・プログラム番号・会社名・Criteriaなどの除外
            if (
                "criteria" in clean_lower or "livejpdb" in clean_lower or "エイブリィ" in line
                or "inventory snapshot" in clean_lower or "report criteria" in clean_lower
                or "page:" in clean_lower or ".p" in clean_lower or "date:" in clean_lower
                or "time:" in clean_lower or "user:" in clean_lower
            ):
                continue

            # 3. プログラム番号形式 (例: 99.3.6.1, 99.3.21.4) で始まる行
            if re.search(r'^\d+\.\d+(?:\.\d+)*', clean_l):
                continue

            # 4. 区切り線行またはプロンプト行の除外 (日英両対応)
            if (
                clean_l.startswith("---")
                or sep_pattern.search(line.replace("│", " ").strip())
                or any(p in clean_lower for p in ["press space", "space to continue", "space bar", "more..."])
                or any(p in clean_l for p in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行", "終了するには"])
            ):
                continue


            raw_col = line.replace("│", " ")
            b_line = raw_col.encode("cp932", errors="replace")
            row = []
            for s, e in slices:
                if s < len(b_line):
                    val = b_line[s:e].decode("cp932", errors="ignore").strip()
                else:
                    val = ""
                # 日付変換
                if len(val) == 8 and val[2] == "/" and val[5] == "/":
                    val = convert_date_format(val)
                row.append(val)

            t_row = tuple(row)
            if t_row == tuple(headers):
                continue
            if any(row):
                if not deduplicate or t_row not in seen_rows:
                    if deduplicate:
                        seen_rows.add(t_row)
                    rows.append(row)
        log_info(f"parse_report_text_to_table: 固定長パース成功 (列数={len(headers)}, データ行数={len(rows)-1})")
        return rows

    # 2. 汎用フォールバック（ヘッダー区切り線がない表や一覧画面）
    rows = []
    for line in lines:
        clean = line.strip().strip("│┌┐└┘├┤─").strip()
        clean_lower = clean.lower()
        if (
            not clean or clean.startswith("---")
            or "end of report" in clean_lower or "レポート終了" in clean
            or any(p in clean_lower for p in ["press space", "space to continue", "space bar", "more..."])
            or any(p in clean for p in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行", "終了するには"])
        ):
            continue
        cols = [c.strip() for c in re.split(r"\s{2,}|\t", clean) if c.strip()]
        if cols:
            rows.append(cols)
    log_info(f"parse_report_text_to_table: 空白区切りパース完了 (行数={len(rows)})")
    return rows


def remove_duplicate_rows(rows):
    """Excel展開前に、すべての列のデータが完全に重複している行（重複レコード）を除外する"""
    if not rows or len(rows) <= 1:
        return rows

    header = rows[0]
    unique_rows = [header]
    seen = set()
    # ヘッダー自体をseenに登録しておくことで、データ途中に混入した同一ヘッダーも除外
    seen.add(tuple(str(c).strip() for c in header))

    dup_count = 0
    for r in rows[1:]:
        # 全列が空の行はスキップ
        if not any(str(c).strip() for c in r):
            continue
        key = tuple(str(c).strip() for c in r)
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        unique_rows.append(r)

    if dup_count > 0:
        log_info(f"remove_duplicate_rows: 全列のデータが一致する重複行を {dup_count} 件除外しました (元行数={len(rows)}, 除外後={len(unique_rows)})")
    return unique_rows


def paste_to_new_excel(rows, title="QAD_Report"):
    """新規Excelブックを開き、全セルを文字列書式(@)に設定してデータを一括展開する（前ゼロ落ち・指数変換を完全防止）"""
    if not rows:
        log_warning("paste_to_new_excel: 展開するデータが空です")
        return False, "展開するデータがありません"

    # Excel出力前に全列のデータが重複している行を除外
    orig_len = len(rows)
    rows = remove_duplicate_rows(rows)
    removed_dups = orig_len - len(rows)

    num_rows = len(rows)
    num_cols = max(len(r) for r in rows) if rows else 0
    if num_rows == 0 or num_cols == 0:
        log_warning("paste_to_new_excel: 有効な行・列が0です")
        return False, "有効なデータ行がありません"

    dup_info = f"（重複 {removed_dups} 件を除外）" if removed_dups > 0 else ""
    log_info(f"paste_to_new_excel: 開始 (行数={num_rows}, 列数={num_cols}, タイトル={title}{dup_info})")

    # 1. win32com による Excel COM 直接操作（前ゼロ落ち・指数変換なしの完全文字列貼り付け）
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = True
            wb = excel.Workbooks.Add()
            ws = wb.Worksheets(1)
            try:
                ws.Name = title[:31]
            except Exception:
                pass

            grid = []
            for r in rows:
                padded = [str(c) if c is not None else "" for c in r] + [""] * (num_cols - len(r))
                grid.append(tuple(padded))

            target_range = ws.Range(ws.Cells(1, 1), ws.Cells(num_rows, num_cols))
            target_range.NumberFormat = "@"  # 全セル文字列書式
            target_range.Value = tuple(grid)
            try:
                target_range.Columns.AutoFit()
            except Exception:
                pass

            try:
                excel.WindowState = -4143  # xlNormal
            except Exception:
                pass
            excel.Visible = True
            msg = f"Excelに {num_rows - 1} 件のデータを展開しました{dup_info}（文字列書式）"
            log_info(f"paste_to_new_excel: COM操作成功 - {msg}")
            return True, msg
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:
        log_warning(f"Excel COM連携エラー (フォールバックCSVへ移行): {exc}")

    # 2. フォールバック: BOM付きUTF-8 CSV で直接起動
    try:
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = Path(tempfile.gettempdir()) / "qad_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        csv_path = export_dir / f"{title}_{now_str}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        os.startfile(str(csv_path))
        msg = f"CSVを生成しExcelで起動しました ({num_rows - 1} 件{dup_info})"
        log_info(f"paste_to_new_excel: フォールバックCSV起動成功 - {csv_path} ({msg})")
        return True, msg
    except Exception as e:
        log_error(f"paste_to_new_excel: CSVフォールバックも失敗: {e}", exc_info=True)
        return False, f"Excel起動失敗: {e}"



class ActionButton(ctk.CTkFrame):
    """角丸サーフェスとネイティブボタントラバーサルを備えたアクションボタン"""

    def __init__(self, parent, text, command, primary=False, font_family="Yu Gothic UI", colors=None):
        self.primary = primary
        self.colors = colors or COLOR_THEMES["light"]
        self.surface = self.colors["accent"] if primary else self.colors["button"]
        super().__init__(parent, fg_color=self.surface, corner_radius=11,
                         border_width=2, border_color=self.surface)
        self.grid_columnconfigure(0, weight=1)
        self._control = tk.Button(
            self, text=text, command=command, font=(font_family, 10),
            bg=self.surface, fg=self.colors["on_accent"] if primary else self.colors["text"],
            activebackground=self.colors["accent_hover"] if primary else self.colors["hover"],
            activeforeground=self.colors["on_accent"] if primary else self.colors["text"],
            disabledforeground=self.colors["disabled"], relief="flat", bd=0,
            highlightthickness=0, cursor="hand2", takefocus=True, padx=4, pady=6,
        )
        self._control.grid(row=0, column=0, padx=9, pady=4, sticky="ew")
        self._control.bind("<FocusIn>", lambda event: super(ActionButton, self).configure(border_color=self.colors["focus"]))
        self._control.bind("<FocusOut>", lambda event: super(ActionButton, self).configure(border_color=self.surface))
        self._control.bind("<Enter>", lambda event: self._hover(True))
        self._control.bind("<Leave>", lambda event: self._hover(False))

    def update_colors(self, colors):
        self.colors = colors
        self.surface = self.colors["accent"] if self.primary else self.colors["button"]
        self.configure(fg_color=self.surface, border_color=self.surface)
        self._control.configure(
            bg=self.surface,
            fg=self.colors["on_accent"] if self.primary else self.colors["text"],
            activebackground=self.colors["accent_hover"] if self.primary else self.colors["hover"],
            activeforeground=self.colors["on_accent"] if self.primary else self.colors["text"],
            disabledforeground=self.colors["disabled"],
        )

    def _hover(self, entered):
        if self._control.cget("state") == "disabled":
            return
        color = self.colors["accent_hover" if self.primary else "hover"] if entered else self.surface
        super().configure(fg_color=color)
        self._control.configure(bg=color)

    def configure(self, require_redraw=False, **kwargs):
        state = kwargs.pop("state", None)
        super().configure(require_redraw=require_redraw, **kwargs)
        if state is not None:
            enabled = state != "disabled"
            self.surface = self.colors["accent" if self.primary else "button"] if enabled else self.colors["disabled_bg"]
            self._control.configure(state=state, bg=self.surface, takefocus=enabled,
                                    cursor="hand2" if enabled else "arrow")
            super().configure(fg_color=self.surface, border_color=self.surface)

    def cget(self, name):
        if name in ("state", "text"):
            return self._control.cget(name)
        return super().cget(name)

    def focus_set(self):
        self._control.focus_set()

    def invoke(self):
        return self._control.invoke()


class ColorPaletteDialog(ctk.CTkToplevel):
    """グラフィカルなカラーパレット設定ウィンドウ"""

    def __init__(self, parent, terminal_app):
        super().__init__(parent)
        self.app = terminal_app

        self.title("カラーパレット設定")
        self.geometry("540x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 540) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 520) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(main_frame, text="🎨 カラーパレット & テーマ設定", font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(10, 12))

        # 1. プリセットテーマ
        theme_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        theme_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(theme_frame, text="標準テーマテンプレート:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 6))

        t_grid = ctk.CTkFrame(theme_frame, fg_color="transparent")
        t_grid.pack(fill="x")
        t_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        themes = [
            ("ライト (標準)", "light", "#E2E8F0", "#0F172A"),
            ("ダークスレート", "dark", "#1E293B", "#F8FAFC"),
            ("グリーン (VT100)", "classic_green", "#0A0F0D", "#00FF66"),
            ("アンバー (琥珀)", "amber", "#120E07", "#FFB000"),
        ]
        for idx, (label, key, bg, fg) in enumerate(themes):
            btn = ctk.CTkButton(
                t_grid, text=label, fg_color=bg, text_color=fg,
                border_width=1, border_color="#64748B", hover_color=bg,
                command=lambda k=key: self._select_theme(k), height=32, font=ctk.CTkFont(size=11, weight="bold")
            )
            btn.grid(row=0, column=idx, padx=4, sticky="ew")

        # 2. ターミナル背景色パレット
        bg_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bg_frame.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(bg_frame, text="ターミナル背景色:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        bg_grid = ctk.CTkFrame(bg_frame, fg_color="transparent")
        bg_grid.pack(fill="x")
        bg_grid.grid_columnconfigure(list(range(len(PALETTE_BG_PRESETS))), weight=1)

        for idx, (color, name) in enumerate(PALETTE_BG_PRESETS):
            btn = ctk.CTkButton(
                bg_grid, text="", fg_color=color, hover_color=color,
                border_width=1, border_color="#64748B", width=34, height=28,
                command=lambda c=color: self._set_bg(c)
            )
            btn.grid(row=0, column=idx, padx=2, sticky="ew")

        # 3. ターミナル文字色パレット
        fg_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        fg_frame.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(fg_frame, text="ターミナル文字色:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        fg_grid = ctk.CTkFrame(fg_frame, fg_color="transparent")
        fg_grid.pack(fill="x")
        fg_grid.grid_columnconfigure(list(range(len(PALETTE_FG_PRESETS))), weight=1)

        for idx, (color, name) in enumerate(PALETTE_FG_PRESETS):
            btn = ctk.CTkButton(
                fg_grid, text="Aa", fg_color="#1E293B", text_color=color, hover_color="#334155",
                border_width=1, border_color="#64748B", width=34, height=28,
                command=lambda c=color: self._set_fg(c), font=ctk.CTkFont(size=11, weight="bold")
            )
            btn.grid(row=0, column=idx, padx=2, sticky="ew")

        # 4. 自由なカラーピッカー
        custom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        custom_frame.pack(fill="x", padx=16, pady=(14, 4))
        custom_frame.grid_columnconfigure((0, 1), weight=1)

        custom_bg_btn = ctk.CTkButton(
            custom_frame, text="🎨 背景色を自由に選ぶ...", fg_color="#356BC4", hover_color="#285BAF",
            command=self._pick_custom_bg, height=34
        )
        custom_bg_btn.grid(row=0, column=0, padx=6, sticky="ew")

        custom_fg_btn = ctk.CTkButton(
            custom_frame, text="✏️ 文字色を自由に選ぶ...", fg_color="#356BC4", hover_color="#285BAF",
            command=self._pick_custom_fg, height=34
        )
        custom_fg_btn.grid(row=0, column=1, padx=6, sticky="ew")

        # 5. 下部操作ボタン
        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=16, pady=(20, 8))
        bottom_frame.grid_columnconfigure((0, 1), weight=1)

        reset_btn = ctk.CTkButton(
            bottom_frame, text="標準の配色に戻す", fg_color="#64748B", hover_color="#475569",
            command=self._reset_colors, height=32
        )
        reset_btn.grid(row=0, column=0, padx=6, sticky="ew")

        close_btn = ctk.CTkButton(
            bottom_frame, text="閉じる", fg_color="#16A34A", hover_color="#15803D",
            command=self.destroy, height=32
        )
        close_btn.grid(row=0, column=1, padx=6, sticky="ew")

    def _select_theme(self, theme_key):
        self.app.switch_theme(theme_key)

    def _set_bg(self, color):
        self.app.set_terminal_custom_color(bg=color)

    def _set_fg(self, color):
        self.app.set_terminal_custom_color(fg=color)

    def _pick_custom_bg(self):
        cur_bg = self.app.terminal_colors.get("terminal", "#E2E8F0")
        color = colorchooser.askcolor(initialcolor=cur_bg, title="ターミナル背景色を選択", parent=self)
        if color and color[1]:
            self.app.set_terminal_custom_color(bg=color[1])

    def _pick_custom_fg(self):
        cur_fg = self.app.terminal_colors.get("text", "#0F172A")
        color = colorchooser.askcolor(initialcolor=cur_fg, title="ターミナル文字色を選択", parent=self)
        if color and color[1]:
            self.app.set_terminal_custom_color(fg=color[1])

    def _reset_colors(self):
        self.app.reset_custom_colors()


class LoginConfigDialog(ctk.CTkToplevel):
    """ログイン情報（ホスト・ポート・ユーザー・パスワード）の編集・保存ダイアログ"""

    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_save_callback = on_save_callback

        self.title("ログイン情報の設定")
        self.geometry("440x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 440) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 380) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="QAD 接続設定", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(12, 16))

        # ホスト名
        row_host = ctk.CTkFrame(frame, fg_color="transparent")
        row_host.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_host, text="ホスト名:", width=90, anchor="w").pack(side="left")
        self.host_entry = ctk.CTkEntry(row_host, width=220)
        self.host_entry.pack(side="left", fill="x", expand=True)
        self.host_entry.insert(0, self.config.get("host", "mfg03"))

        # ポート番号
        row_port = ctk.CTkFrame(frame, fg_color="transparent")
        row_port.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_port, text="ポート番号:", width=90, anchor="w").pack(side="left")
        self.port_entry = ctk.CTkEntry(row_port, width=220)
        self.port_entry.pack(side="left", fill="x", expand=True)
        self.port_entry.insert(0, str(self.config.get("port", 22)))

        # ユーザー名
        row_user = ctk.CTkFrame(frame, fg_color="transparent")
        row_user.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_user, text="ユーザー名:", width=90, anchor="w").pack(side="left")
        self.user_entry = ctk.CTkEntry(row_user, width=220)
        self.user_entry.pack(side="left", fill="x", expand=True)
        self.user_entry.insert(0, self.config.get("user", "takehik"))

        # パスワード
        row_pass = ctk.CTkFrame(frame, fg_color="transparent")
        row_pass.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_pass, text="パスワード:", width=90, anchor="w").pack(side="left")
        self.pass_entry = ctk.CTkEntry(row_pass, width=220, show="*")
        self.pass_entry.pack(side="left", fill="x", expand=True)

        saved_pass = ""
        b64 = self.config.get("pass_b64", "")
        if b64:
            try:
                saved_pass = base64.b64decode(b64.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                pass
        self.pass_entry.insert(0, saved_pass)

        # パスワード表示トグル
        self.show_pass_var = ctk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(
            frame, text="パスワードを表示する", variable=self.show_pass_var,
            command=lambda: self.pass_entry.configure(show="" if self.show_pass_var.get() else "*"),
            checkbox_width=18, checkbox_height=18, font=ctk.CTkFont(size=12)
        )
        chk.pack(anchor="w", padx=110, pady=(2, 14))

        # ボタン
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(10, 10))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
                                   command=self.destroy)
        cancel_btn.grid(row=0, column=0, padx=8, sticky="ew")

        save_btn = ctk.CTkButton(btn_frame, text="保存して適用", fg_color="#356BC4", hover_color="#285BAF",
                                 command=self._on_save)
        save_btn.grid(row=0, column=1, padx=8, sticky="ew")

    def _on_save(self):
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        pwd = self.pass_entry.get()

        if not host or not user:
            messagebox.showwarning("入力エラー", "ホスト名とユーザー名は必須です。", parent=self)
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("入力エラー", "ポート番号は半角数字で入力してください。", parent=self)
            return

        self.config["host"] = host
        self.config["port"] = port
        self.config["user"] = user
        self.config["pass_b64"] = base64.b64encode(pwd.encode("utf-8")).decode("ascii")

        save_config(self.config)
        if self.on_save_callback:
            self.on_save_callback(self.config)
        self.destroy()
        messagebox.showinfo("設定完了", "ログイン情報を保存しました。\n次回の接続から適用されます。", parent=self.parent)


class ShortcutDialog(ctk.CTkToplevel):
    """メニュー番号へ直接移動するショートカットを追加・再編集するダイアログ"""

    def __init__(self, parent, on_save_callback, initial_name="", initial_code="", is_edit=False, on_delete_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.on_delete_callback = on_delete_callback
        self.initial_name = initial_name
        self.initial_code = initial_code
        self.is_edit = is_edit

        self.title("ショートカットの編集" if is_edit else "ショートカットの追加")
        self.geometry("380x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 380) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 240) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        title_text = "✏️ ショートカットの編集" if self.is_edit else "⚡ ショートカットの追加"
        ctk.CTkLabel(frame, text=title_text, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(6, 12))

        # 表示名
        row_name = ctk.CTkFrame(frame, fg_color="transparent")
        row_name.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_name, text="表示名:", width=85, anchor="w").pack(side="left")
        self.name_entry = ctk.CTkEntry(row_name, width=210, placeholder_text="例: 在庫スナップショット")
        if self.initial_name:
            self.name_entry.insert(0, self.initial_name)
        self.name_entry.pack(side="left", fill="x", expand=True)

        # メニュー番号
        row_code = ctk.CTkFrame(frame, fg_color="transparent")
        row_code.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_code, text="メニュー番号:", width=85, anchor="w").pack(side="left")
        self.code_entry = ctk.CTkEntry(row_code, width=210, placeholder_text="例: 99.3.6.1")
        if self.initial_code:
            self.code_entry.insert(0, self.initial_code)
        self.code_entry.pack(side="left", fill="x", expand=True)

        # ボタン
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(16, 6))

        if self.is_edit and self.on_delete_callback:
            btn_frame.grid_columnconfigure((0, 1, 2), weight=1)
            del_btn = ctk.CTkButton(btn_frame, text="削除", fg_color="#DC2626", hover_color="#B91C1C",
                                    command=self._on_delete)
            del_btn.grid(row=0, column=0, padx=4, sticky="ew")

            cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
                                       command=self.destroy)
            cancel_btn.grid(row=0, column=1, padx=4, sticky="ew")

            save_btn = ctk.CTkButton(btn_frame, text="更新する", fg_color="#356BC4", hover_color="#285BAF",
                                     command=self._on_save)
            save_btn.grid(row=0, column=2, padx=4, sticky="ew")
        else:
            btn_frame.grid_columnconfigure((0, 1), weight=1)
            cancel_btn = ctk.CTkButton(btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
                                       command=self.destroy)
            cancel_btn.grid(row=0, column=0, padx=6, sticky="ew")

            save_btn_text = "更新する" if self.is_edit else "追加する"
            save_btn = ctk.CTkButton(btn_frame, text=save_btn_text, fg_color="#356BC4", hover_color="#285BAF",
                                     command=self._on_save)
            save_btn.grid(row=0, column=1, padx=6, sticky="ew")

        self.name_entry.focus_set()

    def _on_delete(self):
        if messagebox.askyesno("削除確認", f"ショートカット「{self.initial_name}」を削除しますか？", parent=self):
            if self.on_delete_callback:
                self.on_delete_callback()
            self.destroy()

    def _on_save(self):
        name = self.name_entry.get().strip()
        code = self.code_entry.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "表示名を入力してください。", parent=self)
            return
        if not code:
            messagebox.showwarning("入力エラー", "メニュー番号を入力してください。", parent=self)
            return
        if self.on_save_callback:
            self.on_save_callback(name, code)
        self.destroy()


# 既存コードとの後方互換性エイリアス
AddShortcutDialog = ShortcutDialog


class ComplaintDialog(ctk.CTkToplevel):
    """99.3.21.4 から Complaint データを抽出して GAS へ転送する条件入力ダイアログ"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Complaint 抽出＆GAS転送")
        self.geometry("440x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 440) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 480) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame, text="📝 Complaint 抽出＆GAS転送 (99.3.21.4)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(6, 14))

        # 1. Item code
        ctk.CTkLabel(frame, text="Item code (必須):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.item_entry = ctk.CTkEntry(frame, width=380, placeholder_text="例: BW0100D")
        self.item_entry.pack(fill="x", padx=16, pady=(0, 10))

        # 日付初期値の算出
        today = datetime.date.today()
        six_months_ago = today - relativedelta(months=6)

        # 2. Start date
        ctk.CTkLabel(frame, text="Start date (YYYY/MM/DD):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        if HAS_CTK_DATE_ENTRY:
            self.start_cal = CTkDateEntry(frame, width=380)
            self.start_cal.variable.set(six_months_ago.strftime("%Y/%m/%d"))
            self.start_cal.variable.trace_add("write", lambda *args: self._format_date_var(self.start_cal.variable))
            self.start_cal.pack(fill="x", padx=16, pady=(0, 10))
            self._start_is_date_entry = True
        else:
            self.start_cal = ctk.CTkEntry(frame, width=380)
            self.start_cal.insert(0, six_months_ago.strftime("%Y/%m/%d"))
            self.start_cal.pack(fill="x", padx=16, pady=(0, 10))
            self._start_is_date_entry = False

        # 3. End date
        ctk.CTkLabel(frame, text="End date (YYYY/MM/DD):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        if HAS_CTK_DATE_ENTRY:
            self.end_cal = CTkDateEntry(frame, width=380)
            self.end_cal.variable.set(today.strftime("%Y/%m/%d"))
            self.end_cal.variable.trace_add("write", lambda *args: self._format_date_var(self.end_cal.variable))
            self.end_cal.pack(fill="x", padx=16, pady=(0, 10))
            self._end_is_date_entry = True
        else:
            self.end_cal = ctk.CTkEntry(frame, width=380)
            self.end_cal.insert(0, today.strftime("%Y/%m/%d"))
            self.end_cal.pack(fill="x", padx=16, pady=(0, 10))
            self._end_is_date_entry = False

        # 4. Cheese lot / Nlot
        ctk.CTkLabel(frame, text="Cheese lot / Nlot (空白可):", anchor="w").pack(fill="x", padx=16, pady=(0, 2))
        self.lot_entry = ctk.CTkEntry(frame, width=380, placeholder_text="空白可")
        self.lot_entry.pack(fill="x", padx=16, pady=(0, 12))

        # ステータス表示ラベル
        self.status_label = ctk.CTkLabel(
            frame, text="", text_color="#D97706",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.status_label.pack(fill="x", padx=16, pady=(0, 8))

        # ボタン
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 6))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="キャンセル", fg_color="#94A3B8", hover_color="#64748B",
            command=self.destroy
        )
        self.cancel_btn.grid(row=0, column=0, padx=6, sticky="ew")

        self.submit_btn = ctk.CTkButton(
            btn_frame, text="OK (抽出＆GAS転送)", fg_color="#4F46E5", hover_color="#4338CA",
            font=ctk.CTkFont(weight="bold"), command=self.on_submit
        )
        self.submit_btn.grid(row=0, column=1, padx=6, sticky="ew")

        self.item_entry.focus_set()

    def _format_date_var(self, var):
        if not var:
            return
        val = var.get()
        if not val or re.match(r'^\d{4}[/-]\d{2}[/-]\d{2}$', val):
            return
        try:
            dt = date_parser.parse(val)
            new_val = dt.strftime("%Y/%m/%d")
            if new_val != val:
                var.set(new_val)
        except Exception:
            pass

    def get_start_date_str(self) -> str:
        if self._start_is_date_entry:
            return self.start_cal.variable.get().strip()
        return self.start_cal.get().strip()

    def get_end_date_str(self) -> str:
        if self._end_is_date_entry:
            return self.end_cal.variable.get().strip()
        return self.end_cal.get().strip()

    def update_dialog_status(self, text: str, color: str = "#D97706"):
        self.after(0, lambda: self.status_label.configure(text=text, text_color=color))

    def on_submit(self):
        item_num = self.item_entry.get().strip()
        item_lot = self.lot_entry.get().strip()

        if not item_num:
            messagebox.showwarning("入力エラー", "Item code は必須項目です。", parent=self)
            self.item_entry.focus_set()
            return

        start_val = self.get_start_date_str()
        end_val = self.get_end_date_str()

        try:
            start_day_server = date_parser.parse(start_val).strftime("%m/%d/%y")
        except Exception:
            start_day_server = start_val

        try:
            end_day_server = date_parser.parse(end_val).strftime("%m/%d/%y")
        except Exception:
            end_day_server = end_val

        self.submit_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.status_label.configure(text="🚀 サーバーと通信中... (データ抽出中)", text_color="#D97706")

        self.parent.run_complaint_gas_transmission(
            item_num=item_num,
            start_day=start_day_server,
            end_day=end_day_server,
            item_lot=item_lot,
            dialog_ref=self
        )


class TabAliasDialog(ctk.CTkToplevel):
    """タブ表示名（エイリアス）の設定ダイアログ"""
    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_save_callback = on_save_callback
        self.aliases = dict(config.get("tab_aliases", {}))

        self.title("タブ表示名（エイリアス）の設定")
        self.geometry("520x460")
        self.minsize(460, 380)
        self.configure(fg_color=parent.ui_colors["background"])
        self.transient(parent)
        self.grab_set()

        # ヘッダー説明
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(16, 8))
        lbl_title = ctk.CTkLabel(
            header_frame,
            text="🏷️ タブ表示名（メニュー番号エイリアス）の設定",
            font=ctk.CTkFont(family=parent.ui_font_family, size=15, weight="bold"),
            text_color=parent.ui_colors["text"]
        )
        lbl_title.pack(anchor="w")

        lbl_desc = ctk.CTkLabel(
            header_frame,
            text="特定のメニュー番号に対し、タブに表示するカスタム名称を設定できます。\n（未設定のメニューは番号のみが表示されます）",
            font=ctk.CTkFont(family=parent.ui_font_family, size=11),
            text_color=parent.ui_colors["muted"],
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(4, 0))

        # 一覧表示領域（スクロールフレーム）
        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=parent.ui_colors["panel"],
            corner_radius=8,
            border_width=1,
            border_color=parent.ui_colors["border"]
        )
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=8)

        # 入力フォーム（メニュー番号 ＆ 表示名）
        input_frame = ctk.CTkFrame(self, fg_color=parent.ui_colors["panel"], corner_radius=8)
        input_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(input_frame, text="メニュー番号:", font=ctk.CTkFont(family=parent.ui_font_family, size=12)).grid(row=0, column=0, padx=(12, 4), pady=10, sticky="w")
        self.code_entry = ctk.CTkEntry(input_frame, placeholder_text="例: 99.7.6.20", width=110, font=ctk.CTkFont(family=parent.ui_font_family, size=12))
        self.code_entry.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="w")

        ctk.CTkLabel(input_frame, text="表示名:", font=ctk.CTkFont(family=parent.ui_font_family, size=12)).grid(row=0, column=2, padx=(0, 4), pady=10, sticky="w")
        self.name_entry = ctk.CTkEntry(input_frame, placeholder_text="例: 受注残", width=140, font=ctk.CTkFont(family=parent.ui_font_family, size=12))
        self.name_entry.grid(row=0, column=3, padx=(0, 10), pady=10, sticky="w")

        self.add_btn = ctk.CTkButton(
            input_frame,
            text="＋ 追加/更新",
            width=80,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=parent.ui_font_family, size=12, weight="bold"),
            command=self._add_or_update_alias
        )
        self.add_btn.grid(row=0, column=4, padx=(0, 12), pady=10, sticky="e")

        # 下部ボタンバー
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(4, 16))

        close_btn = ctk.CTkButton(
            btn_frame,
            text="閉じる",
            width=90,
            fg_color=parent.ui_colors["button"],
            hover_color=parent.ui_colors["hover"],
            text_color=parent.ui_colors["text"],
            font=ctk.CTkFont(family=parent.ui_font_family, size=12),
            command=self.destroy
        )
        close_btn.pack(side="right")

        self._refresh_list()

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not self.aliases:
            empty_lbl = ctk.CTkLabel(
                self.list_frame,
                text="カスタム表示名がまだ登録されていません。\n下の入力欄から追加してください。",
                text_color=self.parent.ui_colors["muted"],
                font=ctk.CTkFont(family=self.parent.ui_font_family, size=12)
            )
            empty_lbl.pack(pady=30)
            return

        for code, name in sorted(self.aliases.items()):
            row_frame = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=3, padx=6)

            code_lbl = ctk.CTkLabel(
                row_frame,
                text=code,
                width=110,
                anchor="w",
                font=ctk.CTkFont(family=self.parent.ui_font_family, size=12, weight="bold"),
                text_color=self.parent.ui_colors["text"]
            )
            code_lbl.pack(side="left", padx=(4, 8))

            arrow_lbl = ctk.CTkLabel(
                row_frame,
                text="➔",
                width=24,
                text_color=self.parent.ui_colors["muted"],
                font=ctk.CTkFont(size=11)
            )
            arrow_lbl.pack(side="left", padx=(0, 8))

            name_lbl = ctk.CTkLabel(
                row_frame,
                text=name,
                anchor="w",
                font=ctk.CTkFont(family=self.parent.ui_font_family, size=12),
                text_color="#2563EB"
            )
            name_lbl.pack(side="left", fill="x", expand=True)

            edit_btn = ctk.CTkButton(
                row_frame,
                text="編集",
                width=46,
                height=24,
                fg_color=self.parent.ui_colors["button"],
                hover_color=self.parent.ui_colors["hover"],
                text_color=self.parent.ui_colors["text"],
                font=ctk.CTkFont(family=self.parent.ui_font_family, size=11),
                command=lambda c=code, n=name: self._load_for_edit(c, n)
            )
            edit_btn.pack(side="right", padx=(4, 0))

            del_btn = ctk.CTkButton(
                row_frame,
                text="削除",
                width=46,
                height=24,
                fg_color="transparent",
                hover_color="#EF4444",
                text_color="#EF4444",
                font=ctk.CTkFont(family=self.parent.ui_font_family, size=11),
                command=lambda c=code: self._delete_alias(c)
            )
            del_btn.pack(side="right", padx=(4, 0))

    def _load_for_edit(self, code, name):
        self.code_entry.delete(0, "end")
        self.code_entry.insert(0, code)
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, name)
        self.name_entry.focus_set()

    def _add_or_update_alias(self):
        code = self.code_entry.get().strip()
        name = self.name_entry.get().strip()
        if not code or not name:
            messagebox.showwarning("入力エラー", "メニュー番号と表示名の両方を入力してください。", parent=self)
            return

        self.aliases[code] = name
        self.config["tab_aliases"] = self.aliases
        save_config(self.config)
        self.on_save_callback()
        self._refresh_list()
        self.code_entry.delete(0, "end")
        self.name_entry.delete(0, "end")

    def _delete_alias(self, code):
        if code in self.aliases:
            del self.aliases[code]
            self.config["tab_aliases"] = self.aliases
            save_config(self.config)
            self.on_save_callback()
            self._refresh_list()


class DataTransmissionSettingDialog(ctk.CTkToplevel):
    """データ送信ボタン名のカスタマイズ設定ダイアログ"""
    def __init__(self, parent, focus_key: str = "inventory", on_save_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback

        self.title("データ送信ボタン名の設定")
        self.geometry("560x400")
        self.minsize(500, 350)
        self.configure(fg_color=parent.ui_colors["background"])
        self.transient(parent)
        self.grab_set()

        dt_names = parent.config.get("data_transmission_names", {})

        # ヘッダー説明
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(16, 8))
        lbl_title = ctk.CTkLabel(
            header_frame,
            text="📤 データ送信ボタン名の編集",
            font=ctk.CTkFont(family=parent.ui_font_family, size=15, weight="bold"),
            text_color=parent.ui_colors["text"]
        )
        lbl_title.pack(anchor="w")

        lbl_desc = ctk.CTkLabel(
            header_frame,
            text="ツールバーに表示されるデータ送信ボタンの表示名を自由に変更できます。\n空欄のまま保存した項目は自動的に初期名に戻ります。",
            font=ctk.CTkFont(family=parent.ui_font_family, size=11),
            text_color=parent.ui_colors["muted"],
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(4, 0))

        # 入力フォームエリア
        form_frame = ctk.CTkFrame(self, fg_color=parent.ui_colors["panel"], corner_radius=8)
        form_frame.pack(fill="both", expand=True, padx=20, pady=8)

        self.entries = {}
        items = [
            ("inventory", "在庫レポート (99.3.6.1)", DEFAULT_DATA_TRANSMISSION_NAMES["inventory"], "#059669"),
            ("complaint", "Complaint (99.3.21.4)", DEFAULT_DATA_TRANSMISSION_NAMES["complaint"], "#4F46E5"),
            ("parallel", "受注残＆売上 並行 (99.7.6.20 & 11)", DEFAULT_DATA_TRANSMISSION_NAMES["parallel"], "#D97706"),
        ]

        for row_idx, (key, label, default_val, badge_color) in enumerate(items):
            cur_val = dt_names.get(key, default_val)

            # ラベル行
            row_label_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_label_frame.pack(fill="x", padx=16, pady=(12 if row_idx == 0 else 8, 2))

            badge = ctk.CTkLabel(
                row_label_frame, text="●", text_color=badge_color,
                font=ctk.CTkFont(family=parent.ui_font_family, size=10)
            )
            badge.pack(side="left", padx=(0, 4))

            lbl_item = ctk.CTkLabel(
                row_label_frame, text=label,
                font=ctk.CTkFont(family=parent.ui_font_family, size=12, weight="bold"),
                text_color=parent.ui_colors["text"]
            )
            lbl_item.pack(side="left")

            # 入力＋リセットボタン行
            input_row = ctk.CTkFrame(form_frame, fg_color="transparent")
            input_row.pack(fill="x", padx=16, pady=(0, 6))

            entry = ctk.CTkEntry(
                input_row,
                font=ctk.CTkFont(family=parent.ui_font_family, size=12),
                height=30
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entry.insert(0, cur_val)
            self.entries[key] = entry

            btn_rst = ctk.CTkButton(
                input_row, text="初期名", width=60, height=28,
                fg_color="transparent", hover_color=parent.ui_colors["hover"],
                border_width=1, border_color=parent.ui_colors["border"],
                text_color=parent.ui_colors["text"],
                font=ctk.CTkFont(family=parent.ui_font_family, size=11),
                command=lambda e=entry, d=default_val: (e.delete(0, tk.END), e.insert(0, d))
            )
            btn_rst.pack(side="right")

            if key == focus_key:
                entry.focus_set()
                entry.select_range(0, tk.END)

        # 下部ボタンバー
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=(4, 16))

        all_reset_btn = ctk.CTkButton(
            btn_bar,
            text="全項目を初期名に戻す",
            width=140,
            fg_color="transparent",
            hover_color=parent.ui_colors["hover"],
            border_width=1,
            border_color=parent.ui_colors["border"],
            text_color=parent.ui_colors["text"],
            font=ctk.CTkFont(family=parent.ui_font_family, size=12),
            command=self._reset_all
        )
        all_reset_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_bar,
            text="保存",
            width=90,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=parent.ui_font_family, size=12, weight="bold"),
            command=self._save
        )
        save_btn.pack(side="right", padx=(8, 0))

        cancel_btn = ctk.CTkButton(
            btn_bar,
            text="キャンセル",
            width=90,
            fg_color=parent.ui_colors["button"],
            hover_color=parent.ui_colors["hover"],
            text_color=parent.ui_colors["text"],
            font=ctk.CTkFont(family=parent.ui_font_family, size=12),
            command=self.destroy
        )
        cancel_btn.pack(side="right")

    def _reset_all(self):
        for k, entry in self.entries.items():
            def_val = DEFAULT_DATA_TRANSMISSION_NAMES.get(k, "")
            entry.delete(0, tk.END)
            entry.insert(0, def_val)

    def _save(self):
        results = {}
        for k, entry in self.entries.items():
            val = entry.get().strip()
            if not val:
                val = DEFAULT_DATA_TRANSMISSION_NAMES.get(k, "")
            results[k] = val
        if self.on_save_callback:
            self.on_save_callback(results)
        self.destroy()


class TerminalTab:
    """タブごとに独立したSSHセッション、バッファ、テキストボックスを保持するクラス"""
    def __init__(self, app, tab_id: int, title: str):
        self.app = app
        self.tab_id = tab_id
        self.title = title
        self.session = None
        self.events = queue.Queue()
        self.is_connected = False
        self.closing = False
        self.rendered_lines = [None] * ROWS
        self.raw_lines = {}
        self.font_size = 18
        self.active_cols = 80
        self.auto_fit = True
        self._resize_job = None

        self.current_cursor = None
        self.cursor_blink_visible = True
        self.is_navigating_field = False
        self._is_waiting_query = False

        # タブウィジェット参照
        self.tab_frame = None
        self.tab_label = None

        # ターミナルパネル & テキストボックス（terminal_container 内に配置）
        self.terminal_panel = ctk.CTkFrame(
            app.terminal_container,
            fg_color=app.terminal_colors["terminal"],
            corner_radius=0
        )
        self.terminal_panel.grid_columnconfigure(0, weight=1)
        self.terminal_panel.grid_rowconfigure(0, weight=1)

        self.terminal_font = ctk.CTkFont(family=app.terminal_font_family, size=self.font_size)
        self.textbox = ctk.CTkTextbox(
            self.terminal_panel,
            font=self.terminal_font,
            fg_color=app.terminal_colors["terminal"],
            text_color=app.terminal_colors["text"],
            wrap="none",
            corner_radius=0,
            border_width=0,
            activate_scrollbars=False,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")
        self.textbox._textbox.configure(spacing1=0, spacing2=0, spacing3=0, padx=0, pady=0)

        app._apply_text_tags_to_widget(self.textbox)
        self._bind_events()

    def _bind_events(self):
        tb = self.textbox
        app = self.app
        tb.bind("<Key>", app.on_key_press)
        tb.bind("<Control-Shift-C>", app.copy_screen_text)
        tb.bind("<Control-Shift-c>", app.copy_screen_text)
        tb.bind("<Control-d>", app.insert_today_date)
        tb.bind("<Control-D>", app.insert_today_date)
        tb._textbox.bind("<Control-d>", app.insert_today_date)
        tb._textbox.bind("<Control-D>", app.insert_today_date)
        tb.bind("<<Paste>>", app._on_paste_event)
        tb.bind("<<Cut>>", lambda event: "break")
        tb._textbox.bind("<<Paste>>", app._on_paste_event)
        tb._textbox.bind("<<Cut>>", lambda event: "break")

        tb._textbox.bind("<Button-1>", app._on_terminal_click, add="+")
        tb._textbox.tag_bind("underline", "<Enter>", lambda e: tb._textbox.configure(cursor="xterm"))
        tb._textbox.tag_bind("underline", "<Leave>", lambda e: tb._textbox.configure(cursor="arrow"))

        self.terminal_panel.bind("<Configure>", app._on_panel_resize)


class TerminalApp(ctk.CTk):
    # --- タブ委譲用プロパティ（既存メソッドを1行も変えずに完全互換動作させるアダプター） ---
    @property
    def active_tab(self):
        if not hasattr(self, "tabs") or not self.tabs:
            return None
        for tab in self.tabs:
            if tab.tab_id == self.active_tab_id:
                return tab
        return self.tabs[0] if self.tabs else None

    @property
    def session(self):
        tab = self.active_tab
        return tab.session if tab else None

    @session.setter
    def session(self, val):
        tab = self.active_tab
        if tab:
            tab.session = val

    @property
    def textbox(self):
        tab = self.active_tab
        return tab.textbox if tab else None

    @property
    def events(self):
        tab = self.active_tab
        return tab.events if tab else None

    @property
    def is_connected(self):
        tab = self.active_tab
        return tab.is_connected if tab else False

    @is_connected.setter
    def is_connected(self, val):
        tab = self.active_tab
        if tab:
            tab.is_connected = val

    @property
    def rendered_lines(self):
        tab = self.active_tab
        return tab.rendered_lines if tab else [None] * ROWS

    @rendered_lines.setter
    def rendered_lines(self, val):
        tab = self.active_tab
        if tab:
            tab.rendered_lines = val

    @property
    def raw_lines(self):
        tab = self.active_tab
        return tab.raw_lines if tab else {}

    @raw_lines.setter
    def raw_lines(self, val):
        tab = self.active_tab
        if tab:
            tab.raw_lines = val

    @property
    def font_size(self):
        tab = self.active_tab
        return tab.font_size if tab else 18

    @font_size.setter
    def font_size(self, val):
        tab = self.active_tab
        if tab:
            tab.font_size = val

    @property
    def active_cols(self):
        tab = self.active_tab
        return tab.active_cols if tab else 80

    @active_cols.setter
    def active_cols(self, val):
        tab = self.active_tab
        if tab:
            tab.active_cols = val

    @property
    def auto_fit(self):
        tab = self.active_tab
        return tab.auto_fit if tab else True

    @auto_fit.setter
    def auto_fit(self, val):
        tab = self.active_tab
        if tab:
            tab.auto_fit = val

    @property
    def terminal_font(self):
        tab = self.active_tab
        return tab.terminal_font if tab else None

    @property
    def terminal_panel(self):
        tab = self.active_tab
        return tab.terminal_panel if tab else getattr(self, "terminal_container", None)

    @property
    def _current_cursor(self):
        tab = self.active_tab
        return tab.current_cursor if tab else None

    @_current_cursor.setter
    def _current_cursor(self, val):
        tab = self.active_tab
        if tab:
            tab.current_cursor = val

    @property
    def _cursor_blink_visible(self):
        tab = self.active_tab
        return tab.cursor_blink_visible if tab else True

    @_cursor_blink_visible.setter
    def _cursor_blink_visible(self, val):
        tab = self.active_tab
        if tab:
            tab.cursor_blink_visible = val

    @property
    def _is_navigating_field(self):
        tab = self.active_tab
        return tab.is_navigating_field if tab else False

    @_is_navigating_field.setter
    def _is_navigating_field(self, val):
        tab = self.active_tab
        if tab:
            tab.is_navigating_field = val

    @property
    def _is_waiting_query(self):
        tab = self.active_tab
        return tab._is_waiting_query if tab else False

    @_is_waiting_query.setter
    def _is_waiting_query(self, val):
        tab = self.active_tab
        if tab:
            tab._is_waiting_query = val

    def __init__(self):
        self.config = load_config()
        self.theme_name = self.config.get("theme", "light")
        # 外枠UI（右カラム・メニューバー・ヘッダー・ボタン）は初期ライト配色で常に固定
        self.ui_colors = dict(COLOR_THEMES["light"])
        # ターミナル表示部分（画面内）のみ、選択テーマ・カスタム色を適用
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.ui_font_family = find_first_available_font(PREFERRED_UI_FONTS, fallback="Yu Gothic UI")
        self.terminal_font_family = find_first_available_font(PREFERRED_TERMINAL_FONTS, fallback="Consolas")

        self.title("QAD / MFG:PRO")
        self.geometry("1460x780")
        self.minsize(1020, 660)
        self.configure(fg_color=self.ui_colors["background"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # 最上部: Chrome風タブバー
        self.grid_rowconfigure(1, weight=1)  # ターミナル領域
        self.grid_rowconfigure(2, weight=0)  # ショートカットバー
        self.grid_rowconfigure(3, weight=0)  # データ送信バー
        self.grid_rowconfigure(4, weight=0)  # ステータスバー

        # マルチタブ管理用変数
        self.tabs = []
        self.active_tab_id = None
        self._next_tab_id = 1
        self.closing = False
        self._resize_job = None
        self.shortcut_buttons = []
        self._is_capturing_report = False
        self._is_capturing_winprint = False
        self._last_report_capture_time = 0.0
        self._is_gas_transmitting = False

        self._query_wait_start_time = 0.0
        self._current_status_type = "info"
        self._status_clear_timer = None

        # 入力受付カーソルの白点滅タイマー管理
        self._cursor_blink_job = None

        self.order_panel = None
        self.order_output = None
        self.last_order_submission = None
        self.order_panel_visible = tk.BooleanVar(self, value=False)
        self._order_control_tap = DoubleControlTap()
        self._order_bindtag = f"OrderEntryShortcut_{id(self)}"
        self.shortcut_assignments = self.config["shortcut_assignments"]
        self.shortcut_dialog = None
        self.shortcut_capture_entry = None
        self._shortcut_order_menu_index = None
        self.shortcut_menu = None
        self._order_original_width = None
        self._order_expanded_width = None

        self._build_menu()
        self._build_tab_bar()
        self._build_terminal_container()
        self._build_shortcut_bar()
        self._build_data_transmission_bar()
        self._build_statusbar()

        # タブ操作グローバルショートカット
        self.bind("<Control-t>", lambda e: self.create_new_tab())
        self.bind("<Control-T>", lambda e: self.create_new_tab())
        self.bind("<Control-w>", lambda e: self.close_tab(self.active_tab_id))
        self.bind("<Control-W>", lambda e: self.close_tab(self.active_tab_id))
        self.bind("<Control-Tab>", lambda e: self.cycle_tab(1))
        self.bind("<Control-Shift-Tab>", lambda e: self.cycle_tab(-1))
        self.bind("<Control-Prior>", lambda e: self.cycle_tab(-1))
        self.bind("<Control-Next>", lambda e: self.cycle_tab(1))

        # 初期タブを作成
        self.create_new_tab("Main", auto_connect=False)
        self._install_order_shortcut()

        self._set_state("未接続")
        self._show_message("")
        self._start_cursor_blink()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_job = self.after(33, self._poll)
        self.after(100, self._apply_auto_fit)
        # 起動時に自動接続を開始
        self.after(200, self.connect_to_server)

    def _get_terminal_colors(self):
        """現在のテーマおよびカスタム色を適用したターミナル表示用カラー辞書を取得"""
        theme_key = self.config.get("theme", "light")
        colors = dict(COLOR_THEMES.get(theme_key, COLOR_THEMES["light"]))
        if self.config.get("custom_terminal_bg"):
            colors["terminal"] = self.config["custom_terminal_bg"]
        if self.config.get("custom_terminal_fg"):
            colors["text"] = self.config["custom_terminal_fg"]
        return colors

    def _get_active_colors(self):
        return self._get_terminal_colors()

    def _button(self, parent, text, command, primary=False):
        return ActionButton(parent, text, command, primary, font_family=self.ui_font_family, colors=self.ui_colors)

    def _build_menu(self):
        menubar = tk.Menu(self)

        # 1. 接続メニュー
        self.connection_menu = tk.Menu(menubar, tearoff=False)
        self.connection_menu.add_command(label="ログイン / 接続", command=self.connect_to_server)
        self.connection_menu.add_command(label="切断", command=self.disconnect_server)
        self.connection_menu.add_separator()
        self.auto_main_menu_var = tk.BooleanVar(value=bool(self.config.get("auto_login_main_menu", True)))
        self.connection_menu.add_checkbutton(
            label="ログイン後に自動でMain Menuへ移動",
            variable=self.auto_main_menu_var,
            command=self.toggle_auto_login_main_menu,
        )
        self.connection_menu.add_separator()
        self.connection_menu.add_command(label="終了", command=self.on_close)
        menubar.add_cascade(label="接続", menu=self.connection_menu)

        # 2. 編集メニュー
        self.edit_menu = tk.Menu(menubar, tearoff=False)
        self.edit_menu.add_command(label="コピー (選択範囲または画面)", accelerator="Ctrl+C", command=self.copy_selection_or_screen)
        self.edit_menu.add_command(label="貼り付け", accelerator="Ctrl+V", command=self.paste_from_clipboard)
        self.edit_menu.add_command(label="すべて選択", accelerator="Ctrl+A", command=self.select_all_text)
        self.edit_menu.add_command(label="📅 今日の日付を入力 (mm/dd/yy)", accelerator="Ctrl+D", command=self.insert_today_date)
        self.edit_menu.add_separator()
        self.windows_shortcuts_var = tk.BooleanVar(value=bool(self.config.get("enable_windows_shortcuts", True)))
        self.edit_menu.add_checkbutton(
            label="Windows標準ショートカットを有効化 (Ctrl+C / Ctrl+V / Ctrl+A / Ctrl+D)",
            variable=self.windows_shortcuts_var,
            command=self.toggle_windows_shortcuts,
        )
        self.block_server_shortcuts_var = tk.BooleanVar(value=bool(self.config.get("block_server_shortcuts", True)))
        self.edit_menu.add_checkbutton(
            label="F1/F4以外のサーバー側ショートカットを無効化",
            variable=self.block_server_shortcuts_var,
            command=self.toggle_block_server_shortcuts,
        )
        self.auto_excel_var = tk.BooleanVar(value=bool(self.config.get("auto_excel_export", True)))
        self.edit_menu.add_checkbutton(
            label="レポート出力を自動でExcelに展開 (文字列書式)",
            variable=self.auto_excel_var,
            command=self.toggle_auto_excel_export,
        )
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="📊 画面のデータをExcelで開く (文字列書式)", accelerator="Ctrl+E", command=self.export_to_excel)
        self.edit_menu.add_command(label="🚀 レポート全ページ自動取得 ＆ Excelで開く", command=self._fetch_all_pages_and_open_excel)
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="📋 画面全体をコピー", accelerator="Ctrl+Shift+C", command=self.copy_screen_text)
        menubar.add_cascade(label="編集", menu=self.edit_menu)

        # 3. 表示メニュー
        view = tk.Menu(menubar, tearoff=False)
        view.add_command(label="文字を大きく", command=lambda: self.change_font_size(1))
        view.add_command(label="文字を小さく", command=lambda: self.change_font_size(-1))
        view.add_command(label="標準サイズ", command=lambda: self.change_font_size(reset=True))
        view.add_separator()
        view.add_command(label="📋 画面の文字をコピー", accelerator="Ctrl+Shift+C", command=self.copy_screen_text)
        view.add_separator()
        self.auto_fit_var = tk.BooleanVar(value=True)
        view.add_checkbutton(label="画面サイズに自動調整 (Auto Fit)", variable=self.auto_fit_var, command=self.toggle_auto_fit)
        view.add_separator()
        view.add_command(label="🏷️ タブ表示名（エイリアス）の設定...", command=self.open_tab_alias_dialog)
        view.add_command(label="📤 データ送信ボタン名の設定...", command=self.open_data_transmission_setting_dialog)
        view.add_separator()
        view.add_command(label="ターミナルにフォーカス", command=self.focus_terminal)
        view.add_separator()
        view.add_checkbutton(label="注文入力", accelerator="Ctrl × 2",
                             variable=self.order_panel_visible, command=self._sync_order_panel)
        order_csv_menu = tk.Menu(view, tearoff=False)
        order_csv_menu.add_command(label="顧客・納品先CSVを読み込む…",
                                   command=self.import_order_choices)
        view.add_cascade(label="注文入力の候補CSV", menu=order_csv_menu)
        menubar.add_cascade(label="表示", menu=view)

        self.shortcut_menu = tk.Menu(menubar, tearoff=False)
        self.shortcut_menu.add_command(label="ショートカット変更...", command=self.open_shortcut_settings)
        self.shortcut_menu.add_separator()
        self._shortcut_order_menu_index = self.shortcut_menu.index("end") + 1
        self.shortcut_menu.add_command(
            label="注文入力",
            accelerator=self.shortcut_assignments.get("order.panel.toggle", ""),
            command=self.toggle_order_panel,
        )
        menubar.add_cascade(label="ショートカット", menu=self.shortcut_menu)

        # 5. カラーパレットメニュー（独立メニュー）
        self.palette_menu = tk.Menu(menubar, tearoff=False)
        self.palette_menu.add_command(label="🎨 カラーパレットを開く...", command=self.open_color_palette)
        self.palette_menu.add_separator()
        self.palette_menu.add_command(label="ライト（標準グレー）", command=lambda: self.switch_theme("light"))
        self.palette_menu.add_command(label="ダークスレート", command=lambda: self.switch_theme("dark"))
        self.palette_menu.add_command(label="クラシックグリーン (VT100)", command=lambda: self.switch_theme("classic_green"))
        self.palette_menu.add_command(label="アンバー（琥珀色）", command=lambda: self.switch_theme("amber"))
        self.palette_menu.add_separator()
        self.palette_menu.add_command(label="配色を標準に戻す", command=self.reset_custom_colors)
        menubar.add_cascade(label="カラーパレット", menu=self.palette_menu)

        # 6. ログイン情報メニュー
        login_menu = tk.Menu(menubar, tearoff=False)
        login_menu.add_command(label="ログイン情報の編集...", command=self.open_login_dialog)
        menubar.add_cascade(label="ログイン情報", menu=login_menu)

        # 7. ヘルプメニュー
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="操作ガイド", command=self.show_help)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)

        self.configure(menu=menubar)

    def _build_tab_bar(self):
        """最上部にGoogle Chromeスタイルの角丸タブバーを構築（クイックメニュー等と同じ背景色）"""
        self.tab_bar = ctk.CTkFrame(
            self,
            fg_color=self.ui_colors["background"],
            height=36,
            corner_radius=0
        )
        self.tab_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.tab_bar.grid_columnconfigure(0, weight=1)
        self.tab_bar.grid_columnconfigure(1, weight=0)

        # タブボタンが並ぶ領域（height=36を明示固定して200px巨大化を完全防止）
        self.tabs_container = ctk.CTkFrame(self.tab_bar, fg_color="transparent", corner_radius=0, height=36)
        self.tabs_container.grid(row=0, column=0, sticky="sw", padx=0, pady=0)

        # 右端のクイック接続操作ツールバー（画面コピーとログイン情報は削除）
        self.right_tool_bar = ctk.CTkFrame(self.tab_bar, fg_color="transparent", corner_radius=0)
        self.right_tool_bar.grid(row=0, column=1, sticky="se", padx=(0, 4), pady=(0, 3))

        self.connect_btn = ctk.CTkButton(
            self.right_tool_bar,
            text="ログイン",
            width=58,
            height=24,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=11, weight="bold"),
            corner_radius=6,
            command=self.connect_to_server
        )
        self.connect_btn.pack(side="left", padx=(0, 4))

        self.disconnect_btn = ctk.CTkButton(
            self.right_tool_bar,
            text="切断",
            width=50,
            height=24,
            fg_color=self.ui_colors["button"],
            hover_color=self.ui_colors["hover"],
            text_color=self.ui_colors["muted"],
            font=ctk.CTkFont(family=self.ui_font_family, size=11),
            corner_radius=6,
            command=self.disconnect_server
        )
        self.disconnect_btn.pack(side="left", padx=(0, 2))

    def _build_terminal_container(self):
        """タブ直下のターミナル格納枠（全タブ共通親コンテナ）"""
        self.terminal_container = ctk.CTkFrame(
            self,
            fg_color=self.terminal_colors["terminal"],
            corner_radius=0
        )
        self.terminal_container.grid(row=1, column=0, padx=8, pady=(0, 4), sticky="nsew")
        self.terminal_container.grid_columnconfigure(0, weight=1)
        self.terminal_container.grid_rowconfigure(0, weight=1)

    def _install_order_shortcut(self):
        # A leading bindtag sees Ctrl before Text's existing "break" bindings.
        self.bind_class(self._order_bindtag, "<KeyPress>", self._on_order_key_press)
        self.bind_class(self._order_bindtag, "<KeyRelease>", self._on_order_key_release)
        self.bind_class(self._order_bindtag, "<FocusOut>", lambda event: self._order_control_tap.reset())
        self.bind_class(self._order_bindtag, "<ButtonPress>", lambda event: self._order_control_tap.reset())
        self.bind("<Map>", self._on_order_widget_map, add="+")
        self._attach_order_bindtag(self)

    def _attach_order_bindtag(self, widget):
        if not hasattr(widget, "winfo_toplevel"):
            return
        top = widget.winfo_toplevel()
        if top is not self and top is not self.shortcut_dialog:
            return
        tags = widget.bindtags()
        if self._order_bindtag not in tags:
            widget.bindtags((self._order_bindtag, *tags))
        for child in widget.winfo_children():
            self._attach_order_bindtag(child)

    def _on_order_widget_map(self, event):
        self._attach_order_bindtag(event.widget)

    def _on_order_key_press(self, event):
        if self.shortcut_capture_entry is not None:
            if event.widget is self.shortcut_capture_entry._entry:
                if event.keysym == "Escape" and not (event.state & (0x4 | 0x8)):
                    self.shortcut_dialog._select_action(self.shortcut_dialog.action_picker.get())
                    self.shortcut_capture_entry = None
                    return "break"
                if event.keysym not in DoubleControlTap.CONTROL_KEYS:
                    return self.shortcut_dialog.capture(event)
                self._order_control_tap.reset()
                return "break"
            if event.widget.winfo_toplevel() is self.shortcut_dialog:
                return None

        shortcut = shortcut_from_key_event(event)
        if shortcut is not None:
            action_id = next((key for key, value in self.shortcut_assignments.items()
                              if value == shortcut), None)
            if action_id:
                self._order_control_tap.reset()
                self._run_shortcut_action(action_id)
                return "break"
        self._order_control_tap.press(event.keysym, time.monotonic(), event.state)
        if event.keysym in DoubleControlTap.CONTROL_KEYS:
            return "break"

    def _on_order_key_release(self, event):
        if self._order_control_tap.release(event.keysym, time.monotonic()):
            self.toggle_order_panel()
        if event.keysym in DoubleControlTap.CONTROL_KEYS:
            return "break"

    def toggle_order_panel(self):
        self.order_panel_visible.set(not self.order_panel_visible.get())
        self._sync_order_panel()

    def _shortcut_actions(self):
        actions = {
            "order.panel.toggle": ("注文入力", self.toggle_order_panel),
            "order.panel.submit": ("注文入力を送信", self._shortcut_submit_order),
            "order.panel.close": ("注文入力を閉じる", self._shortcut_close_order),
            "order.csv.choices": ("顧客・納品先CSVを選択", self.import_order_choices),
            "order.date.required": ("Required dateを選択", lambda: self._shortcut_open_order_date("required_date")),
            "order.date.due": ("due dateを選択", lambda: self._shortcut_open_order_date("due_date")),
        }
        ordinal = {}

        def visit(parent, window_name):
            try:
                children = parent.winfo_children()
            except (tk.TclError, AttributeError):
                return
            for widget in children:
                try:
                    if isinstance(widget, ctk.CTkToplevel) and widget is self.shortcut_dialog:
                        continue
                    if isinstance(widget, ActionButton):
                        label = widget.cget("text")
                        action_id = f"button:{widget._w}"
                        if label and action_id not in actions:
                            key = (window_name, str(label).strip())
                            ordinal[key] = ordinal.get(key, 0) + 1
                            suffix = f" #{ordinal[key]}" if ordinal[key] > 1 else ""
                            actions[action_id] = (f"{window_name} › {str(label).strip()}{suffix}",
                                                  lambda target=widget: self._invoke_shortcut_button(target))
                        continue
                    if isinstance(widget, ctk.CTkButton) or isinstance(widget, tk.Button):
                        label = str(widget.cget("text")).strip()
                        action_id = f"button:{widget._w}"
                        if label and action_id not in actions:
                            key = (window_name, label)
                            ordinal[key] = ordinal.get(key, 0) + 1
                            suffix = f" #{ordinal[key]}" if ordinal[key] > 1 else ""
                            actions[action_id] = (f"{window_name} › {label}{suffix}",
                                                  lambda target=widget: self._invoke_shortcut_button(target))
                        continue
                    visit(widget, window_name)
                except (tk.TclError, AttributeError):
                    continue

        visit(self, self.title())
        if self.order_panel is not None:
            visit(self.order_panel, "注文入力")
        return actions

    def open_shortcut_settings(self):
        if self.shortcut_dialog is not None and self.shortcut_dialog.winfo_exists():
            self.shortcut_dialog.lift()
            return
        self.shortcut_dialog = ShortcutSettingsDialog(
            self, self._shortcut_actions(), dict(self.shortcut_assignments),
            self.ui_colors, self.ui_font_family,
            self._save_shortcut_assignment, self._set_shortcut_capture,
        )
        self._attach_order_bindtag(self.shortcut_dialog)
        self.shortcut_dialog.grab_set()

    def _set_shortcut_capture(self, entry):
        self.shortcut_capture_entry = entry
        if entry is not None:
            entry.focus_set()

    def _save_shortcut_assignment(self, action_id, shortcut):
        if action_id not in self._shortcut_actions():
            if self.shortcut_dialog:
                self.shortcut_dialog.error_label.configure(text="対象の操作を確認できません。")
            return False
        try:
            shortcut = normalize_shortcut(shortcut) if shortcut else ""
        except ValueError as exc:
            if self.shortcut_dialog:
                self.shortcut_dialog.error_label.configure(text=str(exc))
            return False
        if shortcut:
            conflict = next((key for key, value in self.shortcut_assignments.items()
                             if key != action_id and value == shortcut), None)
            if conflict:
                conflict_label = self._shortcut_actions().get(conflict, (conflict, None))[0]
                if self.shortcut_dialog:
                    self.shortcut_dialog.error_label.configure(
                        text=f"「{conflict_label}」に割り当て済みです。別のキーを選んでください。")
                return False
            self.shortcut_assignments[action_id] = shortcut
        else:
            self.shortcut_assignments.pop(action_id, None)
        self.config["shortcut_assignments"] = self.shortcut_assignments
        save_config(self.config)
        if self.shortcut_menu is not None and self._shortcut_order_menu_index is not None:
            self.shortcut_menu.entryconfigure(
                self._shortcut_order_menu_index,
                accelerator=self.shortcut_assignments.get("order.panel.toggle", ""),
            )
        return True

    def _run_shortcut_action(self, action_id):
        action = self._shortcut_actions().get(action_id)
        if action is None:
            self.shortcut_assignments.pop(action_id, None)
            self.config["shortcut_assignments"] = self.shortcut_assignments
            save_config(self.config)
            return
        action[1]()

    def _invoke_shortcut_button(self, button):
        try:
            if not button.winfo_exists() or button.cget("state") == "disabled":
                return
            button.invoke()
        except tk.TclError:
            return

    def _shortcut_submit_order(self):
        if not self.order_panel_visible.get() or self.order_panel is None:
            self.order_panel_visible.set(True)
            self._sync_order_panel()
            return
        self.order_panel.submit()

    def _shortcut_close_order(self):
        if self.order_panel_visible.get():
            self.toggle_order_panel()

    def _shortcut_open_order_date(self, field):
        if not self.order_panel_visible.get():
            self.order_panel_visible.set(True)
            self._sync_order_panel()
        self.order_panel.fields[field].open_calendar()

    def _sync_order_panel(self):
        if self.order_panel_visible.get():
            if self.order_panel is None:
                self.order_panel = OrderEntryPanel(
                    self, self.ui_colors, self.ui_font_family,
                    on_submit=self._process_order_submission, on_close=self.toggle_order_panel,
                )
                self._attach_order_bindtag(self.order_panel)
            path = self.config.get("order_choices_csv")
            if path:
                try:
                    self.order_panel.set_customer_ship_tos(read_customer_ship_to_csv(path))
                except (OSError, UnicodeError, ValueError, csv.Error) as exc:
                    self.set_status(f"注文候補CSVを読み込めません：{exc}", "error")
            self.order_panel.grid(row=0, column=1, rowspan=5, padx=(4, 8), pady=8, sticky="nsew")
            self.grid_columnconfigure(1, minsize=602)
            if self._order_original_width is None and self.state() == "normal":
                self._order_original_width = self.winfo_width()
                available = self.winfo_screenwidth() - max(0, self.winfo_x()) - 20
                width = max(self.winfo_width(), min(self.winfo_width() + 602, available))
                self._order_expanded_width = width
                self.geometry(f"{width}x{self.winfo_height()}")
            self.order_panel.focus_first()
        else:
            if self.order_panel is not None:
                self.order_panel.close_popups()
                self.order_panel.grid_remove()
            self.grid_columnconfigure(1, minsize=0)
            if (self._order_original_width is not None and self.state() == "normal"
                    and self.winfo_width() == self._order_expanded_width):
                self.geometry(f"{self._order_original_width}x{self.winfo_height()}")
            self._order_original_width = self._order_expanded_width = None
            self.focus_terminal()

    def import_order_choices(self):
        path = filedialog.askopenfilename(parent=self, title="顧客・納品先CSVを読み込む",
                                          filetypes=[("CSV", "*.csv"), ("すべてのファイル", "*.*")])
        if not path:
            return
        try:
            choices = read_customer_ship_to_csv(path)
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            messagebox.showerror("CSV読み込みエラー", str(exc), parent=self)
            return
        self.config["order_choices_csv"] = path
        save_config(self.config)
        if self.order_panel is not None:
            self.order_panel.set_customer_ship_tos(choices)
        pair_count = sum(len(destinations) for destinations in choices.values())
        self.set_status(f"顧客{len(choices)}件・納品先{pair_count}件を読み込みました。",
                        "info", clear_delay=4)

    def _process_order_submission(self, payload):
        """今後の所定ロジック接続箇所。現在は注文内容をローカル画面に出力。"""
        self.last_order_submission = payload
        if self.order_output is not None and self.order_output.winfo_exists():
            self.order_output.destroy()
        self.order_output = show_order_output(self, payload, self.ui_colors, self.ui_font_family)
        self.set_status("注文内容を画面に出力しました。", "info", clear_delay=4)

    def _route_order_edit(self, virtual_event):
        """The Edit menu operates on the order field that currently has focus."""
        if self.order_panel is None or not self.order_panel_visible.get():
            return False
        focused = self.focus_get()
        ancestor = focused
        while ancestor is not None:
            if ancestor is self.order_panel:
                if isinstance(focused, (tk.Entry, tk.Text)):
                    focused.event_generate(virtual_event)
                return True
            ancestor = getattr(ancestor, "master", None)
        return False

    def _get_chrome_tab_image(self, width: int, height: int, is_active: bool, is_first: bool = False):
        """Pillow 4倍スーパーサンプリングによる最高品位の滑らかなChromeタブ背景を生成（キャッシュ付き）"""
        if not hasattr(self, "_tab_image_cache"):
            self._tab_image_cache = {}

        term_bg = self.terminal_colors.get("terminal", "#1E293B")
        bar_bg = self.ui_colors.get("background", "#F1F5F9")
        inactive_bg = "#94A3B8"

        cache_key = (width, height, is_active, is_first, term_bg, bar_bg, inactive_bg)
        if cache_key in self._tab_image_cache:
            return self._tab_image_cache[cache_key]

        scale = 4
        W = width * scale
        H = height * scale
        # 引き締まったスタイリッシュなフィレット半径（6px相当）
        R = 6 * scale

        if is_active:
            im = Image.new("RGBA", (W, H), bar_bg)
            draw = ImageDraw.Draw(im)

            if is_first:
                # ========================================================
                # 一番左のアクティブタブ: 左端は垂直に画面左端と直結！
                # ========================================================
                draw.rectangle([0, H - R, W, H], fill=term_bg)
                draw.ellipse([0, 0, 2 * R, 2 * R], fill=term_bg)
                draw.ellipse([W - 3 * R, 0, W - R, 2 * R], fill=term_bg)
                draw.rectangle([R, 0, W - 2 * R, 2 * R], fill=term_bg)
                draw.rectangle([0, R, W - R, H], fill=term_bg)
                draw.ellipse([W - R, H - 2 * R, W + R, H], fill=bar_bg)
            else:
                # ========================================================
                # 2番目以降のアクティブタブ: 左右両方に引き締まった逆アールフィレット
                # ========================================================
                draw.rectangle([0, H - R, W, H], fill=term_bg)
                draw.ellipse([R, 0, 3 * R, 2 * R], fill=term_bg)
                draw.ellipse([W - 3 * R, 0, W - R, 2 * R], fill=term_bg)
                draw.rectangle([2 * R, 0, W - 2 * R, 2 * R], fill=term_bg)
                draw.rectangle([R, R, W - R, H], fill=term_bg)
                draw.ellipse([-R, H - 2 * R, R, H], fill=bar_bg)
                draw.ellipse([W - R, H - 2 * R, W + R, H], fill=bar_bg)
        else:
            r = 6 * scale
            im = Image.new("RGBA", (W, H), bar_bg)
            draw = ImageDraw.Draw(im)
            draw.rounded_rectangle([0, 0, W, H], radius=r, fill=inactive_bg)

        smooth_im = im.resize((width, height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(smooth_im)
        self._tab_image_cache[cache_key] = photo
        return photo

    def _render_tab_buttons(self):
        """Google Chromeスタイルの角丸・幅広タブボタンを再描画（オーバーラップ配置で隙間完全ゼロ化）"""
        for w in self.tabs_container.winfo_children():
            w.destroy()

        active_tab = self.active_tab
        term_bg = self.terminal_colors.get("terminal", "#1E293B")
        bar_bg = self.ui_colors.get("background", "#F1F5F9")
        inactive_bg = "#94A3B8"

        cur_x = 0
        overlap = 6
        canvases = []

        for i, tab in enumerate(self.tabs):
            is_active = (tab == active_tab)
            is_first = (i == 0)
            tid = tab.tab_id
            title_text = tab.title
            if len(title_text) > 20:
                title_text = title_text[:18] + "…"

            if is_active:
                H = 34
                W = max(150, len(title_text) * 9 + 54)
                y_pos = 2
            else:
                H = 28
                W = max(136, len(title_text) * 9 + 46)
                y_pos = 5

            if i > 0:
                prev_is_active = (self.tabs[i - 1] == active_tab)
                if is_active or prev_is_active:
                    cur_x -= overlap
                else:
                    cur_x += 1

            photo = self._get_chrome_tab_image(W, H, is_active=is_active, is_first=is_first)

            canvas = tk.Canvas(
                self.tabs_container,
                width=W,
                height=H,
                bg=bar_bg,
                highlightthickness=0,
                cursor="hand2"
            )
            canvas.place(x=cur_x, y=y_pos)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.image = photo

            if is_active:
                text_x = 16 if is_first else 20
                txt_color = self.terminal_colors.get("text", "#FFFFFF")
                canvas.create_text(
                    text_x,
                    H // 2,
                    text=title_text,
                    fill=txt_color,
                    font=ctk.CTkFont(family=self.ui_font_family, size=11, weight="bold"),
                    anchor="w"
                )

                btn_x = W - 18
                btn_y = H // 2
                btn_r = 9
                hover_circle = canvas.create_oval(
                    btn_x - btn_r, btn_y - btn_r, btn_x + btn_r, btn_y + btn_r,
                    fill=term_bg, outline=term_bg, tags=f"close_{tid}"
                )
                close_txt = canvas.create_text(
                    btn_x, btn_y, text="✕", fill="#94A3B8", font=("Arial", 9, "bold"), tags=f"close_{tid}"
                )

                canvas.tag_bind(f"close_{tid}", "<Enter>", lambda e, c=canvas, hc=hover_circle, ct=close_txt: (c.itemconfig(hc, fill="#EF4444", outline="#EF4444"), c.itemconfig(ct, fill="#FFFFFF")))
                canvas.tag_bind(f"close_{tid}", "<Leave>", lambda e, c=canvas, hc=hover_circle, ct=close_txt, bg=term_bg: (c.itemconfig(hc, fill=bg, outline=bg), c.itemconfig(ct, fill="#94A3B8")))
                canvas.tag_bind(f"close_{tid}", "<Button-1>", lambda e, target_id=tid: (self.close_tab(target_id), "break"))

                def _on_active_click(event, target_id=tid, bx=btn_x, by=btn_y, br=btn_r):
                    if (event.x - bx) ** 2 + (event.y - by) ** 2 <= (br + 2) ** 2:
                        return
                    self.switch_tab(target_id)

                canvas.bind("<Button-1>", _on_active_click)

            else:
                canvas.create_text(
                    14,
                    H // 2,
                    text=title_text,
                    fill="#0F172A",
                    font=ctk.CTkFont(family=self.ui_font_family, size=11, weight="bold"),
                    anchor="w"
                )

                btn_x = W - 16
                btn_y = H // 2
                btn_r = 8
                hover_circle = canvas.create_oval(
                    btn_x - btn_r, btn_y - btn_r, btn_x + btn_r, btn_y + btn_r,
                    fill=inactive_bg, outline=inactive_bg, tags=f"close_{tid}"
                )
                close_txt = canvas.create_text(
                    btn_x, btn_y, text="✕", fill="#1E293B", font=("Arial", 9, "bold"), tags=f"close_{tid}"
                )

                canvas.tag_bind(f"close_{tid}", "<Enter>", lambda e, c=canvas, hc=hover_circle, ct=close_txt: (c.itemconfig(hc, fill="#EF4444", outline="#EF4444"), c.itemconfig(ct, fill="#FFFFFF")))
                canvas.tag_bind(f"close_{tid}", "<Leave>", lambda e, c=canvas, hc=hover_circle, ct=close_txt, bg=inactive_bg: (c.itemconfig(hc, fill=bg, outline=bg), c.itemconfig(ct, fill="#1E293B")))
                canvas.tag_bind(f"close_{tid}", "<Button-1>", lambda e, target_id=tid: (self.close_tab(target_id), "break"))

                def _on_inact_click(event, target_id=tid, bx=btn_x, by=btn_y, br=btn_r):
                    if (event.x - bx) ** 2 + (event.y - by) ** 2 <= (br + 2) ** 2:
                        return
                    self.switch_tab(target_id)

                canvas.bind("<Button-1>", _on_inact_click)

            canvases.append((canvas, is_active))
            cur_x += W

        # アクティブタブを前面に引き上げ（自然なオーバーラップ）
        for c, is_active in canvases:
            if is_active:
                tk.Misc.lift(c)

        # 新規タブ「＋」ボタン（最後のタブに寄り添うように配置）
        plus_btn = ctk.CTkButton(
            self.tabs_container,
            text="+",
            width=24,
            height=24,
            corner_radius=12,
            fg_color="transparent",
            hover_color=self.ui_colors.get("button", "#E2E8F0"),
            text_color="#475569",
            font=("Arial", 14, "bold"),
            command=lambda: self.create_new_tab()
        )
        plus_btn.place(x=cur_x + 4, y=6)

        # tabs_container の幅と高さを明示調整（height=36を固定して200px巨大化を完全防止）
        self.tabs_container.configure(width=cur_x + 36, height=36)

    def create_new_tab(self, title=None, auto_connect=True):
        """新しいタブを作成し、アクティブにする（デフォルトタイトルはMain）"""
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        if not title:
            title = "Main"

        tab = TerminalTab(self, tab_id, title)
        self.tabs.append(tab)
        self.switch_tab(tab_id)

        if auto_connect:
            self.connect_tab(tab)

        return tab

    def switch_tab(self, tab_id: int):
        """アクティブタブを切り替える"""
        target_tab = None
        for t in self.tabs:
            if t.tab_id == tab_id:
                target_tab = t
                break
        if not target_tab:
            return

        self.active_tab_id = tab_id

        # ターミナルパネルの表示・非表示切り替え
        for tab in self.tabs:
            if tab.tab_id == tab_id:
                tab.terminal_panel.grid(row=0, column=0, sticky="nsew")
            else:
                tab.terminal_panel.grid_remove()

        # タブボタンの再描画
        self._render_tab_buttons()

        # 画面状態・ボタン状態の復元
        self._set_state("接続済み" if target_tab.is_connected else "未接続", "success" if target_tab.is_connected else "muted")
        self._update_status_info()
        self.focus_terminal()

        # 切り替え時に即座に差分を強制描画
        if target_tab.is_connected and target_tab.session:
            target_tab.raw_lines.clear()
            self._update_tab_screen(target_tab, force=True)

    def close_tab(self, tab_id: int):
        """指定したIDのタブを安全に閉じる"""
        if len(self.tabs) <= 1:
            self._show_input_error("最後のタブは閉じられません")
            return

        target_idx = None
        for i, tab in enumerate(self.tabs):
            if tab.tab_id == tab_id:
                target_idx = i
                break

        if target_idx is None:
            return

        target_tab = self.tabs[target_idx]

        # SSHセッションを安全に切断
        if target_tab.session:
            try:
                target_tab.closing = True
                target_tab.session.stop()
            except Exception as e:
                log_error(f"タブ切断エラー: {e}")

        # UI要素の破棄
        try:
            target_tab.terminal_panel.destroy()
        except Exception:
            pass

        self.tabs.pop(target_idx)

        # アクティブタブだった場合は直前のタブに切り替え
        if self.active_tab_id == tab_id:
            new_idx = max(0, target_idx - 1)
            self.switch_tab(self.tabs[new_idx].tab_id)
        else:
            self._render_tab_buttons()

    def cycle_tab(self, direction=1):
        """Ctrl+Tab 等で次のタブまたは前のタブに巡回切り替え"""
        if len(self.tabs) <= 1:
            return
        cur_idx = 0
        for i, tab in enumerate(self.tabs):
            if tab.tab_id == self.active_tab_id:
                cur_idx = i
                break
        next_idx = (cur_idx + direction) % len(self.tabs)
        self.switch_tab(self.tabs[next_idx].tab_id)

    def open_tab_alias_dialog(self):
        """タブ表示名（エイリアス）の設定ダイアログを開く"""
        TabAliasDialog(self, self.config, self._on_tab_alias_saved)

    def _on_tab_alias_saved(self):
        """エイリアス設定保存時のコールバック（全タブのタイトルを再評価）"""
        for tab in self.tabs:
            self._detect_tab_title(tab)
        self._render_tab_buttons()

    def _detect_tab_title(self, tab: TerminalTab):
        """画面の内容からQADメニュー番号を検知してタブ名を更新（Main または メニュー番号/エイリアス名）"""
        if not tab or not tab.is_connected:
            return

        lines = []
        if tab.raw_lines:
            lines = [tab.raw_lines[r][0] for r in sorted(tab.raw_lines.keys()) if tab.raw_lines.get(r)]
        if not lines:
            return

        first_few = " ".join(lines[:4])
        aliases = self.config.get("tab_aliases", {})

        new_title = None
        if "mfmenu" in first_few.lower() and "main menu" in first_few.lower():
            new_title = aliases.get("main", aliases.get("mfmenu", "Main"))
        else:
            m = re.search(r'\b(\d{1,2}\.\d{1,2}(?:\.\d{1,2})*(?:\.\d{1,2})*)\b', first_few)
            if m:
                code = m.group(1)
                new_title = aliases.get(code, code)

        if new_title and tab.title != new_title:
            tab.title = new_title
            self._render_tab_buttons()

    def connect_tab(self, tab: TerminalTab):
        """指定されたタブでSSH接続を開始"""
        if tab is None or tab.session is not None or tab.closing:
            return

        host = self.config.get("host", "mfg03")
        port = int(self.config.get("port", 22))
        user = self.config.get("user", "takehik")
        pwd = ""
        b64 = self.config.get("pass_b64", "")
        if b64:
            try:
                pwd = base64.b64decode(b64.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                pass

        tab.session = TerminalSession(host, port, user, pwd, tab.events)
        if tab == self.active_tab:
            self._set_state("接続中…", "warning")
            self._show_tab_message(tab, "")
            self._show_input_error("")
        tab.session.start()

    def _auto_navigate_to_main_menu_for_tab(self, tab: TerminalTab):
        """指定タブに対して自動ログイン（2 -> 1 -> Enter x 2 -> Space）を実行"""
        log_info(f"自動ログイン: Tab {tab.tab_id} のMain Menu自動遷移シーケンスを開始")
        try:
            time.sleep(1.0)
            if not tab.is_connected or tab.session is None:
                return

            tab.session.send("2\r")
            time.sleep(1.0)
            if not tab.is_connected or tab.session is None:
                return

            tab.session.send("1\r")
            time.sleep(1.0)
            if not tab.is_connected or tab.session is None:
                return

            tab.session.send("\r\r")
            time.sleep(0.8)

            start_time = time.time()
            while time.time() - start_time < 15.0:
                if not tab.is_connected or tab.session is None:
                    return

                lines = [tab.raw_lines[r][0] for r in sorted(tab.raw_lines.keys()) if tab.raw_lines.get(r)]
                full_text = "\n".join(lines).lower()
                if "mfmenu" in full_text and "main menu" in full_text:
                    log_info(f"自動ログイン: Tab {tab.tab_id} Main Menu 着弾検知")
                    break

                if any(k in full_text for k in ["space", "press spacebar", "continue", "program information"]):
                    tab.session.send(" ")
                    time.sleep(0.6)
                    continue

                time.sleep(0.8)
                if not ("mfmenu" in full_text and "main menu" in full_text):
                    tab.session.send(" ")

            if tab == self.active_tab:
                self.after(0, lambda: self.set_status("● 接続済み (Main Menu)", "success", clear_delay=4))
        except Exception as e:
            log_error(f"Tab {tab.tab_id} 自動ログインエラー: {e}")

    def _apply_text_tags_to_widget(self, tb):
        """指定テキストボックスのタグ設定（反転・下線・太字等）を現在のターミナルカラーで適用"""
        if not tb:
            return
        tb.tag_config("reverse", background=self.terminal_colors["reverse_bg"], foreground=self.terminal_colors["reverse_fg"])
        tb.tag_config("menu_highlight", background=self.terminal_colors["menu_highlight_bg"], foreground=self.terminal_colors["menu_highlight_fg"])

        underline_color = self.terminal_colors.get("underline_fg", "#2563EB")
        try:
            tb._textbox.tag_config(
                "underline",
                underline=True,
                underlinefg=underline_color,
            )
        except Exception:
            tb.tag_config("underline", underline=True, foreground=underline_color)

        try:
            tb._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
        except Exception:
            tb.tag_config("bold", foreground=self.terminal_colors["accent"])

        try:
            tb._textbox.tag_raise("reverse", "underline")
            tb._textbox.tag_raise("menu_highlight")
            tb._textbox.tag_raise("remote_cursor")
            tb._textbox.tag_raise("sel")
        except Exception:
            pass

    def _apply_text_tags(self):
        """アクティブなテキストボックスにタグ設定を適用"""
        self._update_cursor_tag_style()
        if self.textbox:
            self._apply_text_tags_to_widget(self.textbox)

    def _build_shortcut_bar(self):
        """最下段のショートカット（直接移動）バーを構築"""
        self.shortcut_bar = ctk.CTkFrame(
            self, height=44, fg_color=self.ui_colors["panel"],
            corner_radius=10, border_width=1, border_color=self.ui_colors["border"]
        )
        self.shortcut_bar.grid(row=2, column=0, padx=8, pady=(0, 6), sticky="ew")
        self.shortcut_bar.grid_columnconfigure(1, weight=1)

        # 左端ラベル
        lbl = ctk.CTkLabel(
            self.shortcut_bar, text="📌 クイックメニュー:",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            text_color=self.ui_colors["muted"]
        )
        lbl.grid(row=0, column=0, padx=(12, 6), pady=4)

        # スクロール対応ボタン配置領域（多数登録時も横スクロールで綺麗に収まる）
        self.shortcut_scroll_frame = ctk.CTkScrollableFrame(
            self.shortcut_bar, orientation="horizontal", height=32,
            fg_color="transparent"
        )
        self.shortcut_scroll_frame.grid(row=0, column=1, sticky="ew", padx=4, pady=2)

        # 「🏠 HOME画面に戻る」ボタン（ワンクリックでQADメインメニューへ安全復帰）
        self.home_btn = ctk.CTkButton(
            self.shortcut_bar, text="🏠 HOME画面に戻る", width=130, height=28,
            fg_color="#D97706", hover_color="#B45309", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.go_home_screen
        )
        self.home_btn.grid(row=0, column=2, padx=(4, 4), pady=4)

        # 右側「🖨️ 32printer」ボタン（ワンクリックでOutput欄に32prnを入力）
        self.winprint_btn = ctk.CTkButton(
            self.shortcut_bar, text="🖨️ 32printer", width=96, height=28,
            fg_color="#1E7E34", hover_color="#155724", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.input_32printer
        )
        self.winprint_btn.grid(row=0, column=3, padx=(4, 4), pady=4)

        # 右端「＋ 追加」ボタン
        self.add_shortcut_btn = ctk.CTkButton(
            self.shortcut_bar, text="＋ 追加", width=72, height=28,
            fg_color="#356BC4", hover_color="#285BAF", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.open_add_shortcut_dialog
        )
        self.add_shortcut_btn.grid(row=0, column=4, padx=(4, 10), pady=4)

        self._refresh_shortcut_buttons()

    def _build_data_transmission_bar(self):
        """クイックメニュー直下のデータ送信（GAS転送）バーを構築"""
        self.data_transmission_bar = ctk.CTkFrame(
            self, height=44, fg_color=self.ui_colors["panel"],
            corner_radius=10, border_width=1, border_color=self.ui_colors["border"]
        )
        self.data_transmission_bar.grid(row=3, column=0, padx=8, pady=(0, 6), sticky="ew")
        self.data_transmission_bar.grid_columnconfigure(1, weight=1)

        # 左端ラベル
        lbl = ctk.CTkLabel(
            self.data_transmission_bar, text="📤 データ送信:",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            text_color=self.ui_colors["muted"]
        )
        lbl.grid(row=0, column=0, padx=(12, 6), pady=4)

        # ボタン配置フレーム
        btn_frame = ctk.CTkFrame(self.data_transmission_bar, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="w", padx=4, pady=2)

        # 設定からカスタムボタン名を取得
        dt_names = self.config.get("data_transmission_names", {})
        inv_text = dt_names.get("inventory", DEFAULT_DATA_TRANSMISSION_NAMES["inventory"])
        com_text = dt_names.get("complaint", DEFAULT_DATA_TRANSMISSION_NAMES["complaint"])
        par_text = dt_names.get("parallel", DEFAULT_DATA_TRANSMISSION_NAMES["parallel"])

        # ボタン1: 📦 在庫レポートGAS送信 (99.3.6.1)
        self.inventory_gas_btn = ctk.CTkButton(
            btn_frame, text=inv_text, height=28,
            fg_color="#059669", hover_color="#047857", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.run_inventory_gas_transmission
        )
        self.inventory_gas_btn.pack(side="left", padx=4, pady=2)
        self.inventory_gas_btn.bind("<Button-3>", lambda e: self._show_data_trans_context_menu(e, "inventory"))

        # ボタン2: 📑 Complaint送信 (99.3.21.4)
        self.complaint_gas_btn = ctk.CTkButton(
            btn_frame, text=com_text, height=28,
            fg_color="#4F46E5", hover_color="#4338CA", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.open_complaint_dialog
        )
        self.complaint_gas_btn.pack(side="left", padx=4, pady=2)
        self.complaint_gas_btn.bind("<Button-3>", lambda e: self._show_data_trans_context_menu(e, "complaint"))

        # ボタン3: ⚡ 受注残＆売上 並行送信 (99.7.6.20 & 99.7.5.11)
        self.parallel_gas_btn = ctk.CTkButton(
            btn_frame, text=par_text, height=28,
            fg_color="#D97706", hover_color="#B45309", text_color="#FFFFFF",
            font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold"),
            corner_radius=6, command=self.run_parallel_gas_transmission
        )
        self.parallel_gas_btn.pack(side="left", padx=4, pady=2)
        self.parallel_gas_btn.bind("<Button-3>", lambda e: self._show_data_trans_context_menu(e, "parallel"))

    def _show_data_trans_context_menu(self, event, key: str):
        """データ送信ボタンの右クリックコンテキストメニュー"""
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="ボタン名を変更...", command=lambda: self.open_data_transmission_setting_dialog(key))
        menu.add_command(label="初期の名前に戻す", command=lambda: self._reset_single_data_transmission_name(key))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def open_data_transmission_setting_dialog(self, focus_key: str = "inventory"):
        """データ送信ボタン名設定ダイアログを開く"""
        DataTransmissionSettingDialog(self, focus_key=focus_key, on_save_callback=self._on_data_transmission_names_saved)

    def _on_data_transmission_names_saved(self, new_names: dict):
        """データ送信ボタン名が保存されたときの処理"""
        self.config["data_transmission_names"] = new_names
        save_config(self.config)
        self._refresh_data_transmission_button_texts()
        self._show_input_error("データ送信ボタン名を更新しました")

    def _reset_single_data_transmission_name(self, key: str):
        """単一のデータ送信ボタン名を初期値に戻す"""
        if "data_transmission_names" not in self.config:
            self.config["data_transmission_names"] = {}
        default_val = DEFAULT_DATA_TRANSMISSION_NAMES.get(key, "")
        self.config["data_transmission_names"][key] = default_val
        save_config(self.config)
        self._refresh_data_transmission_button_texts()
        self._show_input_error(f"ボタン名を初期名（{default_val}）に戻しました")

    def _refresh_data_transmission_button_texts(self):
        """データ送信ボタンのテキストを最新設定に更新"""
        dt_names = self.config.get("data_transmission_names", {})
        if hasattr(self, "inventory_gas_btn"):
            self.inventory_gas_btn.configure(text=dt_names.get("inventory", DEFAULT_DATA_TRANSMISSION_NAMES["inventory"]))
        if hasattr(self, "complaint_gas_btn"):
            self.complaint_gas_btn.configure(text=dt_names.get("complaint", DEFAULT_DATA_TRANSMISSION_NAMES["complaint"]))
        if hasattr(self, "parallel_gas_btn"):
            self.parallel_gas_btn.configure(text=dt_names.get("parallel", DEFAULT_DATA_TRANSMISSION_NAMES["parallel"]))

    def _update_data_transmission_buttons_state(self):
        """データ送信ボタンの有効/無効状態を更新"""
        state = "disabled" if self._is_gas_transmitting else "normal"
        if hasattr(self, "inventory_gas_btn"):
            self.inventory_gas_btn.configure(state=state)
        if hasattr(self, "complaint_gas_btn"):
            self.complaint_gas_btn.configure(state=state)
        if hasattr(self, "parallel_gas_btn"):
            self.parallel_gas_btn.configure(state=state)

    def _build_statusbar(self):
        """最下段の常時表示ステータスバーを構築（処理中の進捗・クエリ待機・Excel展開を可視化）"""
        self.statusbar = ctk.CTkFrame(
            self, height=28, fg_color=self.ui_colors["panel"],
            corner_radius=6, border_width=1, border_color=self.ui_colors["border"]
        )
        self.statusbar.grid(row=4, column=0, padx=8, pady=(0, 6), sticky="ew")
        self.statusbar.grid_columnconfigure(0, weight=1)

        self.bottom_status_label = ctk.CTkLabel(
            self.statusbar, text="● 未接続",
            text_color=self.ui_colors["muted"],
            font=ctk.CTkFont(family=self.ui_font_family, size=12),
            anchor="w"
        )
        self.bottom_status_label.grid(row=0, column=0, padx=12, pady=2, sticky="w")

        self.statusbar_info_label = ctk.CTkLabel(
            self.statusbar, text="",
            text_color=self.ui_colors["muted"],
            font=ctk.CTkFont(family=self.ui_font_family, size=11),
            anchor="e"
        )
        self.statusbar_info_label.grid(row=0, column=1, padx=12, pady=2, sticky="e")
        self._update_status_info()

    def _update_status_info(self):
        """ステータスバー右側の端末情報（文字コード、列数、Excel自動展開設定）を更新"""
        if not hasattr(self, "statusbar_info_label"):
            return
        auto_excel = "ON" if self.config.get("auto_excel_export", True) else "OFF"
        cols = getattr(self, "active_cols", 80)
        self.statusbar_info_label.configure(
            text=f"CP932 | {cols}x24 | レポート自動Excel: {auto_excel}"
        )

    def _refresh_shortcut_buttons(self):
        """登録されたショートカットボタン一覧を再描画"""
        for w in self.shortcut_scroll_frame.winfo_children():
            w.destroy()
        self.shortcut_buttons = []

        shortcuts = self.config.get("shortcuts", [])
        state = "normal" if self.is_connected else "disabled"
        for idx, sc in enumerate(shortcuts):
            name = sc.get("name", "")
            code = sc.get("code", "")
            is_order_booking = (str(code).strip() == "99.7.6.20" or "orderbooking" in name.lower() or "order booking" in name.lower())
            btn_text = f"⚡ {name} ({code})" if is_order_booking else f"{name} ({code})"
            btn_fg = "#2563EB" if is_order_booking else self.ui_colors["button"]
            btn_hover = "#1D4ED8" if is_order_booking else self.ui_colors["hover"]
            btn_text_color = "#FFFFFF" if is_order_booking else self.ui_colors["text"]
            btn = ctk.CTkButton(
                self.shortcut_scroll_frame, text=btn_text, height=28,
                fg_color=btn_fg, hover_color=btn_hover,
                text_color=btn_text_color,
                font=ctk.CTkFont(family=self.ui_font_family, size=12, weight="bold" if is_order_booking else "normal"),
                corner_radius=6, state=state,
                command=lambda n=name, c=code: self._handle_shortcut_click(n, c)
            )
            btn.pack(side="left", padx=4, pady=2)
            # 右クリックで編集・削除メニュー表示
            btn.bind("<Button-3>", lambda event, i=idx, n=name, c=code: self._show_shortcut_context_menu(event, i, n, c))
            self.shortcut_buttons.append(btn)

    def _handle_shortcut_click(self, name, code):
        """ショートカットボタン押下時のハンドラ（専用自動化マクロがある場合はそれを実行）"""
        name_lower = str(name).strip().lower()
        code_str = str(code).strip()
        if code_str == "99.7.6.20" or "orderbooking" in name_lower or "order booking" in name_lower:
            self.run_order_booking_automation()
        else:
            self.jump_to_menu(code_str)

    def _show_shortcut_context_menu(self, event, idx, name, code):
        """ショートカットボタンの右クリックコンテキストメニュー（編集のみ）"""
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="編集", command=lambda: self.open_edit_shortcut_dialog(idx))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def open_edit_shortcut_dialog(self, idx):
        """ショートカット再編集ダイアログを開く"""
        shortcuts = self.config.get("shortcuts", [])
        if 0 <= idx < len(shortcuts):
            sc = shortcuts[idx]
            name = sc.get("name", "")
            code = sc.get("code", "")
            ShortcutDialog(
                self,
                on_save_callback=lambda new_name, new_code: self._on_shortcut_updated(idx, new_name, new_code),
                initial_name=name,
                initial_code=code,
                is_edit=True,
                on_delete_callback=lambda: self._delete_shortcut(idx)
            )

    def _on_shortcut_updated(self, idx, name, code):
        """ショートカット更新コールバック"""
        shortcuts = self.config.get("shortcuts", [])
        if 0 <= idx < len(shortcuts):
            shortcuts[idx] = {"name": name, "code": code}
            self.config["shortcuts"] = shortcuts
            save_config(self.config)
            self._refresh_shortcut_buttons()
            self._show_input_error(f"ショートカット「{name} ({code})」を更新しました")

    def _delete_shortcut(self, idx):
        """ショートカットを削除"""
        shortcuts = self.config.get("shortcuts", [])
        if 0 <= idx < len(shortcuts):
            deleted = shortcuts.pop(idx)
            self.config["shortcuts"] = shortcuts
            save_config(self.config)
            self._refresh_shortcut_buttons()
            self._show_input_error(f"ショートカット「{deleted['name']}」を削除しました")

    def open_add_shortcut_dialog(self):
        """「＋」追加ダイアログを開く"""
        ShortcutDialog(self, self._on_shortcut_added, is_edit=False)

    def _on_shortcut_added(self, name, code):
        """ショートカット追加コールバック"""
        shortcuts = self.config.get("shortcuts", [])
        shortcuts.append({"name": name, "code": code})
        self.config["shortcuts"] = shortcuts
        save_config(self.config)
        self._refresh_shortcut_buttons()
        self._show_input_error(f"ショートカット「{name} ({code})」を追加しました")

    def is_main_menu(self):
        """現在の画面がQADメインメニュー（mfmenu / Main Menu）かどうかを判定（右肩日付は変数として無視）"""
        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                content = self.textbox.get("1.0", "end")
                lines = content.splitlines()
            except Exception:
                lines = []

        full_text = "\n".join(lines)
        if not full_text.strip():
            return False

        full_lower = full_text.lower()

        # 1. 2行目ヘッダーの「mfmenu」と「Main Menu」の完全合致（右肩日付は変数として無視）
        # 例: │mfmenu                             Main Menu                          09/18/26│
        for line in lines[:5]:
            l_lower = line.lower()
            if "mfmenu" in l_lower and "main menu" in l_lower:
                return True

        # 2. プロンプト判定: "F4 or blank to EXIT"（メインメニュー特有の終了メッセージ）
        if "f4 or blank to exit" in full_lower:
            return True

        # 3. 単独の mfmenu コマンド名判定
        if re.search(r'\bmfmenu\b', full_lower):
            return True

        return False

    def is_menu_screen(self):
        """現在の画面がメインメニューまたはサブメニュー選択画面かどうかを判定"""
        if self.is_main_menu():
            return True

        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                content = self.textbox.get("1.0", "end")
                lines = content.splitlines()
            except Exception:
                lines = []

        full_text = "\n".join(lines)
        if not full_text.strip():
            return False

        menu_prompts = [
            "Please select a function",
            "select a function",
            "Selection:",
            "選択:",
            "選んでください",
            "メニュー選択",
            "Go to:",
        ]
        full_lower = full_text.lower()
        for p in menu_prompts:
            if p.lower() in full_lower:
                return True

        menu_item_matches = re.findall(r'(?<!\d)\b\d{1,2}\.\s+[^\s│]{2,}', full_text)
        if len(menu_item_matches) >= 3:
            return True

        return False

    def go_home_screen(self):
        """HOME画面（QADメインメニュー）に戻る"""
        if not self.is_connected or not self.session:
            self._show_input_error("サーバーに接続されていません")
            return

        if self.is_main_menu():
            self.set_status("🏠 既にHOME画面（メインメニュー）です", "info", clear_delay=3)
            self.focus_terminal()
            return

        self.set_status("🏠 HOME画面に戻っています...", "working")

        def _do_home():
            try:
                import time
                if getattr(self, "_is_waiting_query", False):
                    self._is_waiting_query = False

                # メインメニューに戻るまで最大3回試行（通常は業務画面から1回のF4で戻る）
                for step in range(3):
                    if self.is_main_menu():
                        break

                    log_info(f"HOME画面復帰: F4 を送信します (step {step + 1})")
                    self.session.send(KEY_SEQUENCES["F4"])

                    # サーバーからの画面反映を十分に待機（最大1.20秒）
                    # ※ 待機時間が短すぎると、画面が更新される前に2回目のF4が誤送信されてしまうのを完全に防止
                    start_wait = time.time()
                    while time.time() - start_wait < 1.20:
                        time.sleep(0.05)
                        if self.is_main_menu():
                            break

                    # メインメニューに着弾したことを検知したら直ちに終了（余計なF4は絶対に送らない）
                    if self.is_main_menu():
                        log_info("HOME画面復帰: メインメニュー着弾を確認しました")
                        break

                    time.sleep(0.2)

                if self.is_main_menu():
                    self.after(0, lambda: self.set_status("🏠 HOME画面（メインメニュー）に戻りました", "success", clear_delay=3))
                else:
                    self.after(0, lambda: self.set_status("● 接続済み (Ready)", "info"))
            except Exception as e:
                log_error(f"HOME画面復帰エラー: {e}")
                self.after(0, lambda: self.set_status("❌ HOME画面への復帰でエラーが発生しました", "error", clear_delay=4))
            finally:
                self.after(50, self.focus_terminal)

        import threading
        threading.Thread(target=_do_home, daemon=True, name="go-home").start()

    def run_order_booking_automation(self):
        """OrderBooking (99.7.6.20) の一括自動実行マクロ
        改行（改セル）を含む一括貼り付け方式により、フィールド位置ズレなく確実に設定・実行します。

        シーケンス:
        1. HOME画面（メインメニュー）に戻る
        2. 99.7.6.20 の画面に移動する（Sales Order From にカーソルが初期配置されるのを待機）
        3. 一括入力バッチ（改行を含む複数行文字列）を送信:
           - Sales Order (From/To) x 2スキップ (\r\r)
           - Order Date (From/To) x 2スキップ (\r\r)
           - Item Number (From/To) x 2スキップ (\r\r)
           - Prod Line (From) に "1fgi" 入力 (\r)
           - Prod Line (To) に "1fgi" 入力 (\r)
           - Site (From/To) x 2スキップ (\r\r)
           - Sold-To (From/To) x 2スキップ (\r\r)
           - Channel (From/To) x 2スキップ (\r\r)
           - Customer PO Number (From/To) x 2スキップ (\r\r)
           - Due Date (From) に本日の日付 (MM/dd/yy) を入力
        4. F1 を押して Output 欄にジャンプ
        5. winPrint を入力して実行、サーバー監視＆重複行除外＆Excel自動展開
        """
        if not self.is_connected or not self.session:
            self._show_input_error("サーバーに接続されていません")
            return

        if getattr(self, "_is_capturing_winprint", False) or getattr(self, "_is_waiting_query", False):
            self._show_input_error("現在別のレポート処理が実行中です。完了までお待ちください。")
            return

        log_info("=== OrderBooking 自動実行マクロ開始（改セル一括貼り付け方式） ===")
        self.set_status("🚀 OrderBooking 自動実行を開始します...", "working")

        def _worker():
            try:
                # -------------------------------------------------------------
                # Step 1: HOME画面（メインメニュー）に戻る
                # -------------------------------------------------------------
                self.set_status("🏠 Step 1/5: HOME画面（メインメニュー）へ復帰中...", "working")
                if not self.is_main_menu():
                    for step in range(4):
                        if self.is_main_menu():
                            break
                        log_info(f"OrderBooking: HOME画面復帰のため F4 送信 (step {step + 1})")
                        self.session.send(KEY_SEQUENCES["F4"])
                        start_wait = time.time()
                        while time.time() - start_wait < 1.20:
                            time.sleep(0.05)
                            if self.is_main_menu():
                                break
                        time.sleep(0.15)

                if self.is_main_menu():
                    log_info("OrderBooking: メインメニュー復帰完了")
                else:
                    log_warning("OrderBooking: メインメニューへの復帰確認が取れませんでしたが、続行を試みます")

                time.sleep(0.3)

                # -------------------------------------------------------------
                # Step 2: 99.7.6.20 の画面に移動する
                # -------------------------------------------------------------
                self.set_status("📋 Step 2/5: 99.7.6.20 画面へ移動中...", "working")
                log_info("OrderBooking: '99.7.6.20\\r' を送信します")
                self.session.send("99.7.6.20\r")

                # 画面が 99.7.6.20 の条件入力画面（Sales Order Detail Report）に遷移するのを待機
                start_nav = time.time()
                nav_ok = False
                while time.time() - start_nav < 4.0:
                    time.sleep(0.1)
                    txt = self._get_current_screen_text().lower()
                    if "99.7.6.20" in txt or "sales order detail report" in txt or "sales order:" in txt:
                        nav_ok = True
                        break

                if nav_ok:
                    log_info("OrderBooking: 99.7.6.20 条件入力画面の表示を確認しました")
                else:
                    log_warning("OrderBooking: 画面判定タイムアウト。入力処理を試行します")

                # カーソルが最初の入力欄（Sales Order From）に安定着弾するまで待機
                time.sleep(0.5)

                # -------------------------------------------------------------
                # Step 3: 改行（改セル）を含む複数行一括入力
                # -------------------------------------------------------------
                self.set_status("✏️ Step 3/5: Prod Line('1fgi') & Due Date(今日) を一括入力中...", "working")
                today_str = datetime.date.today().strftime("%m/%d/%y")
                log_info(f"OrderBooking: 本日の日付 = '{today_str}'")

                # 1. Sales Order (From/To) ~ Item Number (From/To) をスキップ (計6回 Enter)
                # 2. Prod Line (From) に "1fgi"、Prod Line (To) に "1fgi"
                # 3. Site (From/To) ~ Customer PO Number (From/To) をスキップ (計8回 Enter)
                # 4. Due Date (From) に今日の日付 (MM/dd/yy) を入力

                # ブロック1: Prod Line までのスキップと Prod Line 入力
                part1 = "\r" * 6 + "1fgi\r" + "1fgi\r"
                log_info("OrderBooking: Part 1 (Sales Order ~ Prod Line) 送信")
                self.session.send(part1)
                time.sleep(0.2)

                # ブロック2: Site ~ Customer PO Number のスキップと Due Date 入力
                part2 = "\r" * 8 + today_str
                log_info(f"OrderBooking: Part 2 (Site ~ Due Date: {today_str}) 送信")
                self.session.send(part2)
                time.sleep(0.35)

                # -------------------------------------------------------------
                # Step 4: F1 を押して Output の入力欄に移動する
                # -------------------------------------------------------------
                self.set_status("⚡ Step 4/5: F1 を押して Output 欄へジャンプ中...", "working")
                log_info("OrderBooking: F1 を送信して Output 欄へジャンプ")
                self.session.send(KEY_SEQUENCES["F1"])

                # Output 欄に着弾するのを待機（最大2.5秒）
                start_out_wait = time.time()
                while time.time() - start_out_wait < 2.5:
                    time.sleep(0.1)
                    if self._is_cursor_at_output_field():
                        log_info("OrderBooking: Output 欄への着弾を確認しました")
                        break
                time.sleep(0.35)

                # -------------------------------------------------------------
                # Step 5: 32prn を指定して Excel 出力する
                # -------------------------------------------------------------
                self.set_status("🖨️ Step 5/5: Output に '32prn' を設定し、ストリーム受信・Excel展開を開始...", "working")
                log_info("OrderBooking: input_32printer を起動して自動実行・ストリーム直接受信・Excel展開を開始")
                self.after(0, self.input_32printer)

            except Exception as e:
                log_error(f"OrderBooking 自動実行エラー: {e}", exc_info=True)
                self.set_status(f"❌ OrderBooking 自動実行エラー: {e}", "error", clear_delay=6)

        import threading
        threading.Thread(target=_worker, daemon=True, name="order-booking-macro").start()

    # =========================================================================
    # --- GASデータ送信機能 (在庫レポート 99.3.6.1 & Complaint 99.3.21.4) ---
    # =========================================================================

    def _get_qad_credentials(self):
        """QAD接続に必要な (host, port, user, pwd) を取得する"""
        host = self.config.get("host", "mfg03")
        port = int(self.config.get("port", 22))
        user = self.config.get("user", "")
        pwd = ""
        b64 = self.config.get("pass_b64", "")
        if b64:
            try:
                pwd = base64.b64decode(b64.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                pass

        # 設定値が不完全な場合は config.ini (Documents\QAD_Tools\config.ini) をフォールバック確認
        if not user or not pwd:
            if os.path.exists(CONFIG_INI_PATH):
                try:
                    ini_config = configparser.ConfigParser()
                    ini_config.read(CONFIG_INI_PATH, encoding='utf-8')
                    if 'server' in ini_config:
                        sec = ini_config['server']
                        user = user or sec.get('user', '')
                        pwd = pwd or sec.get('password', '')
                        host = sec.get('host', host)
                        port = int(sec.get('port', str(port)))
                except Exception as _ini_e:
                    log_warning(f"config.ini 読み込み警告: {_ini_e}")

        return host, port, user, pwd

    def run_inventory_gas_transmission(self):
        """在庫レポート (99.3.6.1 - 1FGI) を抽出して GAS へ自動転送"""
        if self._is_gas_transmitting:
            messagebox.showwarning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。", parent=self)
            return

        host, port, user, pwd = self._get_qad_credentials()
        if not user or not pwd:
            messagebox.showerror(
                "ログイン情報未設定",
                "QADのログイン情報が設定されていません。\nメニューの「ログイン情報」からユーザーIDとパスワードを設定してください。",
                parent=self
            )
            return

        self._is_gas_transmitting = True
        self._update_data_transmission_buttons_state()
        self.set_status("🚀 在庫レポート抽出＆GAS送信を開始します...", "working")
        log_info(f"在庫レポートGAS送信開始: ユーザー={user}, ホスト={host}")

        def _thread_target():
            self._run_inventory_gas_transmission_worker(host, port, user, pwd)

        threading.Thread(target=_thread_target, daemon=True, name="inventory-gas-worker").start()

    def _run_inventory_gas_transmission_worker(self, host, port, user, pwd):
        """在庫レポート抽出＆GAS送信のバックグラウンドワーカー (32prn 高速ストリーム版)"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.set_status("🔌 [1/5] QADサーバーに接続中...", "working")
            ssh.connect(host, port=port, username=user, password=pwd, timeout=15)

            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(30)

            shell = ssh.invoke_shell(term='vt100', width=256, height=60)
            shell.settimeout(10.0)

            self.set_status("📋 [2/5] QADメニュー(99.3.6.1)へ移動中...", "working")
            time.sleep(2)
            _clear_shell_buffer(shell)

            shell.send("2\r")
            _wait_shell_text(shell, "Selection:", timeout=10)
            _clear_shell_buffer(shell)

            shell.send("1\r")
            login_start = time.time()
            while time.time() - login_start < 15:
                if shell.recv_ready():
                    peek = shell.recv(4096)
                    if b"Press space bar" in peek or b"Pausing" in peek:
                        shell.send(" ")
                    if b"Please select a function" in peek:
                        break
                time.sleep(0.1)

            _clear_shell_buffer(shell)
            shell.send("99.3.6.1\r")
            time.sleep(1.5)
            _clear_shell_buffer(shell)

            self.set_status("⚡ [3/5] 条件 '1fgi' を一括貼り付け入力中...", "working")
            # 改行（改セル）を含む一括貼り付け方式により、高速かつ確実に条件入力
            batch_input = "\r" * 8 + "1fgi\r" + "1fgi\r"
            shell.send(batch_input)
            time.sleep(0.3)
            _clear_shell_buffer(shell)

            # F1キー(1回目): Output欄へジャンプ
            shell.send("\x1bOP")
            time.sleep(0.8)
            _clear_shell_buffer(shell)

            # Output欄に 32prn を入力
            shell.send("32prn\r")
            time.sleep(0.5)

            # F1キー(2回目): 抽出実行
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x06")

            self.set_status("⏳ [4/5] 32prn 圧縮ストリームを受信中...", "working")

            query_start = time.time()
            stream_buffer = bytearray()
            capturing = False
            finished = False
            MAX_WAIT = 300  # 最大5分待機

            while time.time() - query_start < MAX_WAIT:
                if shell.recv_ready():
                    chunk = shell.recv(65535)
                    if chunk:
                        stream_buffer.extend(chunk)

                        if b"begin 0 32PRINTER" in stream_buffer and not capturing:
                            capturing = True
                            self.set_status("📥 [4/5] 圧縮データを受信中...", "working")

                        if capturing:
                            if re.search(rb'\nend(\r|\n|\x1b)', stream_buffer) or b"\x1b[4i" in stream_buffer:
                                finished = True
                                break

                time.sleep(0.05)
                elapsed = int(time.time() - query_start)
                if elapsed % 4 == 0 and elapsed > 0 and not capturing:
                    self.set_status(f"⏳ [4/5] サーバーでクエリ実行中... ({elapsed}秒経過)", "working")

            if not finished:
                raise TimeoutError("32prn ストリームの受信がタイムアウトしました。")

            elapsed_sec = time.time() - query_start
            self.set_status(f"📥 [5/5] 高速インメモリ解凍中 ({len(stream_buffer)/1024:.0f} KB / {elapsed_sec:.1f}秒)...", "working")

            raw_text = decode_32prn_stream(stream_buffer)
            final_text = clean_printer_data(raw_text)
            rows = parse_report_to_rows(final_text)

            row_count = len(rows) - 1
            if row_count <= 0:
                raise ValueError("抽出結果が0件でした。条件に一致するデータが存在しないか、レポート解析に失敗しました。")

            self.set_status(f"🚀 ブラウザを起動しGASへ送信中 ({row_count:,}件)...", "working")
            send_to_gas_via_browser(rows, INVENTORY_GAS_URL, title="Google Sheets 自動転送 (在庫レポート 1FGI)")

            self.after(0, lambda: self._on_inventory_gas_success(row_count))

        except Exception as exc:
            log_error(f"在庫レポートGAS送信エラー: {exc}", exc_info=True)
            err_msg = str(exc)
            self.after(0, lambda: self._on_inventory_gas_error(err_msg))
        finally:
            self._is_gas_transmitting = False
            try:
                ssh.close()
            except Exception:
                pass
            self.after(0, self._update_data_transmission_buttons_state)

    def _on_inventory_gas_success(self, row_count: int):
        self.set_status(f"✅ 在庫レポートをGASへ転送完了 ({row_count:,}件)", "success", clear_delay=8)
        log_info(f"在庫レポートGAS送信完了: {row_count:,}件")

    def _on_inventory_gas_error(self, err_msg: str):
        self.set_status(f"❌ 在庫レポートGAS送信エラー: {err_msg}", "error", clear_delay=10)
        messagebox.showerror("エラー", f"在庫レポートの処理中にエラーが発生しました:\n\n{err_msg}", parent=self)

    def open_complaint_dialog(self):
        """Complaint送信の条件入力ダイアログを開く"""
        if self._is_gas_transmitting:
            messagebox.showwarning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。", parent=self)
            return
        ComplaintDialog(self)

    def run_complaint_gas_transmission(self, item_num: str, start_day: str, end_day: str, item_lot: str, dialog_ref=None):
        """Complaint (99.3.21.4) を抽出して GAS へ自動転送"""
        host, port, user, pwd = self._get_qad_credentials()
        if not user or not pwd:
            if dialog_ref:
                dialog_ref.submit_btn.configure(state="normal")
                dialog_ref.cancel_btn.configure(state="normal")
                dialog_ref.update_dialog_status("❌ ログイン情報が未設定です", color="#DC2626")
            messagebox.showerror(
                "ログイン情報未設定",
                "QADのログイン情報が設定されていません。\nメニューの「ログイン情報」からユーザーIDとパスワードを設定してください。",
                parent=dialog_ref or self
            )
            return

        self._is_gas_transmitting = True
        self._update_data_transmission_buttons_state()
        self.set_status(f"🚀 Complaint 抽出＆GAS送信を開始します (Item: {item_num})...", "working")
        log_info(f"Complaint送信開始: item={item_num}, start={start_day}, end={end_day}, lot={item_lot}")

        def _thread_target():
            self._run_complaint_gas_transmission_worker(host, port, user, pwd, item_num, start_day, end_day, item_lot, dialog_ref)

        threading.Thread(target=_thread_target, daemon=True, name="complaint-gas-worker").start()

    def _run_complaint_gas_transmission_worker(self, host, port, user, pwd, item_num, start_day, end_day, item_lot, dialog_ref):
        """Complaint抽出＆GAS送信のバックグラウンドワーカー"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        def _update_ui_status(msg):
            self.set_status(msg, "working")
            if dialog_ref:
                dialog_ref.update_dialog_status(msg, color="#D97706")

        try:
            _update_ui_status("🔌 [1/6] サーバーに接続中...")
            ssh.connect(host, port=port, username=user, password=pwd, timeout=15)

            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(30)

            shell = ssh.invoke_shell(term='vt100', width=132, height=24)
            shell.settimeout(10.0)

            _update_ui_status("📋 [2/6] QADメニューを移動中...")
            time.sleep(2)
            _clear_shell_buffer(shell)

            shell.send("2\r")
            _wait_shell_text(shell, "Roll Japan Production", timeout=12)
            _clear_shell_buffer(shell)

            shell.send("1\r")
            try:
                _wait_shell_text(shell, "space bar to continue", timeout=8)
                shell.send(" ")
            except Exception:
                pass

            _wait_shell_text(shell, "Please select a function", timeout=15)
            _clear_shell_buffer(shell)

            shell.send("99.3.21.4\r")
            _wait_shell_text(shell, "Item Number", timeout=15)
            _clear_shell_buffer(shell)

            _update_ui_status("⚡ [3/6] 条件を一括貼り付け入力中...")
            # 改行（改セル）を含む一括貼り付け方式により、高速かつ確実に条件入力
            lot_part = f"{item_lot}\r{item_lot}\r" if item_lot else "\r\r"
            batch_input = (
                f"{item_num}\r{item_num}\r"     # 1-2: Item Number (From/To)
                "\r\r"                           # 3-4: Site (From/To) スキップ
                f"{start_day}\r{end_day}\r"     # 5-6: Effective Date (From/To)
                "1fgi\r1fgi\r"                   # 7-8: Prod Line (From/To)
                "\r\r\r\r"                       # 9-12: Order/Customer スキップ
                f"{lot_part}"                    # 13-14: Lot (From/To)
                + ("\r" * 11)                    # 15-25: Output欄までの11フィールドスキップ
            )
            shell.send(batch_input)
            time.sleep(0.3)
            _clear_shell_buffer(shell)

            # Output 欄に 32prn (高速gzipストリーム) を入力
            shell.send("32prn\r")
            time.sleep(0.5)

            _update_ui_status("🚀 [4/6] レポート実行開始...")
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x06")

            # --- 32prn 圧縮ストリーム直接受信 ---
            _update_ui_status("⏳ [4/6] 32prn 圧縮ストリームを受信中...")
            query_start = time.time()
            stream_buffer = bytearray()
            capturing = False
            finished = False
            MAX_WAIT = 300  # 最大5分待機

            while time.time() - query_start < MAX_WAIT:
                if shell.recv_ready():
                    chunk = shell.recv(65535)
                    if chunk:
                        stream_buffer.extend(chunk)

                        if b"begin 0 32PRINTER" in stream_buffer and not capturing:
                            capturing = True
                            _update_ui_status("📥 [4/6] 圧縮データを受信中...")

                        if capturing:
                            if re.search(rb'\nend(\r|\n|\x1b)', stream_buffer) or b"\x1b[4i" in stream_buffer:
                                finished = True
                                break

                time.sleep(0.05)
                elapsed = int(time.time() - query_start)
                if elapsed % 4 == 0 and elapsed > 0 and not capturing:
                    _update_ui_status(f"⏳ [4/6] サーバーでクエリ実行中... ({elapsed}秒経過)")

            if not finished:
                raise TimeoutError("32prn ストリームの受信がタイムアウトしました。")

            elapsed_sec = time.time() - query_start
            _update_ui_status(f"📥 [5/6] データ解析中 ({len(stream_buffer)/1024:.0f} KB / {elapsed_sec:.1f}秒)...")

            raw_text = decode_32prn_stream(stream_buffer)
            final_text = clean_printer_data(raw_text)
            data_list = parse_report_to_rows(final_text)

            if len(data_list) <= 1:
                raise ValueError("処理は完了しましたが、指定された条件に一致するデータがありませんでした。")

            row_count = len(data_list) - 1
            _update_ui_status(f"📤 [6/6] GASへ {row_count:,}件 を送信中...")
            send_to_gas_via_browser(data_list, COMPLAINT_GAS_URL, title="Google Sheets 自動転送 (Complaint)")

            self.after(0, lambda: self._on_complaint_gas_success(row_count, dialog_ref))

        except Exception as exc:
            log_error(f"Complaint送信エラー: {exc}", exc_info=True)
            err_msg = str(exc)
            self.after(0, lambda: self._on_complaint_gas_error(err_msg, dialog_ref))
        finally:
            self._is_gas_transmitting = False
            try:
                ssh.close()
            except Exception:
                pass
            self.after(0, self._update_data_transmission_buttons_state)

    def _on_complaint_gas_success(self, row_count: int, dialog_ref=None):
        self.set_status(f"✅ ComplaintデータをGASへ転送完了 ({row_count:,}件)", "success", clear_delay=8)
        log_info(f"ComplaintデータGAS送信完了: {row_count:,}件")
        if dialog_ref:
            dialog_ref.destroy()

    def _on_complaint_gas_error(self, err_msg: str, dialog_ref=None):
        self.set_status(f"❌ Complaint送信エラー: {err_msg}", "error", clear_delay=10)
        if dialog_ref:
            dialog_ref.submit_btn.configure(state="normal")
            dialog_ref.cancel_btn.configure(state="normal")
            dialog_ref.update_dialog_status("❌ エラーが発生しました", color="#DC2626")
        messagebox.showerror("エラー", f"Complaint送信の処理中にエラーが発生しました:\n\n{err_msg}", parent=dialog_ref or self)

    # =========================================================================
    # --- 32prn 並行データ送信機能 (99.7.6.20 受注残 & 99.7.5.11 売上) ---
    # =========================================================================

    def run_parallel_gas_transmission(self):
        """99.7.6.20 (受注残) と 99.7.5.11 (売上データ) を完全独立セッションで並行抽出し、
        早く出来上がった順に即時 GAS へブラウザ経由で doPost 転送する。
        （確認ポップアップ・完了ポップアップは一切表示せず、ステータスバーとログで通知）
        """
        if self._is_gas_transmitting:
            self.set_status("⚠️ 現在別のデータ送信処理が実行中です", "error", clear_delay=5)
            return

        host, port, user, pwd = self._get_qad_credentials()
        if not user or not pwd:
            self._show_input_error("QADのログイン情報が設定されていません。\nメニューの「ログイン情報」から設定してください。")
            return

        self._is_gas_transmitting = True
        self._update_data_transmission_buttons_state()
        self.set_status("🚀 [並行送信] 受注残(99.7.6.20)＆売上(99.7.5.11)の32prn並行抽出を開始します...", "working")
        log_info(f"並行GAS送信開始 (99.7.6.20 & 99.7.5.11): ユーザー={user}, ホスト={host}")

        def _thread_target():
            self._run_parallel_gas_worker(host, port, user, pwd)

        threading.Thread(target=_thread_target, daemon=True, name="parallel-gas-worker").start()

    def _run_parallel_gas_worker(self, host, port, user, pwd):
        """2メニュー連続自動抽出＆即時GAS送信ワーカー
        QADサーバー（Progress 4GL）の32prnスプール競合や同一ユーザーセッション衝突を物理的に防ぐため、
        受注残(99.7.6.20)と売上(99.7.5.11)を順番に直列実行し、それぞれ抽出完了と同時にGASへ即時転送します。
        """
        results = {}
        overall_start = time.time()

        tasks = [
            ("99.7.6.20", self._parallel_extract_99_7_6_20),
            ("99.7.5.11", self._parallel_extract_99_7_5_11),
        ]

        for menu_name, worker_fn in tasks:
            try:
                res = worker_fn(host, port, user, pwd)
                results[menu_name] = res
                self.after(0, lambda m=menu_name, r=res: self._on_parallel_subtask_success(m, r))
            except Exception as err:
                log_error(f"データ送信 [{menu_name}] エラー: {err}", exc_info=True)
                results[menu_name] = {"error": str(err)}
                self.after(0, lambda m=menu_name, e=str(err): self._on_parallel_subtask_error(m, e))

        total_elapsed = time.time() - overall_start
        self._is_gas_transmitting = False
        self.after(0, self._update_data_transmission_buttons_state)
        self.after(0, lambda: self._on_parallel_all_done(results, total_elapsed))

    def _parallel_extract_99_7_6_20(self, host, port, user, pwd) -> dict:
        """99.7.6.20 (OrderBooking / 受注残) を 32prn で高速抽出し、即座に GAS へ POST"""
        start_t = time.time()
        log_info("並行ワーカー [99.7.6.20 受注残]: 接続中...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(host, port=port, username=user, password=pwd, timeout=15)
            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(30)

            shell = ssh.invoke_shell(term='vt100', width=256, height=60)
            shell.settimeout(10.0)

            time.sleep(2)
            _clear_shell_buffer(shell)

            # メニュー移動: 2 -> 1 -> space -> 99.7.6.20
            shell.send("2\r")
            _wait_shell_text(shell, "Selection:", timeout=10)
            _clear_shell_buffer(shell)

            shell.send("1\r")
            login_start = time.time()
            while time.time() - login_start < 15:
                if shell.recv_ready():
                    peek = shell.recv(4096)
                    if b"Press space bar" in peek or b"Pausing" in peek:
                        shell.send(" ")
                    if b"Please select a function" in peek:
                        break
                time.sleep(0.1)

            _clear_shell_buffer(shell)
            time.sleep(0.5)
            shell.send("99.7.6.20\r")
            if not _wait_shell_text(shell, "Sales Order", timeout=15):
                raise TimeoutError("99.7.6.20 画面への遷移に失敗しました。")
            time.sleep(0.8)
            _clear_shell_buffer(shell)

            # 条件入力: Sales Order~Item Number スキップ(6回 Enter)
            for _ in range(6):
                shell.send("\r")
                time.sleep(0.15)

            # Prod Line (From/To) に 1fgi
            shell.send("1fgi\r")
            time.sleep(0.2)
            shell.send("1fgi\r")
            time.sleep(0.2)

            # Site~Customer PO スキップ(8回 Enter)
            for _ in range(8):
                shell.send("\r")
                time.sleep(0.15)

            # Due Date (From) = 本日日付 (MM/dd/yy)
            today_str = datetime.date.today().strftime("%m/%d/%y")
            shell.send(today_str + "\r")
            time.sleep(0.3)

            # Output欄へ移動: F1 (\x1bOP)
            shell.send("\x1bOP")
            time.sleep(1.0)
            _clear_shell_buffer(shell)

            # Output欄に 32prn を入力
            shell.send("32prn\r")
            time.sleep(0.5)

            # 実行直前のバッファ完全フラッシュ（エコーバック破棄）
            _clear_shell_buffer(shell)

            # 実行: F1 -> F1 -> Ctrl+F (\x06)
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x06")

            # 32prn ストリーム直接受信
            query_start = time.time()
            stream_buffer = bytearray()
            capturing = False
            finished = False
            MAX_WAIT = 300

            while time.time() - query_start < MAX_WAIT:
                if shell.recv_ready():
                    chunk = shell.recv(65535)
                    if chunk:
                        stream_buffer.extend(chunk)
                        if b"begin 0 32PRINTER" in stream_buffer and not capturing:
                            capturing = True
                        if capturing:
                            if re.search(rb'\nend(\r|\n|\x1b)', stream_buffer) or b"\x1b[4i" in stream_buffer:
                                finished = True
                                break
                time.sleep(0.05)

            if not finished:
                raise TimeoutError("99.7.6.20: 32prn ストリーム受信がタイムアウトしました。")

            raw_text = decode_32prn_stream(stream_buffer)
            cleaned_text = clean_printer_data(raw_text)
            rows = parse_report_to_rows(cleaned_text)

            row_count = len(rows) - 1
            if row_count <= 0:
                raise ValueError("99.7.6.20: 抽出結果が0件でした。")

            elapsed = time.time() - start_t
            log_info(f"並行ワーカー [99.7.6.20 受注残]: 抽出完了 {row_count:,}件 ({elapsed:.1f}秒) ➔ 即時GAS送信")

            payload = {
                "menu": "99.7.6.20",
                "title": "OrderBooking",
                "sender": user,
                "exportedAt": datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                "data": rows
            }
            send_to_gas_via_browser(payload, PARALLEL_GAS_URL, title="Google Sheets 転送 (99.7.6.20 OrderBooking)")
            return {"count": row_count, "elapsed": elapsed}

        finally:
            ssh.close()

    def _parallel_extract_99_7_5_11(self, host, port, user, pwd) -> dict:
        """99.7.5.11 (Sales Data / 売上データ) を 32prn で高速抽出し、即座に GAS へ POST"""
        start_t = time.time()
        today = datetime.date.today()
        start_day = today.replace(day=1).strftime("%m/%d/%y")
        end_day = today.strftime("%m/%d/%y")

        log_info(f"並行ワーカー [99.7.5.11 売上]: 接続中 (対象期間: {start_day} ～ {end_day})...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(host, port=port, username=user, password=pwd, timeout=15)
            transport = ssh.get_transport()
            if transport:
                transport.set_keepalive(30)

            shell = ssh.invoke_shell(term='vt100', width=256, height=60)
            shell.settimeout(10.0)

            time.sleep(2)
            _clear_shell_buffer(shell)

            # メニュー移動: 2 -> 1 -> space -> 99.7.5.11
            shell.send("2\r")
            _wait_shell_text(shell, "Selection:", timeout=10)
            _clear_shell_buffer(shell)

            shell.send("1\r")
            login_start = time.time()
            while time.time() - login_start < 15:
                if shell.recv_ready():
                    peek = shell.recv(4096)
                    if b"Press space bar" in peek or b"Pausing" in peek:
                        shell.send(" ")
                    if b"Please select a function" in peek:
                        break
                time.sleep(0.1)

            _clear_shell_buffer(shell)
            time.sleep(0.5)
            shell.send("99.7.5.11\r")
            if not _wait_shell_text(shell, "Invoice", timeout=15):
                raise TimeoutError("99.7.5.11 画面への遷移に失敗しました。")
            time.sleep(0.8)
            _clear_shell_buffer(shell)

            # 条件入力: Invoice(2) + Sales Order(2) = 計4回 Enter
            for _ in range(4):
                shell.send("\r")
                time.sleep(0.15)

            # Effective From/To
            shell.send(start_day + "\r")
            time.sleep(0.2)
            shell.send(end_day + "\r")
            time.sleep(0.2)

            # Customer(2) + Bill-To(2) + Salespsn(2) + Item(2) + Group(2) = 計10回 Enter
            for _ in range(10):
                shell.send("\r")
                time.sleep(0.15)

            # Prod Line (From/To) に 1FGI
            shell.send("1FGI\r")
            time.sleep(0.2)
            shell.send("1FGI\r")
            time.sleep(0.2)

            # Site(2) + Include Sample(1) = 計3回 Enter で Output 欄へ
            for _ in range(3):
                shell.send("\r")
                time.sleep(0.15)
            _clear_shell_buffer(shell)

            # Output欄に 32prn を入力
            shell.send("32prn\r")
            time.sleep(0.5)

            # 実行直前のバッファ完全フラッシュ（エコーバック破棄）
            _clear_shell_buffer(shell)

            # 実行: F1 -> Ctrl+F (\x06)
            shell.send("\x1bOP")
            time.sleep(0.5)
            shell.send("\x06")

            # 32prn ストリーム直接受信
            query_start = time.time()
            stream_buffer = bytearray()
            capturing = False
            finished = False
            MAX_WAIT = 300

            while time.time() - query_start < MAX_WAIT:
                if shell.recv_ready():
                    chunk = shell.recv(65535)
                    if chunk:
                        stream_buffer.extend(chunk)
                        if b"begin 0 32PRINTER" in stream_buffer and not capturing:
                            capturing = True
                        if capturing:
                            if re.search(rb'\nend(\r|\n|\x1b)', stream_buffer) or b"\x1b[4i" in stream_buffer:
                                finished = True
                                break
                time.sleep(0.05)

            if not finished:
                raise TimeoutError("99.7.5.11: 32prn ストリーム受信がタイムアウトしました。")

            raw_text = decode_32prn_stream(stream_buffer)
            cleaned_text = clean_printer_data(raw_text)
            rows = parse_report_to_rows(cleaned_text)

            row_count = len(rows) - 1
            if row_count <= 0:
                raise ValueError("99.7.5.11: 抽出結果が0件でした。")

            elapsed = time.time() - start_t
            log_info(f"並行ワーカー [99.7.5.11 売上]: 抽出完了 {row_count:,}件 ({elapsed:.1f}秒) ➔ 即時GAS送信")

            payload = {
                "menu": "99.7.5.11",
                "title": "Sales",
                "sender": user,
                "exportedAt": datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                "data": rows
            }
            send_to_gas_via_browser(payload, PARALLEL_GAS_URL, title="Google Sheets 転送 (99.7.5.11 Sales)")
            return {"count": row_count, "elapsed": elapsed}

        finally:
            ssh.close()

    def _on_parallel_subtask_success(self, menu_name: str, res: dict):
        """並行タスクの片方が完了した際の通知処理"""
        cnt = res.get("count", 0)
        elp = res.get("elapsed", 0.0)
        label_map = {"99.7.6.20": "受注残", "99.7.5.11": "売上"}
        lbl = label_map.get(menu_name, menu_name)
        self.set_status(f"⚡ [完了速報] {lbl}({menu_name}) をGASへ転送完了 ({cnt:,}件 / {elp:.1f}秒)", "working")
        log_info(f"並行送信サブタスク完了: {menu_name} ({lbl}) -> {cnt:,}件 ({elp:.1f}秒)")

    def _on_parallel_subtask_error(self, menu_name: str, err: str):
        """並行タスクの片方でエラーが発生した際の通知処理"""
        label_map = {"99.7.6.20": "受注残", "99.7.5.11": "売上"}
        lbl = label_map.get(menu_name, menu_name)
        self.set_status(f"⚠️ [{lbl} {menu_name}] エラー: {err}", "error", clear_delay=8)
        log_error(f"並行送信サブタスクエラー: {menu_name} ({lbl}) -> {err}")

    def _on_parallel_all_done(self, results: dict, total_elapsed: float):
        """すべての並行タスク完了時の通知処理（ポップアップは出さず、ステータスバーとログで通知）"""
        details = []
        total_count = 0
        has_error = False

        label_map = {"99.7.6.20": "受注残", "99.7.5.11": "売上"}
        for menu, r in results.items():
            lbl = label_map.get(menu, menu)
            if "error" in r:
                has_error = True
                details.append(f"{lbl}: 失敗")
            else:
                cnt = r.get("count", 0)
                total_count += cnt
                details.append(f"{lbl}: {cnt:,}件")

        summary_str = " & ".join(details)
        if has_error:
            self.set_status(f"⚠️ 並行送信完了 (一部エラー): {summary_str} ({total_elapsed:.1f}秒)", "warning", clear_delay=10)
        else:
            self.set_status(f"🎉 受注残＆売上の並行送信が完了しました ({summary_str} / 計{total_count:,}件 / {total_elapsed:.1f}秒)", "success", clear_delay=8)
        log_info(f"並行送信全完了: {summary_str} (総所要時間: {total_elapsed:.1f}秒)")

    def jump_to_menu(self, code):
        """指定されたメニュー番号へ直接ジャンプ（メイン画面ならF4を押さず直接入力、業務画面ならF4で戻って入力）"""
        if not self.is_connected or not self.session:
            self._show_input_error("サーバーに接続されていません")
            return

        # HOME / MAIN 等のショートカット指定時は直接HOME画面復帰を実行
        code_str = str(code).strip()
        if code_str.upper() in ("HOME", "MAIN", "0", "MENU"):
            self.go_home_screen()
            return

        # 現在の画面がメインメニュー（mfmenu）かどうかを判定
        is_main = self.is_main_menu()

        # メインスレッド側で即座に状況を表示
        if is_main:
            self._show_input_error(f"メイン画面から直接ジャンプ: {code}")
        else:
            self._show_input_error(f"メニューに戻ってジャンプ: {code}")

        def _do_jump():
            try:
                import time
                if is_main:
                    # メイン画面にいる場合: F4を押すとEXITエラーになるため、F4を押さずに直接送信
                    self.session.send(f"{code}\r")
                else:
                    # 業務画面・入力フィールドにいる場合: F4でメニューに戻ってから番号を送信
                    self.session.send(KEY_SEQUENCES["F4"])

                    # メイン画面（またはメニュー画面）に切り替わるのをスマート待機（最大1.2秒）
                    waited = 0.0
                    while waited < 1.2:
                        time.sleep(0.1)
                        waited += 0.1
                        if self.is_main_menu() or self.is_menu_screen():
                            break

                    time.sleep(0.15)
                    self.session.send(f"{code}\r")
            except Exception as e:
                print(f"メニュー直接ジャンプエラー: {e}", file=sys.stderr)
            finally:
                try:
                    self.after(100, self.focus_terminal)
                except Exception:
                    pass

        import threading
        threading.Thread(target=_do_jump, daemon=True, name="menu-jump").start()

    def _get_current_screen_text(self):
        """画面に表示されているテキスト全体を取得"""
        lines = []
        if getattr(self, "raw_lines", None):
            for r in range(ROWS):
                if r in self.raw_lines and self.raw_lines[r]:
                    lines.append(self.raw_lines[r][0].rstrip())
                else:
                    lines.append("")
            while lines and not lines[-1]:
                lines.pop()
            return "\n".join(lines)
        else:
            try:
                return self.textbox.get("1.0", "end-1c").rstrip()
            except Exception:
                return ""

    def copy_screen_text(self, event=None):
        """画面に表示されているテキスト全体をクリップボードにコピー"""
        text = self._get_current_screen_text()
        if text:
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update()
                self._show_input_error("画面の文字をクリップボードにコピーしました 📋")
            except Exception as e:
                self._show_input_error(f"コピー失敗: {e}")
        else:
            self._show_input_error("コピーする画面テキストがありません")
        return "break"

    def export_to_excel(self, event=None):
        """画面上の表データ（または複数ページレポート）をCSV化してExcelで直接起動"""
        log_info("export_to_excel: 手動実行が呼び出されました")
        text = self._get_current_screen_text()
        if not text.strip():
            self.set_status("❌ 出力対象の画面データがありません", "error", clear_delay=4)
            return "break"

        # 複数ページレポートの途中（'space bar to continue' 等、日英両対応）か判定
        lower_text = text.lower()
        has_more_pages = (
            any(p in lower_text for p in ["press space", "space to continue", "space bar", "more..."])
            or any(p in text for p in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行", "終了するには"])
        )

        if has_more_pages and self.is_connected and self.session is not None:
            self._fetch_all_pages_and_open_excel()
        else:
            self._parse_and_open_excel(text, title="qad_screen")
        return "break"

    def _fetch_all_pages_and_open_excel(self):
        """複数ページのレポートを自動スクロールしながら全ページ取得し、1つのCSVとしてExcelで開く"""
        if not self.is_connected or self.session is None:
            text = self._get_current_screen_text()
            if text.strip():
                self._parse_and_open_excel(text, title="qad_screen")
            else:
                self.set_status("❌ 未接続です", "error", clear_delay=4)
            return

        def _worker():
            log_info("手動レポート全ページ取得ワーカーを開始します")
            self.set_status("⏳ レポートを全ページ自動取得中... (Space送信)", "working")
            all_screens = []
            max_pages = 300
            page_count = 0
            last_text = ""
            consecutive_same = 0

            CONTINUE_KEYS = ["press space", "space to continue", "space bar", "more...", "スペース", "ｽﾍﾟｰｽ", "継続", "続行"]
            END_KEYS = ["end of report", "レポート終了", "selection:", "セレクション"]

            while page_count < max_pages and not self.closing:
                cur_text = self._get_current_screen_text()
                if cur_text and cur_text != last_text:
                    all_screens.append(cur_text)
                    last_text = cur_text
                    page_count += 1
                    consecutive_same = 0
                    log_info(f"手動取得: {page_count} ページ目取得")
                    self.set_status(f"📊 レポートデータを自動取得中: {page_count} ページ目 (Space送信)...", "working")
                else:
                    consecutive_same += 1
                    if consecutive_same >= 5:
                        break

                lower = cur_text.lower() if cur_text else ""
                if any(k in lower for k in END_KEYS):
                    log_info(f"終了プロンプト検出: 取得完了")
                    break

                if self.is_main_menu() or self.is_menu_screen():
                    log_info("メニュー画面に戻ったため取得終了")
                    break

                has_continue = any(k in lower for k in CONTINUE_KEYS) or any(k in cur_text for k in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行"])
                if has_continue:
                    try:
                        self.session.send(" ")
                    except Exception as e:
                        log_error(f"Space送信エラー: {e}")
                        break
                    time.sleep(0.3)
                else:
                    time.sleep(0.25)
                    check_text = self._get_current_screen_text()
                    check_lower = check_text.lower() if check_text else ""
                    if any(k in check_lower for k in CONTINUE_KEYS) or any(k in check_text for k in ["スペース", "ｽﾍﾟｰｽ"]):
                        try:
                            self.session.send(" ")
                        except Exception:
                            break
                        time.sleep(0.3)
                    else:
                        break

            if not all_screens:
                log_warning("手動全画面取得結果が空でした")
                self.set_status("❌ レポートデータが取得できませんでした", "error", clear_delay=4)
                return

            full_text = "\n".join(all_screens)
            self._parse_and_open_excel(full_text, title=f"qad_report_{page_count}pages")

        threading.Thread(target=_worker, daemon=True, name="excel-fetch").start()

    def _parse_and_open_excel(self, text, title="QAD_Report"):
        """テキストを表データにパースし、新規Excelを開いて全セルを文字列として貼り付ける"""
        self.set_status("📋 レポートデータを解析中...", "working")
        rows = parse_report_text_to_table(text)
        if not rows or (len(rows) == 1 and not any(rows[0])):
            log_warning("表データパース失敗")
            self.set_status("❌ 解析可能な表データが見つかりませんでした", "error", clear_delay=4)
            return

        self.set_status(f"🚀 Excelを新規作成し、全セルを文字列形式(@)で展開中...", "working")
        success, msg = paste_to_new_excel(rows, title=title)
        if success:
            self.set_status(f"✅ {msg}", "success", clear_delay=8)
        else:
            self.set_status(f"❌ {msg}", "error", clear_delay=6)

    def copy_selection_or_screen(self, event=None):
        if self._route_order_edit("<<Copy>>"):
            return "break"
        """テキスト選択範囲があれば選択部分を、なければ画面全体をコピー"""
        selected_text = ""
        try:
            if self.textbox.tag_ranges("sel"):
                selected_text = self.textbox.get("sel.first", "sel.last")
        except Exception:
            selected_text = ""

        if selected_text:
            try:
                self.clipboard_clear()
                self.clipboard_append(selected_text)
                self.update()
                self._show_input_error(f"選択範囲をコピーしました 📋 ({len(selected_text)}文字)")
            except Exception as e:
                self._show_input_error(f"コピー失敗: {e}")
            return "break"
        else:
            return self.copy_screen_text(event)

    def paste_from_clipboard(self, event=None):
        """クリップボードから文字列を取得し、サーバーへキー入力として安全に送信"""
        if self._route_order_edit("<<Paste>>"):
            return "break"
        if not self.is_connected or self.session is None:
            self._show_input_error("未接続のため貼り付けできません")
            return "break"
        try:
            text = self.clipboard_get()
        except Exception:
            self._show_input_error("クリップボードが空か、取得できませんでした")
            return "break"
        if not text:
            return "break"

        # テキスト選択状態があれば解除（貼り付け後の画面選択残りを防止）
        try:
            self.textbox._textbox.tag_remove("sel", "1.0", "end")
        except Exception:
            pass

        # 改行コードの正規化: Windows (\r\n) や Unix (\n) を VT100 / QAD 形式 (\r) に変換
        text = text.replace("\r\n", "\r").replace("\n", "\r")

        # CP932 エンコード事前チェック
        try:
            text.encode("cp932")
        except UnicodeEncodeError:
            self.bell()
            self._show_input_error("貼り付けできません：CP932（日本語）で表現できない文字が含まれています。")
            return "break"

        self._send(text)
        self._show_input_error(f"クリップボードの内容を貼り付けました 📋 ({len(text)}文字)")
        return "break"

    def insert_today_date(self, event=None):
        """今日の日付を 'mm/dd/yy' 形式でサーバーへ送信（入力欄への直接入力・貼り付け）"""
        if not self.is_connected or self.session is None:
            self._show_input_error("未接続のため日付を入力できません")
            return "break"

        # クエリ待機中やレポート取得中の場合は誤送信を防止
        if (
            getattr(self, "_is_waiting_query", False)
            or getattr(self, "_is_capturing_winprint", False)
            or getattr(self, "_is_capturing_report", False)
        ):
            return "break"

        # テキスト選択状態があれば解除
        try:
            self.textbox._textbox.tag_remove("sel", "1.0", "end")
        except Exception:
            pass

        today_str = datetime.date.today().strftime("%m/%d/%y")
        self._send(today_str)
        self._show_input_error(f"今日の日付 '{today_str}' を入力しました 📅")
        return "break"

    def select_all_text(self, event=None):
        """ターミナル画面のテキスト全体を選択状態にする"""
        if self._route_order_edit("<<SelectAll>>"):
            return "break"
        try:
            self.textbox.tag_add("sel", "1.0", "end-1c")
            self.textbox.focus_set()
            self._show_input_error("画面全体のテキストを選択しました")
        except Exception:
            pass
        return "break"

    def _on_paste_event(self, event=None):
        """Tkinterネイティブのペーストイベントハンドラ（画面崩れを防ぎサーバーへ送信）"""
        if self.config.get("enable_windows_shortcuts", True):
            self.paste_from_clipboard()
        return "break"

    def toggle_windows_shortcuts(self):
        """Windows標準ショートカット（Ctrl+C / Ctrl+V / Ctrl+A）の有効/無効切り替え"""
        val = bool(self.windows_shortcuts_var.get())
        self.config["enable_windows_shortcuts"] = val
        save_config(self.config)
        if val:
            self._show_input_error("Windows標準ショートカット（Ctrl+C/V/A）を有効化しました")
        else:
            self._show_input_error("Windows標準ショートカットを無効化しました（端末標準キー送信）")

    def toggle_block_server_shortcuts(self):
        """F1/F4以外のサーバー側ショートカット（Ctrl系制御コードや不要ファンクションキー）の無効化切替"""
        val = bool(self.block_server_shortcuts_var.get())
        self.config["block_server_shortcuts"] = val
        save_config(self.config)
        if val:
            self._show_input_error("F1/F4以外のサーバー側ショートカットを無効化しました（安全保護有効）")
        else:
            self._show_input_error("サーバー側ショートカットの保護を解除しました（全キー送信）")

    def toggle_auto_excel_export(self):
        """local出力レポートの自動Excel展開機能の有効/無効切替"""
        val = bool(self.auto_excel_var.get())
        self.config["auto_excel_export"] = val
        save_config(self.config)
        self._update_status_info()
        if val:
            self.set_status("レポート出力を自動でExcelに展開（文字列書式）を有効化しました", "info", clear_delay=4)
        else:
            self.set_status("レポート自動Excel展開を無効化しました", "info", clear_delay=4)

    def toggle_auto_login_main_menu(self):
        """ログイン後に自動でMain Menuへ移動する機能の有効/無効切替"""
        val = bool(self.auto_main_menu_var.get())
        self.config["auto_login_main_menu"] = val
        save_config(self.config)
        if val:
            self._show_input_error("ログイン後に自動でMain Menuへ移動を有効化しました")
        else:
            self._show_input_error("ログイン後の自動移動を無効化しました")

    def toggle_auto_winprint_on_f1(self):
        """Output欄でF1押下時に自動で32printerを実行する機能の有効/無効切替"""
        val = bool(self.auto_winprint_f1_var.get())
        self.config["auto_winprint_on_f1"] = val
        self.config["auto_32printer_on_f1"] = val
        save_config(self.config)
        if val:
            self._show_input_error("Output欄でF1押下時に自動で32printer実行を有効化しました")
        else:
            self._show_input_error("Output欄での自動32printerを無効化しました（通常F1送信）")

    def _check_is_report_output(self):
        """現在の画面が QAD レポート出力（local 出力結果）であるかを高精度に判定"""
        # メインメニューや通常メニュー画面は除外
        if self.is_main_menu() or self.is_menu_screen():
            return False

        lines = []
        if getattr(self, "raw_lines", None):
            lines = [self.raw_lines[r][0] for r in sorted(self.raw_lines.keys()) if self.raw_lines.get(r)]
        if not lines:
            try:
                lines = self.textbox.get("1.0", "end").splitlines()
            except Exception:
                lines = []

        if len(lines) < 3:
            return False

        full_text = "\n".join(lines)
        full_lower = full_text.lower()

        # 【超重要】条件入力画面（パラメータ入力・Output指定・Batch ID入力）は絶対に除外！
        # F1 を1回押して Output 欄や Batch ID 欄にカーソルが移動した入力画面を誤検知させない
        is_input_prompt_screen = (
            "output:" in full_lower or "output :" in full_lower
            or "batch id:" in full_lower or "batch id :" in full_lower
            or "enter data or press f4" in full_lower
            or ("from:" in full_lower and "to:" in full_lower)
        )
        if is_input_prompt_screen:
            return False

        # 1. 画面全体（全行）からカラム区切り線を検出
        sep_row_idx = -1
        sep_pattern = re.compile(r'[-─]{2,}\s+[-─]{2,}')
        for idx, line in enumerate(lines):
            clean = line.replace("│", " ").strip()
            if sep_pattern.search(clean) or clean.count("---") >= 2 or (clean.startswith("---") and len(clean) >= 15):
                if not any(c in line for c in ("┌", "┐", "└", "┘", "├", "┤")):
                    sep_row_idx = idx
                    break

        if sep_row_idx == -1:
            return False

        # 2. プロンプトまたは待機フラグの判定
        has_prompt = (
            any(p in full_lower for p in ["press space", "space to continue", "space bar", "more...", "-- more --", "end of report", "return to exit"])
            or any(p in full_text for p in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行", "終了するには", "レポート終了"])
        )

        # クエリ実行待機中フラグ（F1押下後）が立っていれば、入力画面が消えて区切り線が出現した時点でTrue
        if getattr(self, "_is_waiting_query", False):
            log_info(f"_check_is_report_output: 一致！ (クエリ待機中 + レポート区切り線行 {sep_row_idx} 検出: {lines[sep_row_idx][:50]})")
            return True

        # プロンプトが検出された場合もTrue
        if has_prompt:
            log_info(f"_check_is_report_output: 一致！ (区切り線行 {sep_row_idx} + プロンプト検出)")
            return True

        # 区切り線があり、かつ上部にカラムヘッダー、下部にデータ行があればTrue
        if sep_row_idx >= 1 and sep_row_idx < len(lines) - 1:
            data_lines = [l for l in lines[sep_row_idx + 1:] if l.strip()]
            if len(data_lines) >= 1:
                log_info(f"_check_is_report_output: 一致！ (区切り線行 {sep_row_idx} + データ行 {len(data_lines)} 行検出)")
                return True

        return False


    def _start_auto_report_capture(self):
        """サーバーからの local レポート出力を自動で全ページ受信し、Excelを開いて文字列として貼り付ける"""
        if self._is_capturing_report:
            return
        self._is_capturing_report = True
        self._is_waiting_query = False  # クエリ待機完了

        def _worker():
            log_info("=== レポート自動取得・Excel展開ワーカー起動 ===")
            self.set_status("📊 QADレポート出力を検出しました。全データを自動取得中... (Space送信)", "working")
            all_screens = []
            max_pages = 300
            page_count = 0
            last_text = ""
            consecutive_same_count = 0

            # 継続プロンプト判定用キーワード（日英両対応）
            CONTINUE_KEYWORDS = [
                "press space", "space to continue", "space bar", "more...", "-- more --",
                "スペース", "ｽﾍﾟｰｽ", "継続", "続行", "<return>", "return to exit"
            ]
            # 終了キーワード
            END_KEYWORDS = [
                "end of report", "レポート終了", "selection:", "セレクション"
            ]

            try:
                while page_count < max_pages and not self.closing:
                    cur_text = self._get_current_screen_text()
                    if cur_text and cur_text != last_text:
                        all_screens.append(cur_text)
                        last_text = cur_text
                        page_count += 1
                        consecutive_same_count = 0
                        log_info(f"レポート取得: {page_count} ページ目取得完了 (文字数: {len(cur_text)})")
                        self.set_status(f"📊 レポートデータを自動取得中: {page_count} ページ目 (Space送信)...", "working")
                    else:
                        consecutive_same_count += 1
                        if consecutive_same_count >= 5:
                            log_info(f"画面変化なしが {consecutive_same_count} 回継続したためページ送り終了")
                            break

                    lower = cur_text.lower() if cur_text else ""

                    # 終了判定
                    if any(k in lower for k in END_KEYWORDS):
                        log_info(f"レポート終了プロンプトを検出: {lower[-80:]}")
                        break

                    # メインメニューやメニュー画面に戻っていたら終了
                    if self.is_main_menu() or self.is_menu_screen():
                        log_info("メニュー画面に戻ったためレポート取得終了")
                        break

                    # 継続プロンプトがあれば Space キーを送信して次ページへ
                    has_continue = any(k in lower for k in CONTINUE_KEYWORDS) or any(k in cur_text for k in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行"])
                    if has_continue:
                        try:
                            if self.is_connected and self.session is not None:
                                log_debug(f"Space キー送信 (page {page_count})")
                                self.session.send(" ")
                        except Exception as e:
                            log_error(f"Space キー送信エラー: {e}")
                            break
                        time.sleep(0.3)
                    else:
                        # プロンプトが見当たらない場合、少し待って再確認
                        time.sleep(0.25)
                        check_text = self._get_current_screen_text()
                        check_lower = check_text.lower() if check_text else ""
                        if any(k in check_lower for k in CONTINUE_KEYWORDS) or any(k in check_text for k in ["スペース", "ｽﾍﾟｰｽ"]):
                            try:
                                if self.is_connected and self.session is not None:
                                    log_debug(f"再確認後 Space キー送信 (page {page_count})")
                                    self.session.send(" ")
                            except Exception:
                                break
                            time.sleep(0.3)
                        else:
                            # 継続プロンプトなし ＆ 終了プロンプトなし → 1ページのみのレポート等
                            log_info("継続プロンプトが見当たらないため取得完了と判断")
                            break

                if not all_screens:
                    log_warning("全画面取得結果が空でした")
                    self.set_status("❌ レポートデータが取得できませんでした", "error", clear_delay=5)
                    return

                log_info(f"全 {len(all_screens)} ページの取得完了。パース処理を開始します...")
                self.set_status("📋 レポートデータを解析中...", "working")

                full_text = "\n".join(all_screens)
                rows = parse_report_text_to_table(full_text, deduplicate=True)

                if not rows or (len(rows) == 1 and not any(rows[0])):
                    log_warning(f"パース失敗: 行数={len(rows) if rows else 0}")
                    self.set_status("❌ レポートの表データをパースできませんでした", "error", clear_delay=5)
                    return

                log_info(f"パース成功: カラム数={len(rows[0])}, データ行数={len(rows) - 1}")
                self.set_status(f"🚀 Excelを新規作成し、全 {len(rows) - 1} 件を文字列として展開中...", "working")

                success, msg = paste_to_new_excel(rows, title="QAD_Report")
                log_info(f"Excel展開結果: success={success}, msg={msg}")

                if success:
                    self.set_status(f"✅ {msg}", "success", clear_delay=8)
                else:
                    self.set_status(f"❌ {msg}", "error", clear_delay=6)
            except Exception as e:
                log_error(f"自動Excel出力例外エラー: {e}", exc_info=True)
                self.set_status(f"❌ 自動Excel出力エラー: {e}", "error", clear_delay=6)
            finally:
                self._is_capturing_report = False
                self._is_waiting_query = False
                self._last_report_capture_time = time.time()

        threading.Thread(target=_worker, daemon=True, name="auto-excel-capture").start()

    def input_32printer(self):
        """Output欄に '32prn' を入力し、決定＋実行キーシーケンス（F1x2 + Ctrl+F）を送信して抽出を開始"""
        if not self.is_connected:
            self.set_status("❌ 未接続です", "error", clear_delay=3)
            return
        log_info("input_32printer: Output欄に 32prn を入力し、実績キーシーケンスで実行します")
        self.set_status("⏳ Output: 32prn を指示し、レポート実行を開始中...", "waiting")

        def _runner():
            try:
                # 1. 32prn と Enter を送信
                self._send("32prn\r")
                time.sleep(1.0)
                # 2. F1キー（1回目）を送信
                self._send("\x1bOP")
                time.sleep(1.0)
                # 3. F1キー（2回目）を送信
                self._send("\x1bOP")
                time.sleep(1.0)
                # 4. Ctrl+F (\x06) を送信して抽出確定
                self._send("\x06")
                time.sleep(1.0)
                # 5. Program Information 画面（Press space bar to continue）を閉じるため Space を自動送信
                self._send(" ")
                log_info("input_32printer: キーシーケンス送信完了 (32prn\\r -> F1 -> F1 -> Ctrl+F -> Space)")
            except Exception as e:
                log_error(f"input_32printer エラー: {e}", exc_info=True)

        threading.Thread(target=_runner, daemon=True, name="32printer-key-sequence").start()

    def input_winprint(self):
        """互換用エイリアス"""
        self.input_32printer()

    def _start_winprint_capture(self):
        """互換用エイリアス（32printerストリームで自動処理されるため何もしない）"""
        pass

    def _handle_32printer_data(self, captured_bytes: bytes):
        """32printer からの圧縮データストリームを受信し、自動で解凍＆Excel展開"""
        log_info(f"=== 32printer データストリーム受信完了 ({len(captured_bytes):,} bytes) ===")
        self.set_status(f"📥 32printer 圧縮データ受信完了 ({len(captured_bytes)/1024:.1f} KB) → 解凍中...", "working")

        def _worker():
            try:
                raw_text = decode_32prn_stream(captured_bytes)
                final_text = clean_printer_data(raw_text)
                log_info(f"32printer 解凍完了 (文字数: {len(final_text):,})")

                self.set_status("📋 レポートデータを解析中...", "working")
                rows = parse_report_to_rows(final_text)
                if not rows or (len(rows) == 1 and not any(rows[0])):
                    rows = parse_report_text_to_table(final_text, deduplicate=False)

                if not rows or (len(rows) == 1 and not any(rows[0])):
                    log_warning("32printer データのパース失敗")
                    self.set_status("❌ レポートデータの解析に失敗しました", "error", clear_delay=5)
                    return

                row_count = len(rows) - 1
                log_info(f"32printer パース成功 (列数={len(rows[0])}, データ行数={row_count:,})")
                self.set_status(f"🚀 Excelを新規作成し、全 {row_count:,} 件を展開中...", "working")

                screen_txt = self._get_current_screen_text()
                match = re.search(r'\b(\d+\.\d+(?:\.\d+)*)\b', screen_txt)
                title = f"QAD_{match.group(1)}" if match else "QAD_Report"

                success, msg = paste_to_new_excel(rows, title=title)
                if success:
                    self.set_status(f"✅ 32printer出力を検知し、{msg}", "success", clear_delay=8)
                else:
                    self.set_status(f"❌ {msg}", "error", clear_delay=6)

                # 処理完了後、画面に「Press space bar」または「Program Information」があれば自動でSpaceを送信して復帰
                try:
                    time.sleep(1.0)
                    cur_screen = self._get_current_screen_text()
                    cur_screen_lower = cur_screen.lower() if cur_screen else ""
                    if "press space" in cur_screen_lower or "program information" in cur_screen_lower:
                        self._send(" ")
                except Exception:
                    pass

            except Exception as e:
                log_error(f"32printer 処理例外: {e}", exc_info=True)
                self.set_status(f"❌ 32printer 処理エラー: {e}", "error", clear_delay=6)

        threading.Thread(target=_worker, daemon=True, name="32printer-excel-worker").start()



    # --- カラーパレット・テーマ切替処理 ---
    def open_color_palette(self):
        ColorPaletteDialog(self, self)

    def switch_theme(self, theme_key):
        """プリセットテーマへの切り替え（ターミナル表示部のみ変更）"""
        if theme_key not in COLOR_THEMES:
            return
        self.config["theme"] = theme_key
        self.config["custom_terminal_bg"] = None
        self.config["custom_terminal_fg"] = None
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def set_terminal_custom_color(self, bg=None, fg=None):
        """ターミナルの背景色・文字色をカスタム指定（ターミナル表示部のみ変更）"""
        if bg:
            self.config["custom_terminal_bg"] = bg
        if fg:
            self.config["custom_terminal_fg"] = fg
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def reset_custom_colors(self):
        """カスタム色をリセットしテーマ標準に戻す（ターミナル表示部のみ変更）"""
        self.config["custom_terminal_bg"] = None
        self.config["custom_terminal_fg"] = None
        save_config(self.config)
        self.terminal_colors = self._get_terminal_colors()
        self.colors = self.terminal_colors
        self._refresh_theme_ui()

    def _refresh_theme_ui(self):
        """ターミナル表示部分（画面内）の配色を再描画"""
        self._tab_image_cache = {}
        if hasattr(self, "terminal_container"):
            self.terminal_container.configure(fg_color=self.terminal_colors["terminal"])
        for tab in getattr(self, "tabs", []):
            if hasattr(tab, "terminal_panel"):
                tab.terminal_panel.configure(fg_color=self.terminal_colors["terminal"])
            if tab.textbox:
                tab.textbox.configure(
                    fg_color=self.terminal_colors["terminal"],
                    text_color=self.terminal_colors["text"],
                )
                self._apply_text_tags_to_widget(tab.textbox)
        self._update_cursor_tag_style()
        self._render_tab_buttons()
        self._rerender_all()

    # --- ログイン情報ダイアログ ---
    def open_login_dialog(self):
        LoginConfigDialog(self, self.config, self._on_login_config_saved)

    def _on_login_config_saved(self, new_config):
        self.config = new_config

    # --- 状態更新・描画ロジック ---
    def _set_state(self, text, color="muted"):
        cur_tab = self.active_tab
        user = self.config.get("user", "takehik")
        host = self.config.get("host", "mfg03")

        if hasattr(self, "status_label") and self.status_label is not None:
            try:
                if cur_tab and cur_tab.is_connected:
                    self.status_label.configure(text=f"🟢 {user}@{host}", text_color="#10B981")
                elif text == "接続中…":
                    self.status_label.configure(text="⏳ 接続中…", text_color="#F59E0B")
                else:
                    self.status_label.configure(text="⚪ 未接続", text_color="#94A3B8")
            except Exception:
                pass

        idle = (cur_tab is None or cur_tab.session is None)
        if hasattr(self, "connect_btn") and self.connect_btn is not None:
            try:
                self.connect_btn.configure(state="normal" if idle else "disabled")
            except Exception:
                pass
        if hasattr(self, "disconnect_btn") and self.disconnect_btn is not None:
            try:
                self.disconnect_btn.configure(state="disabled" if idle else "normal")
            except Exception:
                pass
        self.connection_menu.entryconfigure(0, state="normal" if idle else "disabled")
        self.connection_menu.entryconfigure(1, state="disabled" if idle else "normal")
        state = "normal" if (cur_tab and cur_tab.is_connected) else "disabled"
        if hasattr(self, "home_btn"):
            self.home_btn.configure(state=state)
        if hasattr(self, "winprint_btn"):
            self.winprint_btn.configure(state=state)
        for button in getattr(self, "shortcut_buttons", []):
            button.configure(state=state)

        if hasattr(self, "_update_data_transmission_buttons_state"):
            self._update_data_transmission_buttons_state()

    def _show_tab_message(self, tab: TerminalTab, message: str):
        """指定タブのテキストボックスに初期/案内メッセージを表示"""
        if not tab or not tab.textbox:
            return
        tb = tab.textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        if message:
            tb.insert("1.0", message)
        else:
            tb.insert("1.0", "\n" * (ROWS - 1))
        for tag in ("reverse", "menu_highlight", "underline", "bold", "remote_cursor"):
            tb.tag_remove(tag, "1.0", "end")
        tb.configure(state="disabled")
        tab.rendered_lines = [None] * ROWS
        tab.raw_lines = {}
        try:
            tb._textbox.yview_moveto(0.0)
            tb._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def _show_message(self, message):
        """アクティブタブのテキストボックスにメッセージを表示"""
        cur = self.active_tab
        if cur:
            self._show_tab_message(cur, message)

    def connect_to_server(self):
        """アクティブタブのSSH接続を開始"""
        cur = self.active_tab
        if cur:
            self.connect_tab(cur)

    def _poll(self):
        """全タブのSSHイベントを監視・ディスパッチし、アクティブタブを描画"""
        if self.closing:
            return

        for tab in list(self.tabs):
            while True:
                try:
                    session, event, error = tab.events.get_nowait()
                except queue.Empty:
                    break
                if session is not tab.session:
                    continue

                if event == "connected":
                    tab.is_connected = True
                    self._show_tab_message(tab, "\n".join([" " * COLS] * ROWS))
                    if tab == self.active_tab:
                        self._set_state("接続済み", "success")
                        self.set_status("● 接続済み (Ready)", "info")
                        self._update_status_info()
                        self.focus_terminal()
                    self._render_tab_buttons()
                    log_info(f"SSH接続確立 (connected) [Tab {tab.tab_id}]")
                    if self.config.get("auto_login_main_menu", True):
                        threading.Thread(
                            target=lambda t=tab: self._auto_navigate_to_main_menu_for_tab(t),
                            daemon=True,
                            name=f"auto-main-menu-{tab.tab_id}"
                        ).start()
                elif event == "32printer_data":
                    self._handle_32printer_data(error)
                elif event == "closed":
                    if tab.is_connected:
                        self._update_tab_screen(tab)
                    tab.session = None
                    tab.is_connected = False
                    tab._is_waiting_query = False
                    if tab == self.active_tab:
                        self._set_state("接続エラー" if error else "切断済み", "error" if error else "muted")
                        self.set_status("● 接続エラー" if error else "● 切断済み", "error" if error else "info")
                        self._update_status_info()
                    self._render_tab_buttons()
                    log_info(f"SSH切断 (closed, error={error}) [Tab {tab.tab_id}]")
                    if error and tab == self.active_tab:
                        messagebox.showerror("SSH接続エラー", error, parent=self)

        # アクティブタブの画面差分描画 ＆ タイトル自動検知
        cur = self.active_tab
        if cur and cur.is_connected and cur.session:
            self._update_tab_screen(cur)
            self._detect_tab_title(cur)

        self.update_job = self.after(33, self._poll)

    def _update_tab_screen(self, tab: TerminalTab, force: bool = False):
        """指定タブの画面スナップショットを取得し、差分更新"""
        if not tab or not tab.session:
            return
        snapshot = tab.session.snapshot()
        if snapshot is None:
            return
        changed, cursor, active_cols = snapshot
        if getattr(tab, "active_cols", 80) != active_cols:
            tab.active_cols = active_cols
            if tab == self.active_tab:
                self._update_status_info()
                if tab.auto_fit:
                    self._apply_auto_fit()

        if force:
            changed_items = {row: data for row, data in changed.items()}
        else:
            changed_items = {row: data for row, data in changed.items() if tab.raw_lines.get(row) != data}

        tb = tab.textbox
        if changed_items:
            tb.configure(state="normal")
            for row, (raw_line, spans) in changed_items.items():
                line, pad_spans = self._align_border_line(raw_line)
                start_idx = f"{row + 1}.0"
                end_idx = f"{row + 1}.end"
                tb.delete(start_idx, end_idx)
                tb.insert(start_idx, line)
                for tag in ("reverse", "underline", "bold"):
                    tb.tag_remove(tag, start_idx, end_idx)
                for s_idx, e_idx, tags in spans:
                    for tag in tags:
                        tb.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
                for s_idx, e_idx, p_tag in pad_spans:
                    tb.tag_add(p_tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
                tab.rendered_lines[row] = (line, spans)
                tab.raw_lines[row] = (raw_line, spans)

            if tab == self.active_tab:
                self._apply_menu_highlight()
                self._auto_align_header_border()
            tb.configure(state="disabled")

            # レポート自動検知（アクティブタブのみ）
            if tab == self.active_tab and self.config.get("auto_excel_export", True) and not self._is_capturing_report and not getattr(self, "_is_capturing_winprint", False):
                now = time.time()
                is_waiting = getattr(self, "_is_waiting_query", False)
                cooldown = 0.5 if is_waiting else 3.0
                if now - self._last_report_capture_time > cooldown:
                    if self._check_is_report_output():
                        self._start_auto_report_capture()

            # クエリ待機タイムアウトまたはメニュー復帰の管理
            if tab == self.active_tab and getattr(self, "_is_waiting_query", False):
                now = time.time()
                if self.is_main_menu() or self.is_menu_screen():
                    log_info("メニュー画面に戻ったためクエリ待機状態を解除します")
                    self._is_waiting_query = False
                    self.set_status("● 接続済み (Ready)", "info")
                elif now - getattr(self, "_query_wait_start_time", now) > 180.0:
                    log_warning("クエリ待機が180秒を超過したため待機状態を解除します")
                    self._is_waiting_query = False
                    self.set_status("● 接続済み (Ready)", "info")

        tb.tag_remove("remote_cursor", "1.0", "end")
        if cursor is not None:
            tab.current_cursor = cursor
            if tab == self.active_tab and not getattr(tab, "is_navigating_field", False):
                row, column = cursor
                tb.tag_add("remote_cursor", f"{row + 1}.{column}", f"{row + 1}.{column + 1}")
                try:
                    tb._textbox.tag_raise("remote_cursor")
                except Exception:
                    pass
        else:
            tab.current_cursor = None

        try:
            tb._textbox.yview_moveto(0.0)
            tb._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def _update_screen(self):
        """アクティブタブの画面を差分更新"""
        cur = self.active_tab
        if cur:
            self._update_tab_screen(cur)

    def _align_border_line(self, line):
        """半角カナ・漢字を含む罫線行のピクセル幅を純ASCII罫線行と揃える"""
        border_right = {"┐", "┘", "│"}
        if not line or line[-1] not in border_right:
            return line, []
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(font=self.textbox._textbox.cget("font"))
        except Exception:
            return line, []
        ref_width = f.measure("M") * self.active_cols
        line_width = f.measure(line)
        needed = ref_width - line_width
        if needed <= 0:
            return line, []

        is_box_line = line and line[0] in {"┌", "└"}
        cw = f.measure("M")
        if cw <= 0:
            return line, []

        cur_font_size = self.font_size

        if is_box_line:
            # 上部・下部枠線行:
            # ─ のフォントサイズを変えるとアセントの違いで横線が凹んでしまうため、
            # ─ は必ず通常フォントサイズ(cur_font_size)で均一に描画する。
            pad_char = "─"
            spaces = [i for i, c in enumerate(line) if c == " "]
            if spaces:
                import math
                pad_count = max(1, math.ceil(needed / cw))
                overhang = (pad_count * cw) - needed  # 縮めるべきピクセル数
                new_line = line[:-1] + (pad_char * pad_count) + line[-1]

                tag_spans = []
                if overhang > 0:
                    # 行内の空白文字(スペース)を縮めてオーバー分を吸収する
                    # 空白は透明なため、アセントによる凹み等の視覚的副作用は一切発生しない
                    use_spaces = spaces[:min(len(spaces), 4)]
                    shrink_per_space = overhang / len(use_spaces)
                    target_w = max(1, cw - shrink_per_space)

                    best_sz = cur_font_size
                    best_diff = 999
                    for sz in range(max(4, cur_font_size - 14), cur_font_size):
                        w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(" ")
                        if abs(w - target_w) < best_diff:
                            best_diff = abs(w - target_w)
                            best_sz = sz

                    tag_name = f"space_shrink_{cur_font_size}_{best_sz}"
                    try:
                        self.textbox._textbox.tag_config(tag_name, font=(self.terminal_font_family, best_sz))
                    except Exception:
                        pass
                    for sp_idx in use_spaces:
                        tag_spans.append((sp_idx, sp_idx + 1, tag_name))
                return new_line, tag_spans
            else:
                # 空白がない場合は通常サイズの ─ を挿入（横線を絶対に凹ませず平坦に保つ）
                pad_count = max(1, round(needed / cw))
                new_line = line[:-1] + (pad_char * pad_count) + line[-1]
                return new_line, []
        else:
            # 中間データ行 (│ ... │):
            # パディング文字は空白 (" ") なので、フォントサイズ微調整を行っても
            # 透明のため横線の凹み等の視覚的副作用は一切生じない。
            pad_char = " "
            pad_count = max(1, round(needed / cw))
            base_w = needed // pad_count
            rem = needed % pad_count
            widths = [base_w + 1 if i < rem else base_w for i in range(pad_count)]

            pad_tags = []
            for idx, tw in enumerate(widths):
                best_sz = cur_font_size
                best_diff = 999
                for sz in range(max(6, cur_font_size - 10), cur_font_size + 10):
                    w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(pad_char)
                    if abs(w - tw) < best_diff:
                        best_diff = abs(w - tw)
                        best_sz = sz
                tag_name = f"pad_tag_sp_{cur_font_size}_{idx}_{best_sz}"
                try:
                    self.textbox._textbox.tag_config(tag_name, font=(self.terminal_font_family, best_sz))
                except Exception:
                    pass
                pad_tags.append(tag_name)

            start_char_idx = len(line) - 1
            new_line = line[:-1] + (pad_char * pad_count) + line[-1]
            tag_spans = [(start_char_idx + i, start_char_idx + i + 1, pad_tags[i]) for i in range(pad_count)]
            return new_line, tag_spans

    def _auto_align_header_border(self):
        """Textウィジェットの実測描画座標(bbox)に基づき、ヘッダー行(Row 0)の右端角(┐)を純罫線行と1px単位で完全一致させる"""
        try:
            tb = self.textbox._textbox
            b1 = tb.bbox("2.end-1c")
            b2 = tb.bbox("3.end-1c")
            target_x = None
            if b1 and b2:
                target_x = max(b1[0], b2[0])
            elif b1:
                target_x = b1[0]
            elif b2:
                target_x = b2[0]
            if not target_x:
                return

            b0 = tb.bbox("1.end-1c")
            if not b0:
                return
            diff_x = target_x - b0[0]
            if diff_x == 0:
                return  # 完全に一致している

            # 1〜3px の微差がある場合、行内の空白文字のタグフォントサイズを微調整して一致させる
            # （※ ─ 文字のフォントサイズを絶対に変更してはいけない！横線が凹む原因になるため）
            line0 = tb.get("1.0", "1.end")
            if len(line0) < 3 or line0[-1] != "┐":
                return

            # 行内の空白文字を探す
            spaces = [i for i, c in enumerate(line0) if c == " "]
            if not spaces:
                return

            import tkinter.font as tkfont
            sp_idx = spaces[0]
            char_idx_str = f"1.{sp_idx}"
            cur_tags = tb.tag_names(char_idx_str)
            existing_tag = next((t for t in cur_tags if t.startswith("space_shrink_") or t.startswith("space_auto_adj_")), None)
            cur_sz = self.font_size
            if existing_tag:
                parts = existing_tag.split("_")
                if len(parts) >= 4:
                    try:
                        cur_sz = int(parts[-1])
                    except Exception:
                        pass
                tb.tag_remove(existing_tag, char_idx_str, f"1.{sp_idx + 1}")

            cur_w = tkfont.Font(family=self.terminal_font_family, size=cur_sz).measure(" ")
            target_space_w = cur_w + diff_x
            best_sz = cur_sz
            best_d = 999
            for sz in range(max(4, self.font_size - 14), self.font_size + 10):
                w = tkfont.Font(family=self.terminal_font_family, size=sz).measure(" ")
                if abs(w - target_space_w) < best_d:
                    best_d = abs(w - target_space_w)
                    best_sz = sz

            new_tag = f"space_auto_adj_{best_sz}"
            tb.tag_config(new_tag, font=(self.terminal_font_family, best_sz))
            tb.tag_add(new_tag, char_idx_str, f"1.{sp_idx + 1}")
        except Exception:
            pass

    def _rerender_all(self):
        """フォントサイズ変更時・テーマ変更時に全行を新しいフォントメトリクスで再描画"""
        if not getattr(self, "raw_lines", None):
            return
        self.textbox.configure(state="normal")
        for row, (raw_line, spans) in self.raw_lines.items():
            line, pad_spans = self._align_border_line(raw_line)
            start_idx = f"{row + 1}.0"
            end_idx = f"{row + 1}.end"
            self.textbox.delete(start_idx, end_idx)
            self.textbox.insert(start_idx, line)
            for tag in ("reverse", "underline", "bold"):
                self.textbox.tag_remove(tag, start_idx, end_idx)
            for s_idx, e_idx, tags in spans:
                for tag in tags:
                    self.textbox.tag_add(tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
            for s_idx, e_idx, p_tag in pad_spans:
                self.textbox.tag_add(p_tag, f"{row + 1}.{s_idx}", f"{row + 1}.{e_idx}")
            self.rendered_lines[row] = (line, spans)
        self._apply_menu_highlight()
        self._auto_align_header_border()
        self.textbox.configure(state="disabled")
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass
        try:
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

    def _apply_menu_highlight(self):
        """メニュー選択プロンプトの入力番号に対応するメニュー項目を検知して暗転（ハイライト）する"""
        self.textbox.tag_remove("menu_highlight", "1.0", "end")
        input_num = None
        for row in range(ROWS):
            line_data = self.rendered_lines[row]
            if not line_data:
                continue
            line = line_data[0]
            m = re.search(r'(?:Please select a function.*?(?:EXIT|\b)|Selection:)\s+([0-9]+)', line)
            if m:
                input_num = m.group(1)
                break

        if not input_num:
            return

        pattern = re.compile(rf'(?<!\d){input_num}\.\s*([^│]+?)(?=\s{{2,}}\d+\.|\s*│|\Z)')
        for row in range(ROWS):
            line_data = self.rendered_lines[row]
            if not line_data:
                continue
            line = line_data[0]
            for m in pattern.finditer(line):
                self.textbox.tag_add("menu_highlight", f"{row + 1}.{m.start()}", f"{row + 1}.{m.end()}")

    def on_key_press(self, event):
        self._reset_cursor_blink()
        if event.state & 0x5 == 0x5 and event.keysym in ("Tab", "ISO_Left_Tab"):
            self.connect_btn.focus_set() if self.session is None else self.disconnect_btn.focus_set()
            return "break"

        is_ctrl = bool(event.state & 0x4)
        is_shift = bool(event.state & 0x1)
        keysym_lower = event.keysym.lower()

        # 1. Windows標準ショートカット（Ctrl+C / Ctrl+V / Ctrl+A / Shift+Insert）
        if self.config.get("enable_windows_shortcuts", True):
            # Ctrl+Shift+C: 画面全体の文字をコピー
            if is_ctrl and is_shift and keysym_lower == "c":
                return self.copy_screen_text(event)

            # Ctrl+C: 選択範囲（なければ画面全体）をコピー
            if is_ctrl and not is_shift and keysym_lower == "c":
                return self.copy_selection_or_screen(event)

            # Ctrl+V または Shift+Insert: クリップボードから貼り付け（サーバーへ送信）
            if (is_ctrl and not is_shift and keysym_lower == "v") or (is_shift and event.keysym in ("Insert", "KP_Insert")):
                return self.paste_from_clipboard(event)

            # Ctrl+A: 画面全体のテキストを選択
            if is_ctrl and not is_shift and keysym_lower == "a":
                return self.select_all_text(event)

            # Ctrl+D: 今日の日付を mm/dd/yy 書式で貼り付け（サーバーへ送信）
            if is_ctrl and not is_shift and keysym_lower == "d":
                return self.insert_today_date(event)

            # Ctrl+E: 画面のデータをCSV化してExcelで開く
            if is_ctrl and not is_shift and keysym_lower == "e":
                return self.export_to_excel(event)

            # Ctrl+H: HOME画面（メインメニュー）に戻る
            if is_ctrl and not is_shift and keysym_lower == "h":
                self.go_home_screen()
                return "break"

        # 2. サーバー側ショートカットの制御（F1/F4以外のCtrl系および不要ファンクションキーを無効化）
        if self.config.get("block_server_shortcuts", True):
            # ① Controlキーが押されている場合（上記Windows標準以外はすべて遮断）
            if is_ctrl:
                self._show_input_error(f"ショートカット 'Ctrl+{event.keysym}' は無効化されています")
                return "break"

            # ② ファンクションキー: F1, F4 以外はすべて遮断
            if event.keysym.startswith("F") and event.keysym[1:].isdigit():
                if event.keysym not in ("F1", "F4"):
                    self._show_input_error(f"ファンクションキー '{event.keysym}' は無効化されています（F1 / F4 のみ有効）")
                    return "break"

        # 3. 通常キー送信（英数字・記号・Enter・Space・Tab・Backspace・矢印キー・F1・F4等）
        if self.is_connected:
            if event.keysym == "F1":
                if self._handle_f1_action():
                    return "break"
            elif event.keysym == "F4":
                if getattr(self, "_is_waiting_query", False):
                    log_info("F4押下によりクエリ待機を解除しました")
                    self._is_waiting_query = False
                    self.set_status("● 接続済み (Ready)", "info")
            self._send(key_sequence(event.keysym, event.char, event.state))
        return "break"

    def _get_line_text(self, row):
        """指定行の画面テキストを取得（raw_linesまたはtextboxから安全に取得）"""
        if getattr(self, "raw_lines", None) and row in self.raw_lines and self.raw_lines[row]:
            return self.raw_lines[row][0]
        try:
            return self.textbox._textbox.get(f"{row + 1}.0", f"{row + 1}.end")
        except Exception:
            return ""

    def _is_cursor_at_output_field(self):
        """現在のカーソルがレポート画面の 'Output:' 入力欄にあるかを高精度に判定"""
        if not self.is_connected or self.is_main_menu() or self.is_menu_screen():
            return False

        cur_pos = getattr(self, "_current_cursor", None)
        if cur_pos is None:
            return False

        cur_row, cur_col = cur_pos
        line_text = self._get_line_text(cur_row)
        if not line_text:
            return False

        # 1. 行内に Output / 出力先 / 出力 ラベルが存在するか検索
        m = re.search(r'(?:output|出力(?:先)?)\s*[:：]?', line_text, re.IGNORECASE)
        if m:
            label_start = m.start()
            label_end = m.end()

            # カーソルがラベルの開始位置（直前含む）からラベル後方の一定範囲内にあるか
            if cur_col >= label_start:
                after_label = line_text[label_end:]
                # 次のラベル（例: "Batch ID:", "バッチID:", "To:" 等。複数スペースをまたがない）
                m_next = re.search(r'\b[A-Za-z0-9_]+(?:\s[A-Za-z0-9_]+)?\s*[:：]|(?:バッチ(?:\s*ID)?|オプション)\s*[:：]', after_label)
                if m_next:
                    next_label_start = label_end + m_next.start()
                    if cur_col < next_label_start:
                        return True
                    else:
                        return False
                else:
                    # 次のラベルがない場合でも、Output欄の長さは通常25文字以内
                    if cur_col <= label_end + 25:
                        return True
                    else:
                        return False

        # 2. カーソル直前の文字列（接頭辞）が Output: で終わっているかチェック
        prefix = line_text[:max(0, cur_col)]
        if re.search(r'(?:output|出力(?:先)?)\s*[:：]?\s*$', prefix, re.IGNORECASE):
            return True

        # 3. 画面上の underline 入力フィールドと照合
        try:
            fields = self._get_all_input_fields()
            cur_field = self._find_field_at(fields, cur_row, cur_col)
            if cur_field:
                before_field = line_text[:cur_field.start_col].rstrip()
                if re.search(r'(?:output|出力(?:先)?)\s*[:：]?$', before_field, re.IGNORECASE):
                    return True
        except Exception:
            pass

        return False

    def _handle_f1_action(self):
        """F1キー押下時に画面状態をチェックし、Output欄であれば32printer実行、またはレポート実行クエリ待機ステータスを設定"""
        if not self.is_connected:
            return False
        if self.is_main_menu() or self.is_menu_screen():
            return False

        # Output欄でのF1押下時に自動で32printerを実行する設定が有効な場合
        auto_32prn = self.config.get("auto_32printer_on_f1", self.config.get("auto_winprint_on_f1", True))
        if auto_32prn and self._is_cursor_at_output_field():
            log_info("Output欄での F1 押下を検知しました。自動で 32prn を設定して実行します。")
            self.input_32printer()
            return True

        cur_text = self._get_current_screen_text()
        lower = cur_text.lower() if cur_text else ""

        # 32prn 出力の指定がある場合
        if "32prn" in lower or "winprint" in lower:
            log_info("Output: 32prn を検知しました。ストリーム受信待機に入ります。")
            self.set_status("⏳ Output: 32prn 圧縮ストリームを待機中...", "waiting")
            return False

        # 画面内に Output / 出力 / 99. / From / To 等のレポート条件画面パターンがあるか判定
        is_report_input = (
            "output" in lower or "出力" in cur_text
            or "99." in cur_text or "local" in lower
            or "from:" in lower or "to:" in lower
        )
        if is_report_input:
            log_info("レポート条件入力画面で F1 キーが押下されました。クエリ待機ステータスを開始します。")
            self._is_waiting_query = True
            self._query_wait_start_time = time.time()
            self.set_status("⏳ サーバーの応答を待機中... (クエリ処理中)", "waiting")

        return False

    def _send(self, data):
        if not data or not self.is_connected or self.session is None:
            return
        try:
            self.session.send(data)
        except UnicodeEncodeError:
            self.bell()
            self.set_status("❌ 送信できません：CP932で表現できない文字です。", "error", clear_delay=4)
        except queue.Full:
            self.bell()
            self.set_status("❌ 送信待ちが多いため、キー入力を一度止めてください。", "error", clear_delay=4)
        else:
            # 待機中・処理中の重要なステータス表示中は、キー送信で消さないよう保護
            if getattr(self, "_current_status_type", "info") not in ("waiting", "working"):
                self._show_input_error("")

    def set_status(self, text, status_type="info", clear_delay=None):
        """画面下のステータスバーに現在の処理状況をリアルタイム表示

        status_type:
            'info': 通常状態（淡色）
            'waiting': クエリ応答待機中（アンバー #F59E0B）
            'working': 取得・解析・展開処理中（ブルー #3B82F6）
            'success': 処理完了（グリーン #10B981）
            'error': エラー（レッド #EF4444）
        """
        self._current_status_type = status_type
        color_map = {
            "info": self.ui_colors.get("muted", "#64748B"),
            "waiting": "#F59E0B",
            "working": "#3B82F6",
            "success": "#10B981",
            "error": self.ui_colors.get("error", "#EF4444"),
        }
        text_color = color_map.get(status_type, color_map["info"])

        # タイマーがあればキャンセル
        if getattr(self, "_status_clear_timer", None) is not None:
            try:
                self.after_cancel(self._status_clear_timer)
            except Exception:
                pass
            self._status_clear_timer = None

        if hasattr(self, "bottom_status_label"):
            self.bottom_status_label.configure(text=text, text_color=text_color)

        if clear_delay and clear_delay > 0:
            def _reset():
                if self.is_connected:
                    self.set_status("● 接続済み (Ready)", "info")
                else:
                    self.set_status("● 未接続", "info")
                self._status_clear_timer = None

            self._status_clear_timer = self.after(int(clear_delay * 1000), _reset)

    def _show_input_error(self, message):
        if message:
            # メッセージ種別に応じた適切なステータス表示（通常案内はinfo、エラー系のみerror）
            if any(message.startswith(p) for p in ("❌", "エラー", "コピー失敗", "未接続", "貼り付けできません", "ショートカット 'Ctrl", "ファンクションキー")):
                prefix = "" if message.startswith("❌") else "❌ "
                self.set_status(f"{prefix}{message}", status_type="error", clear_delay=4)
            else:
                self.set_status(message, status_type="info", clear_delay=3)
        else:
            if getattr(self, "_current_status_type", "info") not in ("waiting", "working"):
                if self.is_connected:
                    self.set_status("● 接続済み (Ready)", "info")
                else:
                    self.set_status("● 未接続", "info")

    def send_key(self, key):
        if key == "F1":
            if self._handle_f1_action():
                self.focus_terminal()
                return
        elif key == "F4":
            if getattr(self, "_is_waiting_query", False):
                log_info("ツールバー/メニューからの F4 送信によりクエリ待機を解除しました")
                self._is_waiting_query = False
                self.set_status("● 接続済み (Ready)", "info")
        self._send(KEY_SEQUENCES[key])
        self.focus_terminal()


    def focus_terminal(self):
        self.textbox.focus_set()

    # --- CLI風白点滅カーソル制御 ---
    def _start_cursor_blink(self):
        """CLI風の白点滅カーソルタイマーを開始"""
        self._cursor_blink_visible = True
        self._schedule_cursor_blink()

    def _schedule_cursor_blink(self):
        if getattr(self, "_cursor_blink_job", None) is not None:
            try:
                self.after_cancel(self._cursor_blink_job)
            except Exception:
                pass
            self._cursor_blink_job = None
        if not self.closing:
            self._cursor_blink_job = self.after(500, self._on_cursor_blink_tick)

    def _on_cursor_blink_tick(self):
        if self.closing:
            return
        if not getattr(self, "_is_navigating_field", False):
            self._cursor_blink_visible = not getattr(self, "_cursor_blink_visible", True)
            self._update_cursor_tag_style()
        self._schedule_cursor_blink()

    def _update_cursor_tag_style(self):
        """カーソルタグ（remote_cursor）のスタイルを白点滅状態に合わせて更新"""
        try:
            if getattr(self, "_cursor_blink_visible", True):
                # CLI風の白ブロックカーソル（白背景＋黒文字で視認性を最大化）
                self.textbox._textbox.tag_config(
                    "remote_cursor",
                    background="#FFFFFF",
                    foreground="#000000",
                )
                self.textbox._textbox.tag_raise("remote_cursor")
            else:
                # 消灯時: スタイルを透過（クリア）し、下地の文字色・背景色（反転や下線）をそのまま保持
                self.textbox._textbox.tag_config(
                    "remote_cursor",
                    background="",
                    foreground="",
                )
        except Exception:
            pass

    def _reset_cursor_blink(self):
        """キー入力やクリック時にカーソルを即座に白点灯状態にリセット"""
        self._cursor_blink_visible = True
        self._update_cursor_tag_style()
        self._schedule_cursor_blink()

    # --- 画面上クリックによる入力欄直接ナビゲーション ---
    def _get_all_input_fields(self):
        """画面上の下線（underline）属性を持つすべての入力可能欄を走査してリスト化"""
        try:
            ranges = self.textbox._textbox.tag_ranges("underline")
        except Exception:
            return []

        fields = []
        for i in range(0, len(ranges), 2):
            start_idx = str(ranges[i])
            end_idx = str(ranges[i + 1])
            s_parts = start_idx.split(".")
            e_parts = end_idx.split(".")
            s_row = int(s_parts[0]) - 1
            s_col = int(s_parts[1])
            e_row = int(e_parts[0]) - 1
            e_col = int(e_parts[1])

            if s_row == e_row:
                fields.append(InputField(s_row, s_col, e_col))
            else:
                for r in range(s_row, e_row + 1):
                    sc = s_col if r == s_row else 0
                    ec = e_col if r == e_row else self.active_cols
                    fields.append(InputField(r, sc, ec))

        fields.sort(key=lambda f: (f.row, f.start_col))
        return fields

    def _find_field_at(self, fields, row, col):
        """指定した行・列に対応する入力フィールドを特定（近接±2文字を含む）"""
        for f in fields:
            if f.row == row and f.start_col <= col <= f.end_col:
                return f
        for f in fields:
            if f.row == row and (f.start_col - 2 <= col <= f.end_col + 2):
                return f
        return None

    def _find_current_field(self, fields, cur_row, cur_col):
        """現在のカーソル位置が属する入力フィールドを特定"""
        for f in fields:
            if f.row == cur_row and f.start_col <= cur_col <= f.end_col:
                return f
        # 同一行にあるフィールドのうち、列の距離が最も近いものを選択（左列固定偏重を防止）
        same_row = [f for f in fields if f.row == cur_row]
        if same_row:
            return min(same_row, key=lambda f: min(abs(f.start_col - cur_col), abs(f.end_col - cur_col)))
        if fields:
            return min(fields, key=lambda f: (abs(f.row - cur_row), min(abs(f.start_col - cur_col), abs(f.end_col - cur_col))))
        return None

    def _on_terminal_click(self, event):
        """画面上の入力可能箇所（下線部）をクリックした際に、その欄へ自動でカーソルを移動させて入力可能にする"""
        self.focus_terminal()
        self._reset_cursor_blink()

        if not self.is_connected or self.session is None:
            return "break"
        if getattr(self, "_is_waiting_query", False) or getattr(self, "_is_capturing_winprint", False):
            return "break"
        if getattr(self, "_is_navigating_field", False):
            return "break"

        try:
            click_index = self.textbox._textbox.index(f"@{event.x},{event.y}")
            parts = click_index.split(".")
            click_row = int(parts[0]) - 1
            click_col = int(parts[1])
        except Exception:
            return "break"

        fields = self._get_all_input_fields()
        if not fields:
            return "break"

        target_field = self._find_field_at(fields, click_row, click_col)
        if target_field is None:
            # 入力可能欄以外をクリックした場合は通常フォーカスのみで、キャレット発生を抑止
            return "break"

        # テキスト選択状態の解除
        try:
            self.textbox._textbox.tag_remove("sel", "1.0", "end")
        except Exception:
            pass

        # 現在のカーソル位置を取得
        cur_pos = getattr(self, "_current_cursor", None)
        if cur_pos is None:
            cur_row, cur_col = target_field.row, target_field.start_col
        else:
            cur_row, cur_col = cur_pos

        cur_field = self._find_current_field(fields, cur_row, cur_col)
        if cur_field is None:
            cur_field = fields[0]

        # 画面上のフィールドを左右の列ブロックに分割（QADのFrom/To 2列構成に対応）
        left_fields = [f for f in fields if f.start_col < 40]
        right_fields = [f for f in fields if f.start_col >= 40]

        cur_is_left = cur_field in left_fields
        target_is_left = target_field in left_fields

        log_info(f"入力欄クリック検知: 現在={cur_field}(左列={cur_is_left}) -> 宛先={target_field}(左列={target_is_left}), クリック列={click_col}")

        # 移動開始：即座に移動フラグをONにし、途中のカーソルを非表示にして画面上を走るのを防止（シームレス化）
        self._is_navigating_field = True
        self.textbox.tag_remove("remote_cursor", "1.0", "end")
        # 万が一の通信遅延に備えた安全タイマー（0.8秒後に自動解除）
        self.after(800, lambda: setattr(self, "_is_navigating_field", False))

        def _do_navigate():
            try:
                # 1. フィールド間移動（キーを一括バッチ送信してサーバー側の処理を最速化）
                if cur_field != target_field:
                    # ケースA: 同一列ブロック内の移動（左列同士、または右列同士）
                    if cur_is_left == target_is_left or not right_fields or not left_fields:
                        col_list = left_fields if target_is_left or not right_fields else right_fields
                        c_idx = col_list.index(cur_field) if cur_field in col_list else 0
                        t_idx = col_list.index(target_field)
                        step = t_idx - c_idx
                        if step > 0:
                            self.session.send(KEY_SEQUENCES["Down"] * step)
                        elif step < 0:
                            self.session.send(KEY_SEQUENCES["Up"] * abs(step))

                    # ケースB: 左列から右列への移動
                    elif cur_is_left and not target_is_left:
                        best_left = min(left_fields, key=lambda f: abs(f.row - target_field.row))
                        c_idx = left_fields.index(cur_field)
                        t_idx = left_fields.index(best_left)
                        step = t_idx - c_idx
                        if step > 0:
                            self.session.send(KEY_SEQUENCES["Down"] * step)
                        elif step < 0:
                            self.session.send(KEY_SEQUENCES["Up"] * abs(step))
                        time.sleep(0.02)
                        # Tab (\t) で同一行の右列フィールドへジャンプ
                        self.session.send("\t")
                        time.sleep(0.02)
                        # 目的行と異なる場合、右列内での上下微調整
                        same_row_right = [f for f in right_fields if f.row == target_field.row]
                        if same_row_right and best_left.row != target_field.row:
                            r_cur = min(right_fields, key=lambda f: abs(f.row - best_left.row))
                            r_step = right_fields.index(target_field) - right_fields.index(r_cur)
                            if r_step > 0:
                                self.session.send(KEY_SEQUENCES["Down"] * r_step)
                            elif r_step < 0:
                                self.session.send(KEY_SEQUENCES["Up"] * abs(r_step))

                    # ケースC: 右列から左列への移動
                    elif not cur_is_left and target_is_left:
                        best_right = min(right_fields, key=lambda f: abs(f.row - target_field.row))
                        c_idx = right_fields.index(cur_field)
                        t_idx = right_fields.index(best_right)
                        step = t_idx - c_idx
                        if step > 0:
                            self.session.send(KEY_SEQUENCES["Down"] * step)
                        elif step < 0:
                            self.session.send(KEY_SEQUENCES["Up"] * abs(step))
                        time.sleep(0.02)
                        # Progress 4GL 正規の BACK-TAB (Ctrl-U: \x15) で左列フィールドへジャンプ
                        self.session.send("\x15")
                        time.sleep(0.02)
                        # 目的行と異なる場合、左列内での上下微調整
                        same_row_left = [f for f in left_fields if f.row == target_field.row]
                        if same_row_left and best_right.row != target_field.row:
                            l_cur = min(left_fields, key=lambda f: abs(f.row - best_right.row))
                            l_step = left_fields.index(target_field) - left_fields.index(l_cur)
                            if l_step > 0:
                                self.session.send(KEY_SEQUENCES["Down"] * l_step)
                            elif l_step < 0:
                                self.session.send(KEY_SEQUENCES["Up"] * abs(l_step))

                    # サーバーから目的行への着弾パケットが届くまで待機（最大0.3秒・途中経過の描画を徹底遮断）
                    start_wait = time.time()
                    while time.time() - start_wait < 0.30:
                        cur = getattr(self, "_current_cursor", None)
                        if cur and cur[0] == target_field.row:
                            break
                        time.sleep(0.01)

                # 2. フィールド内での列位置調整（着弾後の実カーソル列 actual_col を参照して安全に一括調整）
                actual_cur = getattr(self, "_current_cursor", None)
                actual_col = actual_cur[1] if actual_cur and actual_cur[0] == target_field.row else target_field.start_col
                col_diff = click_col - actual_col
                if col_diff > 0:
                    max_right = max(0, target_field.end_col - actual_col)
                    steps = min(col_diff, max_right)
                    if steps > 0:
                        self.session.send(KEY_SEQUENCES["Right"] * steps)
                elif col_diff < 0:
                    max_left = max(0, actual_col - target_field.start_col)
                    steps = min(abs(col_diff), max_left)
                    if steps > 0:
                        self.session.send(KEY_SEQUENCES["Left"] * steps)

                # 列調整キーのサーバー応答着弾待機
                if col_diff != 0:
                    start_col_wait = time.time()
                    while time.time() - start_col_wait < 0.15:
                        cur = getattr(self, "_current_cursor", None)
                        if cur and cur[0] == target_field.row and cur[1] == click_col:
                            break
                        time.sleep(0.01)
                else:
                    time.sleep(0.02)

            except Exception as e:
                log_error(f"入力欄ナビゲーションエラー: {e}")
            finally:
                # 途中の画面更新がすべて収束した直後、メインスレッド(GUI)でアトミックに解除＆目的地点灯
                def _on_finish():
                    self._is_navigating_field = False
                    cur = getattr(self, "_current_cursor", None)
                    if cur is not None:
                        r, c = cur
                        self.textbox.tag_remove("remote_cursor", "1.0", "end")
                        self.textbox.tag_add("remote_cursor", f"{r + 1}.{c}", f"{r + 1}.{c + 1}")
                        try:
                            self.textbox._textbox.tag_raise("remote_cursor")
                        except Exception:
                            pass
                    self._reset_cursor_blink()

                self.after(10, _on_finish)

        threading.Thread(target=_do_navigate, daemon=True, name="field-nav").start()
        return "break"

    def _on_panel_resize(self, event):
        if not self.auto_fit or self.closing:
            return
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._apply_auto_fit)

    def _apply_auto_fit(self):
        self._resize_job = None
        if not self.auto_fit or self.closing:
            return

        # 実際の描画テキストウィジェット (_textbox) の実寸を取得
        inner_w = self.textbox._textbox.winfo_width()
        inner_h = self.textbox._textbox.winfo_height()
        if inner_w <= 100 or inner_h <= 100:
            pw = self.terminal_panel.winfo_width()
            ph = self.terminal_panel.winfo_height()
            if pw <= 100 or ph <= 100:
                return
            inner_w = pw - 12
            inner_h = ph - 12

        import tkinter.font as tkfont
        target_cols = getattr(self, "active_cols", 80)
        target_rows = ROWS

        best_size = 12
        best_cw = 9
        best_ch = 18

        # 24行が絶対に1ピクセルも切れることなくスクロールバー不要で収まる最大フォントを探索
        for size in range(36, 11, -1):
            f = tkfont.Font(family=self.terminal_font_family, size=-size)
            cw = f.measure("M")
            ch = f.metrics("linespace")
            if cw * target_cols <= inner_w - 6 and ch * target_rows <= inner_h - 4:
                best_size = size
                best_cw = cw
                best_ch = ch
                break

        # 左右を自動中央揃え（右端文字のクリッピングを防ぐため8pxの安全マージンを確保）
        pad_x = max(2, (inner_w - best_cw * target_cols) // 2 - 8)
        # padyは必ず0に設定（padyを設定するとTkinter仕様により最下行がはみ出して切れるため）
        try:
            self.textbox._textbox.configure(padx=pad_x, pady=0)
            self.textbox._textbox.yview_moveto(0.0)
            self.textbox._textbox.xview_moveto(0.0)
        except Exception:
            pass

        if best_size != self.font_size:
            self.font_size = best_size
            self.terminal_font.configure(size=self.font_size)
            try:
                self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
            except Exception:
                pass
            self._rerender_all()

    def toggle_auto_fit(self):
        self.auto_fit = self.auto_fit_var.get()
        if self.auto_fit:
            self._apply_auto_fit()

    def change_font_size(self, delta=0, reset=False):
        if self.auto_fit:
            self.auto_fit = False
            self.auto_fit_var.set(False)
        self.font_size = 18 if reset else max(10, min(36, self.font_size + delta))
        self.terminal_font.configure(size=self.font_size)
        try:
            self.textbox._textbox.tag_config("bold", font=(self.terminal_font_family, self.font_size, "bold"))
        except Exception:
            pass
        self._rerender_all()

    def disconnect_server(self):
        cur = self.active_tab
        if cur is None or cur.session is None:
            return
        cur.session.stop()
        cur.session = None
        cur.is_connected = False
        if cur.textbox:
            for tag in ("remote_cursor", "reverse", "menu_highlight", "underline", "bold"):
                cur.textbox.tag_remove(tag, "1.0", "end")
        self._set_state("切断済み")
        self._render_tab_buttons()

    def show_help(self):
        messagebox.showinfo(
            "操作ガイド",
            "【Chrome風タブ操作】\n"
            "・Ctrl+T: 新規タブを開いて新しいSSHセッションを開始\n"
            "・Ctrl+W: 現在のタブを閉じる\n"
            "・Ctrl+Tab / Ctrl+Shift+Tab: タブを左右に切り替え\n"
            "・各タブの「✕」ボタンや「＋」ボタンでも直感的に操作可能\n\n"
            "【ログイン・接続】\n"
            "・「ログイン」ボタンまたはメニュー「接続」→「ログイン / 接続」から開始します。\n"
            "・メニューバーの「ログイン情報」からホストやユーザー・パスワードを安全に登録・保存できます。\n\n"
            "【カラーパレット・テーマ】\n"
            "・メニューバーの「カラーパレット」から、専用パレットウィンドウを開いてワンクリックで配色を変更できます。\n"
            "・ライト、ダーク、クラシックグリーン、アンバーの標準テンプレートや、カラーピッカーでの自由な色指定が可能です。\n\n"
            "【画面サイズ・余白調整】\n"
            "・画面サイズに合わせて文字が自動的に最大化され、上下左右中央に綺麗にフィットします（文字切れ防止対応済み）。\n"
            "・「表示」メニューから手動での文字拡大・縮小も行えます。\n\n"
            "【キー操作・ショートカット】\n"
            "・Ctrl+C: 選択範囲（または画面全体）のコピー\n"
            "・Ctrl+V: クリップボードの内容を貼り付け\n"
            "・Ctrl+A: 画面全体の文字を選択\n"
            "・Ctrl+D: 今日の日付を mm/dd/yy 書式で直接貼り付け・入力\n"
            "・Ctrl+E: 画面のデータをCSV化してExcelで開く\n"
            "・Ctrl+H: HOME画面（メインメニュー）に戻る\n"
            "・右側ツールバーおよび「キー送信」メニューから各ファンクションキー（F1〜F4）やEnter等を送信できます。\n"
            "・ターミナル内のTabキーはQADに送信され、Ctrl+Shift+Tabで上部ボタンへフォーカス移動できます。",
            parent=self,
        )

    def on_close(self):
        self.closing = True
        if self.order_panel is not None:
            self.order_panel.close_popups()
        for sequence in ("<KeyPress>", "<KeyRelease>", "<FocusOut>", "<ButtonPress>"):
            self.unbind_class(self._order_bindtag, sequence)
        if getattr(self, "_cursor_blink_job", None) is not None:
            try:
                self.after_cancel(self._cursor_blink_job)
            except Exception:
                pass
            self._cursor_blink_job = None
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        if self.update_job is not None:
            self.after_cancel(self.update_job)
            self.update_job = None
        for tab in getattr(self, "tabs", []):
            if tab.session is not None:
                try:
                    tab.closing = True
                    tab.session.stop()
                except Exception:
                    pass
        self.destroy()


if __name__ == "__main__":
    app = TerminalApp()
    app.mainloop()
