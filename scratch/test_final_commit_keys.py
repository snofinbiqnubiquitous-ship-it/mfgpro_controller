import base64
import json
import os
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
        except Exception:
            time.sleep(0.03)

def send_keys(data, wait_after=0.4):
    if isinstance(data, str):
        shell.sendall(data.encode("ascii", errors="replace"))
    else:
        shell.sendall(data)
    feed(wait_after)

def get_text():
    return "\n".join("".join(screen.buffer[y][x].data or " " for x in range(80)).rstrip() for y in range(24))

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
feed(0.5)
send_keys(b"SO199396\r", 1.2)

# Line Items画面へ
for i in range(1, 15):
    txt = get_text().lower()
    if "sales order line" in txt and "transaction comments" not in txt:
        break
    if "press space" in txt or "space bar" in txt:
        send_keys(b" ", 0.4)
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Ln 1 -> Create WO -> Item BW0100D -> Site CB2 -> Qty
send_keys(b"\r", 0.8)
if "create wo:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)
if "site" in get_text().lower():
    send_keys(b"CB2", 0.2)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
if "item width(mm):" not in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# SL 1 -> Len 100 -> Ser -> Rolls 1 -> Width 200 -> F4 -> F1 -> F4 -> F1
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
send_keys(b"100\r", 0.8)
send_keys(b"\r", 0.5)
send_keys(b"1\r", 0.5)
send_keys(b"200\r", 0.8)
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Orig Qty -> F1 -> Pricing Date -> F1 -> List Price -> F1
if "orig order qty:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)
if "pricing date:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Price 150 -> F1 -> Tax F1 -> Comments F4
send_keys(b"150\r", 0.6)
send_keys(KEY_SEQUENCES["F1"], 0.8)
if "tax usage" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)
if "transaction comments" in get_text().lower():
    send_keys(KEY_SEQUENCES["F4"], 0.8)

# Reason Code 入力
txt = get_text().lower()
if "reason code" in txt:
    send_keys(b"70\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# F4 (1st): Item -> Ln
send_keys(KEY_SEQUENCES["F4"], 0.8)
# F4 (2nd): Ln -> Ln Format S/M
send_keys(KEY_SEQUENCES["F4"], 0.8)
# F4 (3rd): Ln Format S/M -> Totals Screen
send_keys(KEY_SEQUENCES["F4"], 1.0)
print_screen("Step 6.3.0 Totals Screen (Waiting for Commit Key)")

# ここで何を押すと注文が保存されるかテスト！
# まず F4 を押してみる
print(">>> Sending F4 on Totals Screen...", flush=True)
send_keys(KEY_SEQUENCES["F4"], 1.0)
print_screen("After F4 on Totals Screen")

txt = get_text().lower()
if "press space" in txt or "space bar" in txt:
    print(">>> Space prompt appeared! Sending Space to complete!", flush=True)
    send_keys(b" ", 1.0)
    print_screen("After Space Key")

# もしまだ残っていたらクリーンアップ
for _ in range(6):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()
