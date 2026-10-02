"""Data transmission item: inventory report (99.3.6.1, Prod Line 1FGI) to GAS."""
import time

from addon_kit import GAS_BUSY, LEGACY_NAMES, begin_transmission, get_login, receive_rows, run_transmission
from qad_report import KEY_CTRL_F, KEY_F1, ReportShell, send_to_gas_via_browser

ADDON = {"id": "inventory_transmission", "name": "在庫送信"}
GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbwS6dZ9umUKP71NGieiW_tDffygGtAFHKOAxyAo7cWDe3T_xMxlISSdmXoNlK6TaENfkA/exec"


def extract(shell, progress):
    """Key sequence and waits unchanged from the version recorded as working."""
    shell.open(width=256, height=60)
    progress("📋 [2/5] QADメニュー(99.3.6.1)へ移動中...")
    shell.login("Selection:", 10)
    shell.clear()
    shell.send("99.3.6.1\r")
    shell.pause(1.5)
    shell.clear()
    progress("⚡ [3/5] 条件 '1fgi' を一括貼り付け入力中...")
    shell.send("\r" * 8 + "1fgi\r" + "1fgi\r")
    shell.pause(0.3)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.8)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def register(api, shell_factory=ReportShell, sender=send_to_gas_via_browser, clock=time.monotonic):
    def start():
        login = get_login(api)
        if login is None or not begin_transmission(api):
            return
        api.set_status("🚀 在庫レポート抽出＆GAS送信を開始します...", "working")
        api.log_info(f"在庫レポートGAS送信開始: ユーザー={login[2]}, ホスト={login[0]}")
        progress = lambda text: api.set_status(text, "working")

        def worker():
            try:
                progress("🔌 [1/5] QADサーバーに接続中...")
                with shell_factory(*login) as shell:
                    extract(shell, progress)
                    rows, elapsed, size = receive_rows(shell, progress, "[4/5]")
                count = len(rows) - 1
                progress(f"🚀 [5/5] ブラウザを起動しGASへ送信中 ({count:,}件 / {size / 1024:.0f} KB / {elapsed:.1f}秒)...")
                sender(rows, GAS_URL, title="Google Sheets 自動転送 (在庫レポート 1FGI)")
                api.set_status(f"✅ 在庫レポートをGASへ転送完了 ({count:,}件)", "success", clear_delay=8)
                api.log_info(f"在庫レポートGAS送信完了: {count:,}件")
            except Exception as exc:
                api.log_error(f"在庫レポートGAS送信エラー: {exc}", exc_info=True)
                api.set_status(f"❌ 在庫レポートGAS送信エラー: {exc}", "error", clear_delay=10)
                api.show_error("エラー", f"在庫レポートの処理中にエラーが発生しました:\n\n{exc}")

        run_transmission(api, "inventory", worker)

    api.add_button("run", "📦 在庫レポートGAS送信 (99.3.6.1)", start, bar="data", color="#059669",
                   hover_color="#047857", busy_group=GAS_BUSY, legacy_label=(LEGACY_NAMES, "inventory"))
    api.register_action("inventory_transmission.run", start)
