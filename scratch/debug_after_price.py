import sys
from pathlib import Path

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
sys.path.insert(0, str(repo_dir))

import base64
import json
import time
import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(cfg["host"], port=cfg.get("port", 22), username=cfg["user"], password=base64.b64decode(cfg["pass_b64"]).decode("utf-8"), timeout=12)

channel = ssh.invoke_shell(term="vt100", width=132, height=24)
channel.setblocking(False)

screen = pyte.Screen(132, 24)
stream = pyte.Stream(screen)

def feed(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        try:
            data = channel.recv(4096)
            if data:
                stream.feed(data.decode("cp932", errors="replace"))
        except Exception:
            pass
        time.sleep(0.05)

def get_text():
    return "\n".join("".join(screen.buffer[r][c].data for c in range(80)).rstrip() for r in range(24))

def send_keys(keys, wait=0.5):
    if isinstance(keys, str):
        keys = keys.encode("cp932")
    channel.send(keys)
    feed(wait)

def print_screen(title=""):
    print(f"\n{'='*70}\n {title} (Cursor: row={screen.cursor.y+1}, col={screen.cursor.x+1})\n{'='*70}")
    for y, line in enumerate(screen.display, 1):
        safe_line = "".join([c if ord(c) < 128 or c.isprintable() else "?" for c in line[:80]])
        print(f"{y:2d} | {safe_line}")

# ログイン
feed(1.0)
send_keys("2\r", 0.8)
send_keys("1\r", 0.8)
send_keys("\r\r", 0.8)

for _ in range(15):
    txt = get_text().lower()
    if "mfmenu" in txt and "main menu" in txt:
        break
    if "space" in txt or "continue" in txt:
        send_keys(" ", 0.4)
    time.sleep(0.3)

send_keys("99.7.1.1\r", 1.5)
send_keys("\r", 1.5)

send_keys("20000600\r", 1.2)
if "space" in get_text().lower() or "category=" in get_text().lower():
    send_keys(" ", 0.5)

send_keys("20000600\r", 0.4)
send_keys("20000601\r", 0.6)
send_keys("\r", 0.3)
send_keys("09/30/26\r", 0.3)
send_keys("\r", 0.3)
send_keys("10/01/26\r", 0.3)
send_keys("\r", 0.3)
send_keys("\r", 0.3)
send_keys("test\r", 0.3)
send_keys("test\r", 0.6)
send_keys(KEY_SEQUENCES["F1"], 1.0)
if "space" in get_text().lower():
    send_keys(" ", 0.5)

if "tax usage:" in get_text().lower() or "tax" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

if "salesperson 1:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

for _ in range(5):
    txt = get_text().lower()
    if "transaction comments" in txt:
        send_keys(KEY_SEQUENCES["F4"], 0.8)
        break
    time.sleep(0.3)

# Step 6.1.0 Ln 採番
send_keys("\r", 0.8)
send_keys(KEY_SEQUENCES["F1"], 0.8) # Create WO
send_keys("BW0116Q3-2", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8) # Item
send_keys("CB2", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8) # Site
if "item width(mm):" not in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8) # Qty Ordered

# SL 1
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
send_keys(b"600\r", 0.8)

# Roll 1
send_keys(b"\r", 0.4)
send_keys(b"1\r", 0.4)
send_keys(b"200\r", 0.8)

# Exit rolls
send_keys(KEY_SEQUENCES["F4"], 0.8)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Exit SL
send_keys(KEY_SEQUENCES["F4"], 0.8)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Pricing Date skip
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Price
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys("120", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8)

print_screen("Right After Price 120 + F1")

# ここで何を送れば次に進むかテスト！
# まず F1 を送信してみる
print("\n>>> Sending F1...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After 1st F1 post-price")

# 次に何が出るか？
print("\n>>> Sending F1 again...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After 2nd F1 post-price")

# さらに F1 または F4
print("\n>>> Sending F1 or F4...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After 3rd F1 post-price")

# クリーンアップ
for _ in range(5):
    send_keys(KEY_SEQUENCES["F4"], 0.5)

ssh.close()
