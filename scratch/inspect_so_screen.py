import base64
import json
import logging
import os
import re
import socket
import sys
import time

repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

# --- ログ設定 ---
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("SO_Inspector")

# --- 接続情報読込 ---
with open(os.path.join(repo_dir, "terminal_config.json"), "r", encoding="utf-8") as f:
    cfg = json.load(f)

host = cfg["host"]
port = cfg.get("port", 22)
user = cfg["user"]
password = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

def dump_screen(screen, title="SCREEN"):
    lines = []
    lines.append("=" * 80)
    lines.append(f" {title} (Cursor: row={screen.cursor.y + 1}, col={screen.cursor.x + 1})")
    lines.append("=" * 80)
    for y in range(24):
        row_chars = []
        for x in range(80):
            char_data = screen.buffer[y][x].data
            row_chars.append(char_data if char_data else " ")
        row_str = "".join(row_chars).rstrip()
        lines.append(f"{y + 1:2d} | {row_str}")
    lines.append("=" * 80)
    return "\n".join(lines)

def run_inspection():
    logger.info("1. SSH接続開始...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=10)

    shell = ssh.invoke_shell(term="vt100", width=COLS, height=ROWS)
    shell.settimeout(0.1)

    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)

    def feed_available(wait_sec=1.0):
        start = time.time()
        while time.time() - start < wait_sec:
            try:
                chunk = shell.recv(65536)
                if chunk:
                    stream.feed(chunk)
            except socket.timeout:
                time.sleep(0.05)

    feed_available(1.5)

    # 自動ログイン
    logger.info("2. 自動ログイン中 (2 -> 1 -> Enter x 2)...")
    shell.sendall(b"2\r")
    feed_available(1.0)
    shell.sendall(b"1\r")
    feed_available(1.0)
    shell.sendall(b"\r\r")
    feed_available(1.0)

    # Main Menu待機
    logger.info("3. Main Menu 到達待機中...")
    for _ in range(10):
        feed_available(0.8)
        text = "\n".join("".join(screen.buffer[y][x].data for x in range(80)) for y in range(24)).lower()
        if "mfmenu" in text and "main menu" in text:
            logger.info("Main Menu 着弾確認！")
            break
        if any(k in text for k in ["space", "press spacebar", "continue", "program information"]):
            shell.sendall(b" ")
            feed_available(0.6)
            continue
        shell.sendall(b" ")

    log_screens = []
    log_screens.append(dump_screen(screen, "01_MAIN_MENU"))

    # 99.7.1.1 へジャンプ
    logger.info("4. 99.7.1.1 (SO作成) へ遷移中...")
    shell.sendall(b"99.7.1.1\r")
    feed_available(2.0)

    # Screen 1: SO作成 初期画面
    s1_text = dump_screen(screen, "02_SO_INITIAL_SCREEN")
    log_screens.append(s1_text)
    logger.info("Screen 1 取得完了")

    # ユーザー指示の安全ルール確認:
    # "ただし、99.7.1.1のOrderがnullの時F1を押すとサーバーで新たなOrder IDが作られてしまうので、
    #  Orderがnulの状態ではEnter、もしくはF1を押して先に進まず、Order:'SO199302'を使用して構造の特定を試みてください"
    logger.info("5. Order 欄に 'SO199302' を入力 (空での Enter / F1 は絶対に押しません)...")
    # 入力欄に SO199302 を送信
    shell.sendall(b"SO199302")
    feed_available(0.8)

    s1_typed = dump_screen(screen, "03_SO_TYPED_ORDER")
    log_screens.append(s1_typed)

    # 次に進むため F1 (実行) を送信
    logger.info("6. F1 を送信して既存オーダー SO199302 の詳細画面へ遷移...")
    shell.sendall(KEY_SEQUENCES["F1"].encode("ascii"))
    feed_available(2.0)

    # Screen 2: 詳細画面（ヘッダー画面など）
    s2_text = dump_screen(screen, "04_SO_ORDER_DETAILS_SCREEN")
    log_screens.append(s2_text)
    logger.info("Screen 2 取得完了")

    # さらに F1 または Enter でどうなるか確認（安全のため F1 を1回試行）
    logger.info("7. 次の画面/明細画面を確認するため F1 を送信...")
    shell.sendall(KEY_SEQUENCES["F1"].encode("ascii"))
    feed_available(2.0)

    s3_text = dump_screen(screen, "05_SO_NEXT_SCREEN")
    log_screens.append(s3_text)
    logger.info("Screen 3 取得完了")

    # 安全脱出: 何も保存せず F4 を連打して Main Menu に安全復帰
    logger.info("8. 安全脱出処理 (F4 を連打して保存せずに戻る)...")
    for _ in range(5):
        shell.sendall(KEY_SEQUENCES["F4"].encode("ascii"))
        feed_available(0.5)

    s_exit = dump_screen(screen, "06_AFTER_EXIT_TO_MENU")
    log_screens.append(s_exit)
    logger.info("Main Menu への安全復帰を確認")

    shell.close()
    ssh.close()

    # ログファイルに保存
    log_file_path = os.path.join(repo_dir, "scratch", "so_screen_inspection.log")
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(log_screens))
    logger.info(f"調査ログ保存完了: {log_file_path}")

if __name__ == "__main__":
    try:
        run_inspection()
    except Exception as e:
        logger.error(f"調査実行中エラー: {e}", exc_info=True)
