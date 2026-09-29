import base64
import json
import logging
import os
import re
import socket
import sys
import time
from datetime import date
from pathlib import Path

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
sys.path.insert(0, str(repo_dir))

import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

host = cfg["host"]
port = cfg.get("port", 22)
user = cfg["user"]
password = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port=port, username=user, password=password, timeout=12)

shell = ssh.invoke_shell(term="vt100", width=COLS, height=ROWS)
shell.settimeout(0.08)

screen = pyte.Screen(COLS, ROWS)
stream = pyte.ByteStream(screen)

def feed(wait_sec=0.4):
    start = time.time()
    while time.time() - start < wait_sec:
        try:
            chunk = shell.recv(65536)
            if chunk:
                stream.feed(chunk)
        except socket.timeout:
            time.sleep(0.03)

def send_keys(data, wait_after=0.4):
    if isinstance(data, str):
        shell.sendall(data.encode("ascii", errors="replace"))
    else:
        shell.sendall(data)
    feed(wait_after)

def get_text():
    return "\n".join("".join(screen.buffer[y][x].data or " " for x in range(80)).rstrip() for y in range(24))

def wait_pred(pred, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        feed(0.1)
        txt = get_text()
        if pred(txt, txt.lower()):
            return True
        if "press space" in txt.lower() or "space bar" in txt.lower():
            send_keys(b" ", 0.4)
    return False

def print_screen(title=""):
    print(f"\n{'='*70}\n {title} (Cursor: row={screen.cursor.y+1}, col={screen.cursor.x+1})\n{'='*70}")
    for y, line in enumerate(screen.display, 1):
        safe_line = "".join([c if ord(c) < 128 or c.isprintable() else "?" for c in line])
        print(f"{y:2d} | {safe_line}")

# 1. ログイン
feed(1.0)
send_keys(b"2\r", 0.8)
send_keys(b"1\r", 0.8)
send_keys(b"\r\r", 0.8)
for _ in range(15):
    txt = get_text().lower()
    if "mfmenu" in txt and "main menu" in txt:
        if "please confirm exit" in txt:
            send_keys(b"n\r", 0.5)
            continue
        break
    if "space" in txt or "continue" in txt:
        send_keys(b" ", 0.4)
    time.sleep(0.3)

# 2. 99.7.1.1
send_keys(b"99.7.1.1\r", 1.0)
wait_pred(lambda t, tl: "order:" in tl)

# 3. Enter 自動採番
send_keys(b"\r", 1.0)
wait_pred(lambda t, tl: "sold-to" in tl)

# 4. ヘッダー
send_keys(b"20000900\r", 1.2)
txt = get_text().lower()
if "space" in txt or "continue" in txt or "category=" in txt:
    send_keys(b" ", 0.6)

send_keys(b"20000900\r", 0.4)
send_keys(b"20000904\r", 0.6)
send_keys(b"\r", 0.3)          # Order Date
send_keys(b"09/29/26\r", 0.3)  # Req Date
send_keys(b"\r", 0.3)          # Promise Date
send_keys(b"09/30/26\r", 0.3)  # Due Date
send_keys(b"\r", 0.3)          # Perform Date
send_keys(b"\r", 0.3)          # Pricing Date
send_keys(b"test\r", 0.3)      # PO
send_keys(b"test\r", 0.6)      # Remarks

# F1 確定
send_keys(KEY_SEQUENCES["F1"], 1.0)
if "space" in get_text().lower():
    send_keys(b" ", 0.6)

# Step 3 Tax
wait_pred(lambda t, tl: "tax usage:" in tl or "salesperson 1:" in tl)
if "tax usage:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Step 4 Salesperson
wait_pred(lambda t, tl: "salesperson 1:" in tl or "transaction comments" in tl or "sales order line" in tl)
if "salesperson 1:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Step 5 Comments
wait_pred(lambda t, tl: "transaction comments" in tl or "sales order line" in tl)
if "transaction comments" in get_text().lower():
    send_keys(KEY_SEQUENCES["F4"], 1.0)

# Step 6.1.0 明細
wait_pred(lambda t, tl: "sales order line" in tl and "transaction comments" not in tl)
send_keys(b"\r", 0.8)  # Ln 採番

# Create WO
wait_pred(lambda t, tl: "create wo:" in tl)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Item Number
wait_pred(lambda t, tl: "create wo:" not in tl and "sales order line" in tl)
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Site
wait_pred(lambda t, tl: "site" in tl)
send_keys(b"CB2", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Qty Ordered UM -> F1
wait_pred(lambda t, tl: "item width(mm):" in tl or "avail. to allocate" in tl)
if "item width(mm):" not in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# SL一覧画面到達
wait_pred(lambda t, tl: "item width(mm):" in tl)
print_screen("Step 6.1.4 SL一覧画面")

# F1 送信 (SL 1 取得)
print("\n>>> Sending F1 to acquire SL 1...")
send_keys(KEY_SEQUENCES["F1"], 1.0)
print_screen("After F1 (SL 1 acquired)")

# ここで何が起きるか？ Enter を押してみる
print("\n>>> Sending Enter #1...")
send_keys(b"\r", 0.8)
print_screen("After Enter #1")

# もう一度 Enter を押してみる
print("\n>>> Sending Enter #2...")
send_keys(b"\r", 0.8)
print_screen("After Enter #2")

# クリーンアップ (F4 x 6)
print("\n>>> Cleaning up (Pressing F4)...")
for _ in range(6):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()
