"""Data transmission item: order backlog (99.7.6.20) and sales (99.7.5.11) to GAS.

The two reports run one after another on separate logins: concurrent 32prn
spools collide on the server (751179a).
"""
import datetime
import time

from addon_kit import GAS_BUSY, LEGACY_NAMES, begin_transmission, get_login, receive_rows, run_transmission
from qad_report import KEY_CTRL_F, KEY_F1, ReportShell, send_to_gas_via_browser

ADDON = {"id": "backlog_sales_transmission", "name": "受注残＆売上送信"}
GAS_URL = "https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbxkUsNnoE0mPLRt-6XNwEP4ns9hqSzeWKsu4i_BXSrfcPvdye2rRDp_RBvOLeTvKje-/exec"


def extract_order_backlog(shell, progress):
    shell.open(width=256, height=60)
    shell.login("Selection:", 10)
    shell.clear()
    shell.pause(0.5)
    shell.send("99.7.6.20\r")
    shell.wait_text("Sales Order", timeout=15)
    shell.pause(0.8)
    shell.clear()
    for _ in range(6):
        shell.send("\r")
        shell.pause(0.15)
    shell.send("1fgi\r")
    shell.pause(0.2)
    shell.send("1fgi\r")
    shell.pause(0.2)
    for _ in range(8):
        shell.send("\r")
        shell.pause(0.15)
    shell.send(datetime.date.today().strftime("%m/%d/%y") + "\r")
    shell.pause(0.3)
    shell.send(KEY_F1)
    shell.pause(1.0)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def extract_sales(shell, progress, start_day, end_day):
    shell.open(width=256, height=60)
    shell.login("Selection:", 10)
    shell.clear()
    shell.pause(0.5)
    shell.send("99.7.5.11\r")
    shell.wait_text("Invoice", timeout=15)
    shell.pause(0.8)
    shell.clear()
    for _ in range(4):                   # Invoice(2) + Sales Order(2)
        shell.send("\r")
        shell.pause(0.15)
    shell.send(start_day + "\r")
    shell.pause(0.2)
    shell.send(end_day + "\r")
    shell.pause(0.2)
    for _ in range(10):                  # Customer, Bill-To, Salespsn, Item, Group
        shell.send("\r")
        shell.pause(0.15)
    shell.send("1FGI\r")
    shell.pause(0.2)
    shell.send("1FGI\r")
    shell.pause(0.2)
    for _ in range(3):                   # Site(2) + Include Sample(1)
        shell.send("\r")
        shell.pause(0.15)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.clear()
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)


def register(api, shell_factory=ReportShell, sender=send_to_gas_via_browser, clock=time.monotonic):
    def start():
        login = get_login(api)
        if login is None or not begin_transmission(api):
            return
        api.set_status("🚀 受注残(99.7.6.20)＆売上(99.7.5.11)の32prn抽出を開始します...", "working")
        api.log_info(f"受注残＆売上 GAS送信開始: ユーザー={login[2]}, ホスト={login[0]}")

        def worker():
            today = datetime.date.today()
            sales_range = (today.replace(day=1).strftime("%m/%d/%y"), today.strftime("%m/%d/%y"))
            tasks = (
                ("99.7.6.20", "受注残", "OrderBooking", lambda shell, p: extract_order_backlog(shell, p)),
                ("99.7.5.11", "売上", "Sales", lambda shell, p: extract_sales(shell, p, *sales_range)),
            )
            results = {}
            overall = clock()
            for index, (menu, label, title, procedure) in enumerate(tasks, 1):
                started = clock()
                progress = lambda text, label=label, index=index: api.set_status(f"[{index}/2 {label}] {text}", "working")
                try:
                    progress("🔌 QADサーバーに接続中...")
                    with shell_factory(*login) as shell:
                        procedure(shell, progress)
                        rows, _, _ = receive_rows(shell, progress, "", menu)
                    count = len(rows) - 1
                    elapsed = clock() - started
                    api.log_info(f"[{menu} {label}]: 抽出完了 {count:,}件 ({elapsed:.1f}秒) ➔ 即時GAS送信")
                    payload = {"menu": menu, "title": title, "sender": login[2],
                               "exportedAt": datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"), "data": rows}
                    sender(payload, GAS_URL, title=f"Google Sheets 転送 ({menu} {title})")
                    results[menu] = (label, count, None)
                    api.set_status(f"⚡ [完了速報] {label}({menu}) をGASへ転送完了 ({count:,}件 / {elapsed:.1f}秒)", "working")
                except Exception as exc:
                    api.log_error(f"データ送信 [{menu}] エラー: {exc}", exc_info=True)
                    results[menu] = (label, 0, str(exc))
                    api.set_status(f"⚠️ [{label} {menu}] エラー: {exc}", "error", clear_delay=8)
            total = clock() - overall
            summary = " & ".join(f"{label}: {'失敗' if error else f'{count:,}件'}" for label, count, error in results.values())
            if any(error for _, _, error in results.values()):
                api.set_status(f"⚠️ 受注残＆売上送信完了 (一部エラー): {summary} ({total:.1f}秒)", "error", clear_delay=10)
            else:
                total_count = sum(count for _, count, _ in results.values())
                api.set_status(f"🎉 受注残＆売上の送信が完了しました ({summary} / 計{total_count:,}件 / {total:.1f}秒)", "success", clear_delay=8)
            api.log_info(f"受注残＆売上送信 全完了: {summary} (総所要時間: {total:.1f}秒)")

        run_transmission(api, "backlog-sales", worker)

    api.add_button("run", "⚡ 受注残＆売上 送信 (99.7.6.20 & 99.7.5.11)", start, bar="data", color="#D97706",
                   hover_color="#B45309", busy_group=GAS_BUSY, legacy_label=(LEGACY_NAMES, "parallel"))
    api.register_action("backlog_sales_transmission.run", start)
