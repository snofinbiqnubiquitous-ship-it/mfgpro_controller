"""Shared helpers for add-ons that extract a QAD report and forward it to GAS.

The existing items keep their own GAS web apps (fixed URL per add-on). New items
can use the generic GAS through add_sheet_report_button: the add-on chooses
spreadsheetId and sheetName. All share the busy group GAS_BUSY so only one
transmission runs at a time.
"""
import re

from addon_host import SHEET_WRITER_URL_KEY
from qad_report import ReportShell, send_to_gas_via_browser

GAS_BUSY = "gas_transmission"
LEGACY_NAMES = "data_transmission_names"


def get_login(api, parent=None):
    """Return (host, port, user, password) or show an error and return None."""
    host, port, user, password = api.qad_credentials()
    if not user or not password:
        api.show_error("ログイン情報未設定",
                       "QADのログイン情報が設定されていません。\nメニューの「ログイン情報」からユーザーIDとパスワードを設定してください。",
                       parent)
        return None
    return host, port, user, password


def begin_transmission(api, parent=None):
    if api.begin_busy(GAS_BUSY):
        return True
    api.show_warning("データ送信実行中", "現在データ送信処理が実行中です。完了するまでお待ちください。", parent)
    return False


def run_transmission(api, name, worker):
    """Run worker in the background and always release the busy group."""
    def body():
        try:
            worker()
        finally:
            api.end_busy(GAS_BUSY)
    api.run_in_background(body, name)


def receive_rows(shell, progress, step="", menu=""):
    """Receive the 32prn stream and return (rows, seconds, bytes); stop on zero rows."""
    lead = f"{step} " if step else ""

    def on_progress(stage, elapsed):
        if stage == "capturing":
            progress(f"📥 {lead}圧縮データを受信中...")
        else:
            progress(f"⏳ {lead}サーバーでクエリ実行中... ({elapsed}秒経過)")

    progress(f"⏳ {lead}32prn 圧縮ストリームを受信中...")
    rows, elapsed, size = shell.receive_rows(300, on_progress)
    if len(rows) <= 1:
        prefix = f"{menu}: " if menu else ""
        raise ValueError(f"{prefix}抽出結果が0件でした。条件に一致するデータが存在しないか、レポート解析に失敗しました。")
    return rows, elapsed, size


# ---------------------------------------------------------------------------
# Generic sheet writer (one GAS web app; each add-on chooses the destination)
# ---------------------------------------------------------------------------
SPREADSHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{25,}$")
GAS_URL_RE = re.compile(r"^https://script\.google\.com/\S+/exec$")
SHEET_WRITER_URL_MISSING = ("シート書き込み用GASのURLが未設定です。\n"
                            "「ツール → アドオン → シート書き込みGASのURL設定...」から設定してください。")


def check_destination(spreadsheet_id, sheet_name):
    """Validate the destination written in an add-on (raises ValueError)."""
    if not SPREADSHEET_ID_RE.match(str(spreadsheet_id or "")):
        raise ValueError(f"SPREADSHEET_ID が正しくありません: {spreadsheet_id!r}")
    if not str(sheet_name or "").strip():
        raise ValueError("SHEET_NAME が指定されていません。")


def sheet_writer_url(api, gas_url=None):
    """Return the generic GAS URL (add-on value first, then the terminal setting) or None."""
    url = str(gas_url or api.config_get(SHEET_WRITER_URL_KEY, "") or "").strip()
    return url if GAS_URL_RE.match(url) else None


def sheet_payload(rows, spreadsheet_id, sheet_name, menu=""):
    """Request body for the generic GAS: spreadsheetId, sheetName and data."""
    check_destination(spreadsheet_id, sheet_name)
    payload = {"spreadsheetId": spreadsheet_id, "sheetName": str(sheet_name).strip(), "data": rows}
    if menu:
        payload["menu"] = menu   # ignored by GAS; used for the temporary file name
    return payload


def send_rows_to_sheet(api, rows, spreadsheet_id, sheet_name, *, menu="", gas_url=None, title=None,
                       sender=send_to_gas_via_browser):
    """Forward rows to the generic GAS, which clears the sheet and writes them."""
    url = sheet_writer_url(api, gas_url)
    if url is None:
        raise ValueError(SHEET_WRITER_URL_MISSING)
    payload = sheet_payload(rows, spreadsheet_id, sheet_name, menu)
    sender(payload, url, title=title or f"Google Sheets 転送 ({payload['sheetName']})")


def add_sheet_report_button(api, button_id, label, *, extract, spreadsheet_id, sheet_name, menu="",
                            color="#0F766E", hover_color="#115E59", gas_url=None,
                            shell_factory=ReportShell, sender=send_to_gas_via_browser):
    """Register a data button: QAD report -> 32prn -> generic GAS -> spreadsheet/sheet.

    extract(shell, progress) opens the shell (shell.open(width, height)), logs in and
    types the report conditions up to Ctrl+F, exactly as the existing add-ons do.
    """
    check_destination(spreadsheet_id, sheet_name)   # a wrong value shows as a load error
    title = f"{label.strip()}"

    def start():
        if sheet_writer_url(api, gas_url) is None:
            api.show_error("送信先未設定", SHEET_WRITER_URL_MISSING)
            return
        login = get_login(api)
        if login is None or not begin_transmission(api):
            return
        api.set_status(f"🚀 {title} を開始します...", "working")
        api.log_info(f"{title} 開始: ユーザー={login[2]}, ホスト={login[0]}, 送信先シート={sheet_name}")
        progress = lambda text: api.set_status(f"[{title}] {text}", "working")

        def worker():
            try:
                progress("🔌 QADサーバーに接続中...")
                with shell_factory(*login) as shell:
                    extract(shell, progress)
                    rows, elapsed, size = receive_rows(shell, progress, "", menu)
                count = len(rows) - 1
                progress(f"🚀 GASへ送信中 ({count:,}件 / {size / 1024:.0f} KB / {elapsed:.1f}秒)...")
                send_rows_to_sheet(api, rows, spreadsheet_id, sheet_name, menu=menu, gas_url=gas_url,
                                   title=f"Google Sheets 転送 ({title} → {sheet_name})", sender=sender)
                api.set_status(f"✅ {title}: シート「{sheet_name}」へ転送完了 ({count:,}件)", "success", clear_delay=8)
                api.log_info(f"{title} 完了: {count:,}件 → {sheet_name}")
            except Exception as exc:
                api.log_error(f"{title} エラー: {exc}", exc_info=True)
                api.set_status(f"❌ {title} エラー: {exc}", "error", clear_delay=10)
                api.show_error("エラー", f"{title} の処理中にエラーが発生しました:\n\n{exc}")

        run_transmission(api, f"sheet-{button_id}", worker)

    handle = api.add_button(button_id, label, start, bar="data", color=color, hover_color=hover_color,
                            busy_group=GAS_BUSY)
    api.register_action(f"{api.id}.{button_id}", start)
    return handle
