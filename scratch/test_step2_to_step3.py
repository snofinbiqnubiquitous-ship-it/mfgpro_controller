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
    time.sleep(0.5)
    feed(0.1)

print_screen("Main Menu Reached")

# 2. 99.7.1.1 起動
send_keys(b"99.7.1.1\r", 1.5)
for _ in range(10):
    txt = get_text().lower()
    if "order:" in txt and "sales order maintenance" in txt:
        break
    time.sleep(0.5)
    feed(0.1)

print_screen("Step 1 Order Prompt")

# 3. Enter で最新番号自動採番
send_keys(b"\r", 1.5)
for _ in range(10):
    txt = get_text().lower()
    if "sold-to" in txt and ("order date:" in txt or "line pricing:" in txt):
        break
    time.sleep(0.5)
    feed(0.1)

print_screen("Step 1 After Auto Order (Cursor should be on Sold-To)")

# Order ID 抽出
full_txt = get_text()
m = re.search(r'(?:sales\s+order|order):\s*([a-z0-9]+)', full_txt, re.IGNORECASE)
order_id = m.group(1) if m else "UNKNOWN"
print(f"\n★ 採番された Order ID: {order_id}\n")

# 4. Step 2: ヘッダー各項目の順次入力
print(">>> [Step 2] Sold-To: 20000900 + Enter")
send_keys(b"20000900\r", 1.2)
txt = get_text().lower()
if "space" in txt or "continue" in txt or "category=" in txt:
    print(">>> Space bar prompt detected! Sending Space...")
    send_keys(b" ", 0.8)

print_screen("Step 2 After Sold-To and Space")

print(">>> [Step 2] Bill-To: 20000900 + Enter")
send_keys(b"20000900\r", 0.6)
print_screen("Step 2 After Bill-To")

print(">>> [Step 2] Ship-To: 20000907 + Enter")
send_keys(b"20000907\r", 0.8)
print_screen("Step 2 After Ship-To")

print(">>> [Step 2] Order Date: Enter (Keep 09/29/26)")
send_keys(b"\r", 0.4)

print(">>> [Step 2] Required Date: 09/29/26 + Enter")
send_keys(b"09/29/26\r", 0.4)

print(">>> [Step 2] Promise Date: Enter (Skip)")
send_keys(b"\r", 0.4)

print(">>> [Step 2] Due Date: 09/30/26 + Enter")
send_keys(b"09/30/26\r", 0.4)

print(">>> [Step 2] Perform Date: Enter (Skip)")
send_keys(b"\r", 0.4)

print(">>> [Step 2] Pricing Date: Enter (Skip)")
send_keys(b"\r", 0.4)

print(">>> [Step 2] Purchase Order: test + Enter")
send_keys(b"test\r", 0.4)

print(">>> [Step 2] Remarks: test + Enter")
send_keys(b"test\r", 0.8)
print_screen("Step 2 Completed Header Fields")

# 5. ヘッダー確定 <F1>
print(">>> [Step 2] Confirm Header with <F1>...")
send_keys(b"\x1b[OP", 1.5)  # F1 = ESC [ O P
print_screen("After Step 2 Confirm (F1)")

# 6. 次の画面の確認（Tax, Salesperson, etc.）
txt = get_text().lower()
print(f"\n画面検知: tax={'tax' in txt}, salesperson={'salesperson' in txt}, comments={'comments' in txt}, line={'line' in txt}")

# クリーンアップ (F4 x 5)
print("\n>>> Cleaning up (Pressing F4)...")
for _ in range(5):
    send_keys(b"\x1b[OS", 0.5)

client.close()
