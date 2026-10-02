"""Shared helpers for add-ons that extract a QAD report and forward it to GAS.

Add-ons using these helpers can be added or removed independently. They share
the busy group GAS_BUSY so only one transmission runs at a time.
"""
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
