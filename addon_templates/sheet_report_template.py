"""雛形: QADレポートを抽出し、汎用GASで指定のスプレッドシート・シートへ書き込むアドオン。

使い方:
  1. このファイルをコピーし、ADDON の id（英小文字・数字・_）と name を変更します。
  2. SPREADSHEET_ID と SHEET_NAME に書き込み先を指定します。
  3. extract にレポートの条件入力（Ctrl+F まで）を書きます。
  4. 「ツール → アドオン → アドオンを追加...」でファイルを選ぶと、データ送信のバーにボタンが出ます。

汎用GASのURLは「ツール → アドオン → シート書き込みGASのURL設定...」で一度だけ設定します。
アドオンごとに別のGASを使う場合は add_sheet_report_button(..., gas_url="https://script.google.com/.../exec") を指定します。
GASはシートの値をすべて消してから、抽出結果を A1 から書き込みます。
"""
from addon_kit import add_sheet_report_button
from qad_report import KEY_CTRL_F, KEY_F1

ADDON = {"id": "sample_inventory_sheet", "name": "在庫をシートへ (サンプル)"}

SPREADSHEET_ID = "ここに書き込み先スプレッドシートのIDを貼り付け"   # URLの /d/ と /edit の間の文字列
SHEET_NAME = "Inventory"


def extract(shell, progress):
    """例: 在庫 99.3.6.1（Prod Line 1FGI）。11_inventory_transmission.py と同じキー列です。"""
    shell.open(width=256, height=60)
    progress("📋 QADメニュー(99.3.6.1)へ移動中...")
    shell.login("Selection:", 10)          # 2 → 環境選択 → 1 → メインメニューを確認
    shell.clear()
    shell.send("99.3.6.1\r")
    shell.pause(1.5)
    shell.clear()
    progress("⚡ 条件 '1fgi' を一括入力中...")
    shell.send("\r" * 8 + "1fgi\r" + "1fgi\r")
    shell.pause(0.3)
    shell.clear()
    shell.send(KEY_F1)                     # Output 欄へ
    shell.pause(0.8)
    shell.clear()
    shell.send("32prn\r")
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_F1)
    shell.pause(0.5)
    shell.send(KEY_CTRL_F)                 # 実行。以降の32prn受信と送信は共通処理が行います


def register(api):
    add_sheet_report_button(
        api, "run", "📄 在庫をシートへ (99.3.6.1)",
        extract=extract, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME, menu="99.3.6.1",
        color="#0F766E", hover_color="#115E59",
    )
