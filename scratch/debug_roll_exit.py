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

print("Starting 99.7.1.1...")
send_keys("99.7.1.1\r", 1.5)
send_keys("\r", 1.5) # 新規オーダー採番

# ヘッダー
send_keys("20000600\r", 1.2)
if "space" in get_text().lower() or "category=" in get_text().lower():
    send_keys(" ", 0.5)

send_keys("20000600\r", 0.4)
send_keys("20000601\r", 0.6)
send_keys("\r", 0.3)          # Order Date
send_keys("09/30/26\r", 0.3)  # Req Date
send_keys("\r", 0.3)          # Promise Date
send_keys("10/01/26\r", 0.3)  # Due Date
send_keys("\r", 0.3)          # Perform Date
send_keys("\r", 0.3)          # Pricing Date
send_keys("test\r", 0.3)      # PO
send_keys("test\r", 0.6)      # Remarks

# F1 確定
send_keys(KEY_SEQUENCES["F1"], 1.0)
if "space" in get_text().lower():
    send_keys(" ", 0.5)

# Step 3 Tax
if "tax usage:" in get_text().lower() or "tax" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Step 4 Salesperson
if "salesperson 1:" in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Step 5 Comments -> F4 でスキップ
for _ in range(5):
    txt = get_text().lower()
    if "transaction comments" in txt:
        send_keys(KEY_SEQUENCES["F4"], 0.8)
        break
    time.sleep(0.3)

# Step 6.1.0 Ln 採番
send_keys("\r", 0.8)

# Create WO
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Item Number
send_keys("BW0116Q3-2", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Site
send_keys("CB2", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8)

# Qty Ordered UM -> F1
if "item width(mm):" not in get_text().lower():
    send_keys(KEY_SEQUENCES["F1"], 0.8)

print_screen("SL Table Screen")

# SL 1 取得: F1 -> Enter -> Enter
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
print_screen("After F1 -> Enter -> Enter (Len prompt)")

# 長さ: 600 + Enter
send_keys(b"600\r", 0.8)
print_screen("After 600 + Enter (Roll Popup)")

# ロール入力: Ser -> Enter, Rolls -> 1 + Enter, Width -> 200 + Enter
send_keys(b"\r", 0.4) # Ser
send_keys(b"1\r", 0.4) # Rolls
send_keys(b"200\r", 0.8) # Width
print_screen("After Width 200 + Enter")

# ここが問題の箇所！
# 今、カーソルはどこにあるか？何が表示されているか？
# 1. ロール完了 F4
print("\n>>> 1. Sending F4 to exit rolls...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
print_screen("After F4 (Rolls)")

# 2. ロール確定 F1
print("\n>>> 2. Sending F1 to confirm rolls update...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After F1 (Rolls Confirm -> Back to SL)")

# 3. 全スリット完了 F4
print("\n>>> 3. Sending F4 on SL screen to finish slit config...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
print_screen("After F4 on SL Screen")

# 4. 全スリット確定 F1
print("\n>>> 4. Sending F1 to confirm SL update...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After F1 (SL Confirm)")

# 5. Orig Order Qty が出るか？ Pricing Date が出るか？
txt = get_text().lower()
if "orig order qty:" in txt:
    print("\n>>> Orig Order Qty detected. Sending F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Orig Order Qty skip")

# 6. Pricing Date スキップ F1
print("\n>>> 6. Sending F1 on Pricing Date screen...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After Pricing Date F1 (Price Screen)")

# 7. List Price スキップ F1 -> Price 入力 -> F1
print("\n>>> 7. Sending F1 to skip List Price...")
send_keys(KEY_SEQUENCES["F1"], 0.6)
print("\n>>> Entering Price '120' + F1...")
send_keys("120", 0.3)
send_keys(KEY_SEQUENCES["F1"], 0.8)
print_screen("After Price Entered")

# 8. Tax スキップ F1
txt = get_text().lower()
if "tax" in txt:
    print("\n>>> 8. Sending F1 on Tax screen...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Tax F1")

# 9. Comments スキップ F1
txt = get_text().lower()
if "transaction comments" in txt or "adding new record" in txt:
    print("\n>>> 9. Sending F1 on Comments screen...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    print_screen("After Comments F1")

# 10. メインメニュー (Sales Order Line) 復帰 -> F4 で Totals へ
print("\n>>> 10. Sending F4 to go to Totals screen...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
print_screen("After F4 (Totals Screen)")

# クリーンアップ (F4 x 5)
for _ in range(5):
    send_keys(KEY_SEQUENCES["F4"], 0.5)

ssh.close()
