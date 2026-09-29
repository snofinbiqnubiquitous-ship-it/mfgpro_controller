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
from order_entry import SalesOrderAutomationController

with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(cfg["host"], port=cfg.get("port", 22), username=cfg["user"], password=base64.b64decode(cfg["pass_b64"]).decode("utf-8"), timeout=12)

channel = ssh.invoke_shell(term="vt100", width=132, height=24)
channel.setblocking(False)

screen = pyte.Screen(132, 24)
stream = pyte.Stream(screen)

def feed(sec=0.4):
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
    feed(0.1)
    return "\n".join("".join(screen.buffer[r][c].data for c in range(132)).rstrip() for r in range(24))

class MockSession:
    def __init__(self, ch):
        self.ch = ch
    def send(self, data):
        if isinstance(data, str):
            self.ch.send(data.encode("cp932"))
        else:
            self.ch.send(data)
        feed(0.2)

session = MockSession(channel)

# 1. ログイン
feed(1.0)
session.send("2\r")
session.send("1\r")
session.send("\r\r")

for _ in range(15):
    txt = get_text().lower()
    if "mfmenu" in txt and "main menu" in txt:
        break
    if "space" in txt or "continue" in txt:
        session.send(" ")
    time.sleep(0.3)

print("Starting 99.7.1.1...")
session.send("99.7.1.1\r")
feed(1.0)
session.send("\r") # Order 採番
feed(1.2)

# ヘッダー入力
payload = {
    "customer_name": "TOPPANインフォメディア株式会社",
    "ship_to": "TOPPANインフォメディア(株)福島工場",
    "purchase_order": "test",
    "customer_code": "20000600",
    "ship_to_code": "20000601",
    "address": "960-8201\nTOPPANインフォメディア(株)福島工場\n福島県福島市岡島字宮田30-2\n\n\n024-536-6111",
    "remarks": "test",
    "so_comment": "",
    "required_date": "2026-09-30",
    "due_date": "2026-10-01",
    "items": [
        {
            "product_name": "BW0116Q3-2",
            "width": "200",
            "length": "600",
            "quantity": 1,
            "price": "120"
        }
    ]
}

controller = SalesOrderAutomationController(
    session=session,
    get_screen_text=get_text,
    payload=payload,
    sleep_func=lambda s: time.sleep(s),
    default_timeout=15.0,
    logger=lambda msg: print(f"[CONTROLLER LOG] {msg}")
)

# Step 2 ヘッダー
print("\n>>> Executing Step 2 Header manually...")
session.send("20000600\r")
feed(0.5)
if "space" in get_text().lower() or "category=" in get_text().lower():
    session.send(" ")
    feed(0.5)

session.send("20000600\r")
session.send("20000601\r")
session.send("\r")          # Order Date
session.send("09/30/26\r")  # Req Date
session.send("\r")          # Promise Date
session.send("10/01/26\r")  # Due Date
session.send("\r")          # Perform Date
session.send("\r")          # Pricing Date
session.send("test\r")      # PO
session.send("test\r")      # Remarks
session.send(KEY_SEQUENCES["F1"])
feed(1.0)
if "space" in get_text().lower():
    session.send(" ")
    feed(0.5)

# Step 3 Tax
if "tax usage:" in get_text().lower() or "tax" in get_text().lower():
    session.send(KEY_SEQUENCES["F1"])
    feed(0.8)

# Step 4 Salesperson
if "salesperson 1:" in get_text().lower():
    session.send(KEY_SEQUENCES["F1"])
    feed(0.8)

# Step 5 Comments
for _ in range(5):
    txt = get_text().lower()
    if "transaction comments" in txt:
        session.send(KEY_SEQUENCES["F4"])
        feed(0.8)
        break
    time.sleep(0.3)

# Step 6 Line Items (ここからコントローラーが全自動実行！)
print("\n>>> Executing Step 6 with SalesOrderAutomationController.execute_step6()...")
controller.execute_step6()

print("\n>>> COMPLETED SUCCESSFULLY!")
final_txt = get_text()
print("Final Screen text:")
for line in final_txt.split("\n")[:10]:
    if line.strip():
        print("  ", line)

# クリーンアップ
for _ in range(5):
    session.send(KEY_SEQUENCES["F4"])
    time.sleep(0.3)

ssh.close()
