import os
import sys
import time
import socket
import json
import base64
from pathlib import Path
from datetime import date
import paramiko
import pyte
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

HOST = cfg["host"]
PORT = cfg.get("port", 22)
USER = cfg["user"]
PASS = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=PORT, username=USER, password=PASS)

channel = client.invoke_shell(term="vt100", width=80, height=24)
channel.setblocking(False)

screen = pyte.Screen(80, 24)
stream = pyte.ByteStream(screen)

def feed(wait=0.2):
    time.sleep(wait)
    chunks = []
    while True:
        try:
            data = channel.recv(4096)
            if not data:
                break
            chunks.append(data)
            stream.feed(data)
        except (socket.error, paramiko.SSHException):
            break
    return b"".join(chunks)

def send_keys(data, wait_after=0.4):
    channel.send(data)
    return feed(wait_after)

def get_text():
    return "\n".join("".join(screen.display[y]) for y in range(24))

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
        send_keys(b" ", 0.5)
    time.sleep(0.3)
    feed(0.1)

# 2. 99.7.1.1 起動
send_keys(b"99.7.1.1\r", 1.5)
for _ in range(10):
    if "order:" in get_text().lower():
        break
    time.sleep(0.3)
    feed(0.1)

# 3. Enter で採番
send_keys(b"\r", 1.2)
for _ in range(10):
    if "sold-to" in get_text().lower():
        break
    time.sleep(0.3)
    feed(0.1)

# 4. ヘッダー入力
send_keys(b"20000900\r", 1.2)
txt = get_text().lower()
if "space" in txt or "continue" in txt or "category=" in txt:
    send_keys(b" ", 0.8)

send_keys(b"20000900\r", 0.5)
send_keys(b"20000904\r", 0.6)
send_keys(b"\r", 0.3)          # Order Date
send_keys(b"09/29/26\r", 0.3)  # Req Date
send_keys(b"\r", 0.3)          # Promise Date
send_keys(b"09/30/26\r", 0.3)  # Due Date
send_keys(b"\r", 0.3)          # Perform Date
send_keys(b"\r", 0.3)          # Pricing Date
send_keys(b"test\r", 0.3)      # PO
send_keys(b"test\r", 0.6)      # Remarks

# F1 (ヘッダー確定)
send_keys(b"\x1b[OP", 1.2)
if "space" in get_text().lower():
    send_keys(b" ", 0.6)

# Step 3 Tax ポップアップ -> F1
for _ in range(10):
    txt = get_text().lower()
    if "tax usage:" in txt or "tax environment:" in txt:
        send_keys(b"\x1b[OP", 0.8)
        break
    time.sleep(0.3)
    feed(0.1)

# Step 4 Salesperson -> F1
for _ in range(10):
    txt = get_text().lower()
    if "salesperson 1:" in txt:
        send_keys(b"\x1b[OP", 0.8)
        break
    time.sleep(0.3)
    feed(0.1)

# Step 5 Comments -> F4
for _ in range(10):
    txt = get_text().lower()
    if "transaction comments" in txt:
        send_keys(b"\x1b[OS", 1.0)
        break
    time.sleep(0.3)
    feed(0.1)

# Step 6.1.0 明細メイン画面待機
for _ in range(10):
    if "sales order line" in get_text().lower() and "transaction comments" not in get_text().lower():
        break
    time.sleep(0.3)
    feed(0.1)

print_screen("Step 6.1.0 Line Main Screen")

# 6.1.0 Ln 自動採番 (Enter)
send_keys(b"\r", 0.8)

# 6.1.1 Create WO -> F1
for _ in range(10):
    if "create wo:" in get_text().lower():
        send_keys(b"\x1b[OP", 0.8)
        break
    time.sleep(0.3)
    feed(0.1)

# 6.1.3 Item Number 入力 (BW0100D + F1)
for _ in range(10):
    if "item number" in get_text().lower() and "create wo:" not in get_text().lower():
        break
    time.sleep(0.3)
    feed(0.1)

print_screen("Step 6.1.3 Item Number Active")
send_keys(b"BW0100D", 0.2)
send_keys(b"\x1b[OP", 0.8)

# 6.1.3 Site 入力 (CB2 + F1)
for _ in range(10):
    if "site" in get_text().lower():
        break
    time.sleep(0.3)
    feed(0.1)

print_screen("Step 6.1.3 Site Active")
send_keys(b"CB2", 0.2)
send_keys(b"\x1b[OP", 0.8)

# 6.1.4 Qty Ordered UM -> F1
for _ in range(10):
    txt = get_text().lower()
    if "item width(mm):" in txt or "total qty (m2)" in txt:
        break
    if "avail. to allocate" in txt or "on hand:" in txt:
        send_keys(b"\x1b[OP", 0.8)
        break
    time.sleep(0.3)
    feed(0.1)

print_screen("Step 6.1.4 Slit List (Item Width)")

# サブライン SL 1 採番 (F1)
print("\n>>> Sending F1 to acquire SL 1...")
send_keys(b"\x1b[OP", 1.0)
print_screen("After F1 (SL 1 Acquired)")

# ここでカーソルがどこにあるか？ Enter を押したらどこへ行くか？
print("\n>>> Pressing Enter #1...")
send_keys(b"\r", 0.8)
print_screen("After Enter #1")

print("\n>>> Pressing Enter #2...")
send_keys(b"\r", 0.8)
print_screen("After Enter #2")

# クリーンアップ (F4 x 5)
print("\n>>> Cleaning up (Pressing F4)...")
for _ in range(6):
    send_keys(b"\x1b[OS", 0.5)

client.close()
