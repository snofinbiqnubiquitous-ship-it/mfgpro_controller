import base64
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
    print(f"\n{'='*70}\n {title} (Cursor: row={screen.cursor.y+1}, col={screen.cursor.x+1})\n{'='*70}", flush=True)
    for y, line in enumerate(screen.display, 1):
        safe_line = "".join([c if ord(c) < 128 or (c.isprintable() and ord(c) != 0xfffd) else "?" for c in line])
        print(f"{y:2d} | {safe_line}", flush=True)

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

# 2. 99.7.1.1 起動
send_keys(b"99.7.1.1\r", 1.0)
wait_pred(lambda t, tl: "order:" in tl)

# 3. Order 欄に SO199396 を入力して Enter
print(">>> Looking up SO199396...", flush=True)
send_keys(b"SO199396\r", 1.2)
print_screen("Step 1 Order Header SO199396")

# 4. F1 でヘッダーを確定して明細画面へ
print(">>> Pressing F1 to advance to line items...", flush=True)
send_keys(KEY_SEQUENCES["F1"], 1.2)
if "space" in get_text().lower():
    send_keys(b" ", 0.6)

# Tax や Salesperson や Comments が出たら通過
for _ in range(6):
    txt = get_text().lower()
    if "tax usage" in txt or "salesperson" in txt:
        send_keys(KEY_SEQUENCES["F1"], 0.8)
    elif "transaction comments" in txt:
        send_keys(KEY_SEQUENCES["F4"], 0.8)
    elif "sales order line" in txt and "transaction comments" not in txt:
        break
    time.sleep(0.3)
    feed(0.1)

print_screen("Step 6.1.0 Line Items Screen")

# 5. Ln 採番 (Enter)
print(">>> Pressing Enter for Ln 1...", flush=True)
send_keys(b"\r", 0.8)
print_screen("After Ln Enter")

# Create WO が出たら F1
if "create wo:" in get_text().lower():
    print(">>> Create WO detected, sending F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Create WO F1")

# Item Number: BW0100D + F1
print(">>> Inputting Item Number: BW0100D + F1...", flush=True)
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After Item Number BW0100D")

# Site: CB2 + F1
if "site" in get_text().lower():
    print(">>> Inputting Site: CB2 + F1...", flush=True)
    send_keys(b"CB2", 0.2)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Site CB2")

# Qty Ordered UM -> F1
txt = get_text().lower()
if "item width(mm):" not in txt:
    print(">>> Skipping Qty Ordered UM with F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Qty Ordered UM F1")

# SL一覧画面
print_screen("SL Menu (Item Width)")

# SL 1 取得: F1 -> Enter -> Enter
print(">>> Acquiring SL 1: F1 -> Enter -> Enter...", flush=True)
send_keys(KEY_SEQUENCES["F1"], 0.8)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
print_screen("Len(m) Active")

# Len(m): 100 + Enter
print(">>> Inputting Length: 100 + Enter...", flush=True)
send_keys(b"100\r", 1.0)
print_screen("Rolls Popup Open")

# Ser: Enter
print(">>> Ser: Enter...", flush=True)
send_keys(b"\r", 0.6)
print_screen("Rolls Active")

# Rolls: 1 + Enter
print(">>> Rolls: 1 + Enter...", flush=True)
send_keys(b"1\r", 0.6)
print_screen("Width Active")

# Width: 200 + Enter
print(">>> Width: 200 + Enter...", flush=True)
send_keys(b"200\r", 0.8)
print_screen("After Width 200 Entered (Next line Ser)")

# ここで何を押すと何が出るか？
print(">>> Pressing F4 to finish rolls...", flush=True)
send_keys(KEY_SEQUENCES["F4"], 1.0)
print_screen("After F4 on Next Ser")

# クリーンアップ (F4 x 6)
for _ in range(6):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()
