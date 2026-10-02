"""Quick menu: OrderBooking report (99.7.6.20) in the active terminal tab.

The key sequence is the one recorded as stable in the terminal log
(2026-09-30). Each stage now stops when its screen cannot be confirmed instead
of typing into an unknown screen.
"""
import datetime
import time

ADDON = {"id": "quick_order_booking", "name": "クイックメニュー: OrderBooking出力"}

KEY_F1 = "\x1bOP"
KEY_F4 = "\x1bOS"
BUSY = "terminal_macro"


def wait_until(predicate, timeout, interval, clock=time.monotonic, sleep=time.sleep):
    end = clock() + timeout
    while clock() < end:
        sleep(interval)
        if predicate():
            return True
    return False


def run_order_booking(api, tab, clock=time.monotonic, sleep=time.sleep):
    """Worker body. Raises RuntimeError when a screen cannot be confirmed."""
    api.set_status("🏠 Step 1/5: HOME画面（メインメニュー）へ復帰中...", "working")
    if not api.is_main_menu():
        for step in range(4):
            if api.is_main_menu():
                break
            api.log_info(f"HOME画面復帰のため F4 送信 (step {step + 1})")
            api.send_to_tab(tab, KEY_F4)
            wait_until(api.is_main_menu, 1.20, 0.05, clock, sleep)
            sleep(0.15)
    if not api.is_main_menu():
        raise RuntimeError("メインメニューへの復帰を確認できないため中止しました。")
    api.log_info("メインメニュー復帰完了")
    sleep(0.3)

    api.set_status("📋 Step 2/5: 99.7.6.20 画面へ移動中...", "working")
    api.log_info("'99.7.6.20\\r' を送信します")
    api.send_to_tab(tab, "99.7.6.20\r")

    def on_report_screen():
        text = api.screen_text().lower()
        return "99.7.6.20" in text or "sales order detail report" in text or "sales order:" in text

    if not wait_until(on_report_screen, 4.0, 0.1, clock, sleep):
        raise RuntimeError("99.7.6.20 の条件入力画面を確認できないため中止しました。")
    api.log_info("99.7.6.20 条件入力画面の表示を確認しました")
    sleep(0.5)

    api.set_status("✏️ Step 3/5: Prod Line('1fgi') & Due Date(今日) を一括入力中...", "working")
    today_str = datetime.date.today().strftime("%m/%d/%y")
    api.log_info(f"本日の日付 = '{today_str}'")
    api.log_info("Part 1 (Sales Order ~ Prod Line) 送信")
    api.send_to_tab(tab, "\r" * 6 + "1fgi\r" + "1fgi\r")
    sleep(0.2)
    api.log_info(f"Part 2 (Site ~ Due Date: {today_str}) 送信")
    api.send_to_tab(tab, "\r" * 8 + today_str)
    sleep(0.35)

    api.set_status("⚡ Step 4/5: F1 を押して Output 欄へジャンプ中...", "working")
    api.log_info("F1 を送信して Output 欄へジャンプ")
    api.send_to_tab(tab, KEY_F1)
    if not wait_until(api.is_cursor_at_output_field, 2.5, 0.1, clock, sleep):
        raise RuntimeError("Output 欄への移動を確認できないため、32prn を入力せずに中止しました。")
    api.log_info("Output 欄への着弾を確認しました")
    sleep(0.35)

    api.set_status("🖨️ Step 5/5: Output に '32prn' を設定し、ストリーム受信・Excel展開を開始...", "working")
    api.log_info("input_32printer を起動して自動実行・ストリーム直接受信・Excel展開を開始")
    api.start_32printer(tab)


def register(api):
    def start():
        if not api.is_connected():
            api.set_status("❌ サーバーに接続されていません", "error", clear_delay=4)
            return
        if api.is_report_busy():
            api.set_status("❌ 現在別のレポート処理が実行中です。完了までお待ちください。", "error", clear_delay=4)
            return
        if not api.try_acquire(BUSY):
            api.set_status("❌ OrderBooking 出力を実行中です。完了までお待ちください。", "error", clear_delay=4)
            return
        tab = api.active_tab()
        api.log_info("=== OrderBooking 自動実行マクロ開始（改セル一括貼り付け方式） ===")
        api.set_status("🚀 OrderBooking 自動実行を開始します...", "working")

        def worker():
            try:
                run_order_booking(api, tab)
            except Exception as exc:
                api.log_error(f"OrderBooking 自動実行エラー: {exc}", exc_info=True)
                api.set_status(f"❌ OrderBooking 自動実行エラー: {exc}", "error", clear_delay=8)
            finally:
                api.release(BUSY)

        api.run_in_background(worker, "order-booking")

    api.add_button("order_booking", "⚡ OrderBooking出力 (99.7.6.20)", start, bar="quick",
                   color="#2563EB", hover_color="#1D4ED8", requires_connection=True)
    api.register_action("order_booking.run", start)
