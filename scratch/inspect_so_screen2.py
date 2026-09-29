import base64
import json
import logging
import os
import socket
import sys
import time

repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

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

def run():
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
    shell.sendall(b"2\r")
    feed_available(1.0)
    shell.sendall(b"1\r")
    feed_available(1.0)
    shell.sendall(b"\r\r")
    feed_available(1.0)

    for _ in range(10):
        feed_available(0.8)
        text = "\n".join("".join(screen.buffer[y][x].data for x in range(80)) for y in range(24)).lower()
        if "mfmenu" in text and "main menu" in text:
            break
        shell.sendall(b" ")

    shell.sendall(b"99.7.1.1\r")
    feed_available(2.0)

    # Order 入力
    shell.sendall(b"SO199302")
    feed_available(0.8)

    # F1
    shell.sendall(KEY_SEQUENCES["F1"].encode("ascii"))
    feed_available(2.0)

    # F1
    shell.sendall(KEY_SEQUENCES["F1"].encode("ascii"))
    feed_available(1.5)

    log_screens = []
    log_screens.append(dump_screen(screen, "01_BEFORE_SPACE"))

    # スペースキーを送信
    shell.sendall(b" ")
    feed_available(2.0)

    log_screens.append(dump_screen(screen, "02_AFTER_SPACE_LINE_ITEMS"))

    # もう1回 F1 や Enter、Space でどうなるか確認
    # もしさらにメッセージがあるか、明細画面になっているか
    text2 = "\n".join("".join(screen.buffer[y][x].data for x in range(80)) for y in range(24)).lower()
    if "press space" in text2:
        shell.sendall(b" ")
        feed_available(1.5)
        log_screens.append(dump_screen(screen, "03_AFTER_SECOND_SPACE"))

    # 安全脱出: F4 を複数回送信
    for _ in range(6):
        shell.sendall(KEY_SEQUENCES["F4"].encode("ascii"))
        feed_available(0.5)

    log_screens.append(dump_screen(screen, "04_SAFE_EXIT"))

    shell.close()
    ssh.close()

    log_file_path = os.path.join(repo_dir, "scratch", "so_screen_inspection_lines.log")
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(log_screens))
    print("Done. Saved to:", log_file_path)

if __name__ == "__main__":
    run()
