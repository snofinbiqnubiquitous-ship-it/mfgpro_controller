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

# 3. SO199396 ロード
print(">>> Lookup SO199396", flush=True)
send_keys(b"SO199396\r", 1.2)

# 4. Sales Order Line 画面まで F1 で進む
for i in range(1, 15):
    txt = get_text().lower()
    if "sales order line" in txt and "transaction comments" not in txt:
        print(">>> At Sales Order Line screen!", flush=True)
        break
    if "press space" in txt or "space bar" in txt:
        send_keys(b" ", 0.4)
    send_keys(KEY_SEQUENCES["F1"], 0.8)

print_screen("01_AT_LINE_ITEMS_SCREEN")

# 5. Ln 1 (Enter)
print(">>> Sending Enter for Ln 1...", flush=True)
send_keys(b"\r", 0.8)
print_screen("02_AFTER_LN_ENTER")

if "create wo:" in get_text().lower():
    print(">>> Create WO popup, sending F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("03_AFTER_CREATE_WO")

# Item Number: BW0100D + F1
print(">>> Item Number BW0100D + F1...", flush=True)
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("04_AFTER_ITEM_INPUT")

if "site" in get_text().lower():
    print(">>> Site CB2 + F1...", flush=True)
    send_keys(b"CB2", 0.2)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("05_AFTER_SITE_INPUT")

# Qty Ordered UM -> F1
if "item width(mm):" not in get_text().lower():
    print(">>> Qty Ordered UM -> F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("06_AFTER_QTY_ORDERED")

print_screen("07_SLIT_MENU")

# SL 1: F1 -> Enter -> Enter
print(">>> SL 1: F1 -> Enter -> Enter...", flush=True)
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
print_screen("08_LEN_PROMPT")

# Len: 100 + Enter
print(">>> Len: 100 + Enter...", flush=True)
send_keys(b"100\r", 0.8)
print_screen("09_ROLL_POPUP")

# Ser: Enter
print(">>> Ser: Enter...", flush=True)
send_keys(b"\r", 0.5)
# Rolls: 1 + Enter
print(">>> Rolls: 1 + Enter...", flush=True)
send_keys(b"1\r", 0.5)
# Width: 200 + Enter
print(">>> Width: 200 + Enter...", flush=True)
send_keys(b"200\r", 0.8)
print_screen("10_AFTER_WIDTH_INPUT")

# Rolls 終了: F4
print(">>> Rolls finish: F4...", flush=True)
send_keys(KEY_SEQUENCES["F4"], 0.8)
print_screen("11_AFTER_ROLLS_F4")

# Please confirm update yes -> F1
if "confirm update" in get_text().lower():
    print(">>> Confirm update 1: F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("12_AFTER_CONFIRM_1")

# SL 終了: F4
print(">>> SL finish: F4...", flush=True)
send_keys(KEY_SEQUENCES["F4"], 0.8)
print_screen("13_AFTER_SL_F4")

# Please confirm update yes -> F1
if "confirm update" in get_text().lower():
    print(">>> Confirm update 2: F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("14_AFTER_CONFIRM_2")

# Orig Order Qty -> F1
txt = get_text().lower()
if "orig order qty:" in txt:
    print(">>> Orig Order Qty: F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("15_AFTER_ORIG_QTY_F1")

# Pricing Date popup -> F1
txt = get_text().lower()
if "pricing date:" in txt and "price list:" in txt:
    print(">>> Pricing Date popup: F1...", flush=True)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("16_AFTER_PRICING_DATE_F1")

# List Price -> F1
print(">>> List Price: F1...", flush=True)
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("17_PRICE_FIELD_ACTIVE")

# Price: 150
print(">>> Price: 150...", flush=True)
send_keys(b"150", 0.2)
print_screen("18_PRICE_TYPED")

# ここで何を押すと明細が確定するか？
# まず Enter を送ってみる
print(">>> Sending Enter on Price...", flush=True)
send_keys(b"\r", 0.8)
print_screen("19_AFTER_PRICE_ENTER")

# さらに F1 を送ってみる
print(">>> Sending F1 after Price Enter...", flush=True)
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("20_AFTER_PRICE_F1")

# 何が出ているか確認し、Tax や Comments や Ln 2 の挙動を観察
for step in range(21, 26):
    txt = get_text().lower()
    print(f"\n>>> Step {step}: current screen status...", flush=True)
    if "tax usage" in txt or "tax environment" in txt:
        print(">>> Tax popup detected, sending F1", flush=True)
        send_keys(KEY_SEQUENCES["F1"], 0.8)
    elif "transaction comments" in txt:
        print(">>> Comments detected, sending F4", flush=True)
        send_keys(KEY_SEQUENCES["F4"], 0.8)
    elif "sales order line" in txt:
        print(f">>> At Line Items screen, cursor is row={screen.cursor.y+1}, col={screen.cursor.x+1}")
        # 空の Ln 欄なら F4 を押してみる
        if screen.cursor.y + 1 in [8, 9] and screen.cursor.x + 1 in [4, 5]:
            print(">>> Cursor is on Ln (new line), sending F4 to exit lines!", flush=True)
            send_keys(KEY_SEQUENCES["F4"], 1.0)
            print_screen(f"{step}_AFTER_LN_F4")
            break
        else:
            print(">>> Sending F1...", flush=True)
            send_keys(KEY_SEQUENCES["F1"], 0.8)
    else:
        print(">>> Other screen, sending F1", flush=True)
        send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen(f"{step}_RESULT")

print_screen("FINAL_STATE_BEFORE_CLEANUP")

# クリーンアップ
for _ in range(6):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()
