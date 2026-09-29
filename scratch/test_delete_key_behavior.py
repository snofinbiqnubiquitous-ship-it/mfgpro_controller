import base64
import json
import time
from pathlib import Path
import paramiko
import pyte

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
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
    return "\n".join("".join(screen.buffer[r][c].data for c in range(132)) for r in range(24))

def send_keys(keys, wait=0.5):
    if isinstance(keys, str):
        keys = keys.encode("cp932")
    channel.send(keys)
    feed(wait)

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

print("Logged in. Starting 99.7.1.1...")
send_keys("99.7.1.1\r", 1.5)

# Order 番号採番
send_keys("\r", 1.5)

# Step 2 ヘッダー画面に到着
# Sold-To に "20000900" を入れてみる
print("In Step 2 header screen.")

# テスト1: 候補キーを試す
# カーソル位置で "TESTING" と入力し、Left を 3回送り（'I' の位置）、キーを押し、画面の文字を確認する
candidates = [
    ("Control-D (\\x04)", b"\x04"),
    ("DEL 127 (\\x7f)", b"\x7f"),
    ("VT220 Delete (\\x1b[3~)", b"\x1b[3~"),
    ("Backspace (\\x08)", b"\x08"),
    ("Escape-W (\\x1bW)", b"\x1bW"),
    ("Escape-w (\\x1bw)", b"\x1bw"),
]

for name, key in candidates:
    # 一旦フィールドをクリアするために Backspace をたくさん送る
    send_keys(b"\x08" * 15, 0.3)
    # 文字列 "ABCDEF" を入力
    send_keys(b"ABCDEF", 0.4)
    # カーソルを 3文字左に戻す ("\x1b[D" * 3) -> カーソルは 'D' の上
    send_keys(b"\x1b[D\x1b[D\x1b[D", 0.4)
    # テスト対象キーを 1回送信
    send_keys(key, 0.5)
    
    # 画面行を取得
    txt = get_text()
    lines = [line.strip() for line in txt.split("\n") if "ABC" in line or "AB" in line]
    print(f"Key [{name}]:")
    for l in lines:
        print(f"  Line: {l}")

# 終了処理 (F4 で抜ける)
send_keys(b"\x1bOS", 0.8) # F4
send_keys(b"\x1bOS", 0.8) # F4
send_keys(b"\x1bOS", 0.8) # F4

ssh.close()
