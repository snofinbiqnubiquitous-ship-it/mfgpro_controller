import os
import sys
import time
import socket
import json
import base64
from pathlib import Path
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

# 4. Sold-To に 20000900 を入力して Enter
print("\n>>> Inputting Sold-To: 20000900 + Enter")
send_keys(b"20000900\r", 1.5)
print_screen("Step 2 After Sold-To Entered")

# 5. その後、何もしないで Enter を 1 回ずつ押してカーソルがどの行・列に移動するかを10回観察
for step in range(1, 12):
    print(f"\n>>> Step 2 Field {step}: Pressing Enter...")
    send_keys(b"\r", 0.8)
    print_screen(f"Step 2 Field {step} after Enter")
    txt = get_text().lower()
    if "tax usage" in txt or "salesperson" in txt:
        print(f"!!! Reached next popup/screen at field {step} !!!")
        break

# クリーンアップ (F4 x 5)
print("\n>>> Cleaning up (Pressing F4)...")
for _ in range(5):
    send_keys(b"\x1b[OS", 0.5)

client.close()
