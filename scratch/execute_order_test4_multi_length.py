import base64
import json
import os
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
sys.path.insert(0, str(repo_dir))

import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

# ログファイル準備
log_file_path = repo_dir / "scratch" / "order_test4_execution.log"
log_fp = open(log_file_path, "w", encoding="utf-8")

def log(msg):
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}"
    print(line, flush=True)
    if not log_fp.closed:
        log_fp.write(line + "\n")
        log_fp.flush()

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

def dump_screen(title=""):
    lines = []
    lines.append("=" * 80)
    lines.append(f" {title} (Cursor: row={screen.cursor.y + 1}, col={screen.cursor.x + 1})")
    lines.append("=" * 80)
    for y in range(24):
        row_chars = []
        for x in range(80):
            char_data = screen.buffer[y][x].data
            row_chars.append(char_data if char_data else " ")
        row_str = "".join(row_chars).rstrip()
        lines.append(f"{y + 1:2d} | {row_str}")
    lines.append("=" * 80)
    full_text = "\n".join(lines)
    log("\n" + full_text)
    return full_text

def wait_for_pattern(pred, desc, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        feed(0.1)
        txt = get_text()
        tl = txt.lower()
        if pred(txt, tl):
            log(f">>> Detected pattern for: {desc}")
            return True
        if "press space" in tl or "space bar" in tl:
            log(f">>> Space prompt detected while waiting for {desc}, clearing...")
            send_keys(b" ", 0.5)
    log(f"TIMEOUT waiting for: {desc}")
    dump_screen(f"TIMEOUT_{desc}")
    return False

log("================================================================================")
log("STARTING TEST 4: Single Item BW0100D, 2 Lengths (600m & 400m), Multi Widths")
log("================================================================================")

# ==============================================================================
# 1. ログイン処理
# ==============================================================================
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

log("Logged in to MFG/PRO successfully.")
dump_screen("01_MAIN_MENU")

# ==============================================================================
# 2. 99.7.1.1 起動
# ==============================================================================
log("Starting 99.7.1.1...")
send_keys(b"99.7.1.1\r", 1.2)

if not wait_for_pattern(lambda t, tl: "sales order maintenance" in tl and "order:" in tl, "99.7.1.1 Order Screen"):
    log("ERROR: Did not reach 99.7.1.1 initial screen!")
    sys.exit(1)

dump_screen("02_STEP1_ORDER_INITIAL")

# ==============================================================================
# 3. Step 1 Order 採番 (Enter)
# ==============================================================================
log("Step 1: Pressing Enter to acquire new Order ID...")
send_keys(b"\r", 1.2)

if "press space" in get_text().lower():
    send_keys(b" ", 0.6)

dump_screen("03_STEP1_AFTER_ORDER_ENTER")

order_match = re.search(r"Order:\s*(SO\d+)", get_text())
if not order_match:
    log("ERROR: Could not parse new Order ID from screen!")
    sys.exit(1)

order_id = order_match.group(1)
log(f"*** NEW ORDER ID ACQUIRED: {order_id} ***")

# ==============================================================================
# 4. Step 2 ヘッダー情報入力
# ==============================================================================
log("Step 2: Inputting Header fields...")
# Sold-To: 20000900
send_keys(b"20000900\r", 0.8)
txt = get_text().lower()
if "press space" in txt or "space bar" in txt or "strat hipo" in txt:
    log(">>> Category prompt after Sold-To, clearing with Space...")
    send_keys(b" ", 0.5)

# Bill-To: 20000900
send_keys(b"20000900\r", 0.4)
# Ship-To: 20000911
send_keys(b"20000911\r", 0.4)
# Dates & Fields:
# Order Date (Enter)
send_keys(b"\r", 0.2)
# Req Date: 09/30/26
send_keys(b"09/30/26\r", 0.2)
# Promise Date: (Enter skip)
send_keys(b"\r", 0.2)
# Due Date: 10/01/26
send_keys(b"10/01/26\r", 0.2)
# Perform Date: (Enter skip)
send_keys(b"\r", 0.2)
# Pricing Date: (Enter skip)
send_keys(b"\r", 0.2)
# PO: test2
send_keys(b"test2\r", 0.2)
# Remarks: test2
send_keys(b"test2\r", 0.4)

dump_screen("04_STEP2_HEADER_INPUT_DONE")

# ヘッダー確定: F1
log("Step 2: Confirming Header with F1...")
send_keys(KEY_SEQUENCES["F1"], 1.0)
if "press space" in get_text().lower():
    send_keys(b" ", 0.5)
dump_screen("05_STEP2_CONFIRMED")

# Step 3: Tax Popup -> F1
txt = get_text().lower()
if "tax usage" in txt or "tax environment" in txt:
    log("Step 3: Tax popup detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("06_STEP3_AFTER_TAX")

# Step 4: Salesperson / Freight -> F1
txt = get_text().lower()
if "salesperson 1:" in txt:
    log("Step 4: Salesperson / Freight detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("07_STEP4_AFTER_SALESPERSON")

# Step 5: Transaction Comments -> F4 (so_comment is empty)
txt = get_text().lower()
if "transaction comments" in txt:
    log("Step 5: Transaction Comments detected, pressing F4 to advance to Line Items...")
    send_keys(KEY_SEQUENCES["F4"], 1.0)
    dump_screen("08_STEP5_AFTER_COMMENTS")

# ==============================================================================
# 5. Step 6 明細入力 (BW0100D, 長さ2パターン: 600m & 400m, 単価130円)
# ==============================================================================
if not wait_for_pattern(lambda t, tl: "sales order line" in tl and "transaction comments" not in tl, "Line Items Screen"):
    log("ERROR: Did not reach Sales Order Line screen!")
    sys.exit(1)

log("Step 6.1.0: At Sales Order Line screen. Creating Ln 1 with Enter...")
send_keys(b"\r", 0.8)
dump_screen("09_STEP6_AFTER_LN_ENTER")

# Create WO popup -> F1
if "create wo:" in get_text().lower():
    log("Step 6.1.1: Create WO popup detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("10_STEP6_AFTER_CREATE_WO")

# Item Number: BW0100D + F1
log("Step 6.1.3: Inputting Item Number BW0100D + F1...")
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("11_STEP6_AFTER_ITEM_INPUT")

# Site: CB2 + F1
if "site" in get_text().lower():
    log("Step 6.1.3: Inputting Site CB2 + F1...")
    send_keys(b"CB2", 0.2)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("12_STEP6_AFTER_SITE_INPUT")

# Qty Ordered UM -> F1
if "item width(mm):" not in get_text().lower():
    log("Step 6.1.4: Skipping Qty Ordered UM with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("13_STEP6_AFTER_QTY_ORDERED")

# ==============================================================================
# スリット設定 SL 1 (長さ 600m, 幅 250mm, 数量 1本)
# ==============================================================================
log("Step 6.1.4 [SL 1]: Acquiring SL 1 with F1 -> Enter -> Enter...")
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
dump_screen("14_STEP6_SL1_LEN_PROMPT")

# 長さ入力: 600 + Enter
log("Step 6.2.0 [SL 1]: Inputting Length 600 + Enter...")
send_keys(b"600\r", 0.8)
dump_screen("15_STEP6_SL1_ROLL_POPUP")

# ロール入力: Rolls 1, Width 250
log("Step 6.2.1 [SL 1 Roll 1]: Ser -> Enter...")
send_keys(b"\r", 0.5)
log("Step 6.2.1 [SL 1 Roll 1]: Rolls -> 1 + Enter...")
send_keys(b"1\r", 0.5)
log("Step 6.2.1 [SL 1 Roll 1]: Width -> 250 + Enter...")
send_keys(b"250\r", 0.8)
dump_screen("16_STEP6_SL1_AFTER_WIDTH_250")

# ロール終了: F4 -> Please confirm update -> F1
log("Step 6.2.1 [SL 1]: Finishing rolls with F4...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    log("Step 6.2.1 [SL 1]: Confirm update (Rolls) with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("17_STEP6_SL1_AFTER_ROLLS_CONFIRM")

# ==============================================================================
# スリット設定 SL 2 (長さ 400m, 幅 120mm, 数量 1本)
# (カーソルは既に SL 一覧の 2行目 row=14, col=4 にある)
# ==============================================================================
log("Step 6.1.4 [SL 2]: Acquiring SL 2 with F1 -> Enter -> Enter...")
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
dump_screen("18_STEP6_SL2_LEN_PROMPT")

# 長さ入力: 400 + Enter
log("Step 6.2.0 [SL 2]: Inputting Length 400 + Enter...")
send_keys(b"400\r", 0.8)
dump_screen("19_STEP6_SL2_ROLL_POPUP")

# ロール入力: Rolls 1, Width 120
log("Step 6.2.1 [SL 2 Roll 1]: Ser -> Enter...")
send_keys(b"\r", 0.5)
log("Step 6.2.1 [SL 2 Roll 1]: Rolls -> 1 + Enter...")
send_keys(b"1\r", 0.5)
log("Step 6.2.1 [SL 2 Roll 1]: Width -> 120 + Enter...")
send_keys(b"120\r", 0.8)
dump_screen("20_STEP6_SL2_AFTER_WIDTH_120")

# ロール終了: F4 -> Please confirm update -> F1
log("Step 6.2.1 [SL 2]: Finishing rolls with F4...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    log("Step 6.2.1 [SL 2]: Confirm update (Rolls) with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("21_STEP6_SL2_AFTER_ROLLS_CONFIRM")

# ==============================================================================
# 全スリット(全長さ)終了: F4 -> Please confirm update -> F1
# ==============================================================================
log("Step 6.2.1: Finishing ALL SL with F4...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    log("Step 6.2.1: Confirm update (ALL SL) with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("22_STEP6_AFTER_ALL_SL_CONFIRM")

# Orig Order Qty -> F1
if "orig order qty:" in get_text().lower():
    log("Step 6.2.3: Skipping Orig Order Qty with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Pricing Date popup -> F1
if "pricing date:" in get_text().lower():
    log("Step 6.2.3: Skipping Pricing Date popup with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# List Price -> F1
log("Step 6.2.4: Advancing past List Price with F1...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("23_STEP6_PRICE_PROMPT")

# Price: 130 + Enter -> F1
log("Step 6.2.4: Inputting Price 130 + Enter...")
send_keys(b"130\r", 0.6)
log("Step 6.2.4: Sending F1 after Price...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("24_STEP6_AFTER_PRICE")

# Tax popup -> F1
if "tax usage" in get_text().lower():
    log("Step 6.2.5: Line Tax popup detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Transaction comments -> F4
if "transaction comments" in get_text().lower():
    log("Step 6.2.5: Line Comments detected, skipping with F4...")
    send_keys(KEY_SEQUENCES["F4"], 0.8)

dump_screen("25_STEP6_AFTER_LINE_COMMENTS")

# Reason Code ポップアップが出現した場合の対応 (70, 28, 28)
txt = get_text().lower()
if "reason code" in txt:
    log(">>> Reason Code popup detected! Inputting 70, 28, 28...")
    send_keys(b"70\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("26_STEP6_AFTER_REASON_CODE")

# ==============================================================================
# 6. 明細脱出シーケンス（Ln 2 -> Ln -> Format -> Step 6.3.0 合計画面）
# ==============================================================================
log("Step 6.2.5: Line 1 complete. Checking for Create WO popup on next line...")
txt = get_text().lower()
if "create wo:" in txt:
    log(">>> Create WO popup detected on next line, dismissing with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

log("Step 6.2.5: Navigating dynamically to Step 6.3.0 Totals screen...")
for attempt in range(6):
    txt = get_text().lower()
    if "line total:" in txt or "total tax:" in txt or "enter data or press f4" in txt:
        log(">>> Reached Step 6.3.0 Totals screen successfully!")
        break
    log(f">>> Sending F4 (stage {attempt + 1})...")
    send_keys(KEY_SEQUENCES["F4"], 0.8)

dump_screen("27_STEP630_TOTALS_SCREEN")

if not wait_for_pattern(lambda t, tl: "line total:" in tl or "total tax:" in tl or "enter data or press f4" in tl, "Totals Screen", timeout=8.0):
    log("ERROR: Did not reach Step 6.3.0 Totals screen!")
    sys.exit(1)

# ==============================================================================
# 7. Step 6.3.0 最終コミット処理
# ==============================================================================
log("Step 6.3.0: On Totals Screen. Sending F1 to advance to Frame 2+...")
send_keys(KEY_SEQUENCES["F1"], 1.0)
dump_screen("28_STEP630_FRAME_2PLUS")

log("Step 6.3.0: Sending F4 to commit and trigger hold/credit check...")
send_keys(KEY_SEQUENCES["F4"], 1.2)
dump_screen("29_STEP630_AFTER_F4_COMMIT")

# Space プロンプト（Credit check / Overdue warnings）の解除
for i in range(1, 6):
    txt = get_text().lower()
    if "press space" in txt or "space bar" in txt:
        log(f">>> Space prompt {i} detected! Sending Space...")
        send_keys(b" ", 1.0)
        dump_screen(f"30_STEP630_AFTER_SPACE_{i}")
    else:
        break

# 最終確定・初期画面へ戻る: F4
log("Step 6.3.0: Sending final F4 to complete order and return to initial screen...")
send_keys(KEY_SEQUENCES["F4"], 1.5)
dump_screen("31_STEP630_INITIAL_SCREEN")

log("================================================================================")
log(f"*** ORDER {order_id} CREATION & COMMIT FLOW COMPLETED SUCCESSFULLY! ***")
log("================================================================================")

# 終了クリーンアップ
for _ in range(3):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()

# ==============================================================================
# 8. DB直接検証
# ==============================================================================
log("Querying database to verify commit...")
ssh_db = paramiko.SSHClient()
ssh_db.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_db.connect(host, port=port, username=user, password=password, timeout=12)

p_script = f"""
OUTPUT TO "/tmp/order_test4_db.txt".
PUT UNFORMATTED "=== SO_MSTR ===" SKIP.
FOR EACH so_mstr NO-LOCK WHERE so_nbr = "{order_id}":
    EXPORT so_nbr so_cust so_ship so_ord_date so_req_date so_due_date so_po so_stat so_taxable so_tax_env.
END.
PUT UNFORMATTED "=== SOD_DET ===" SKIP.
FOR EACH sod_det NO-LOCK WHERE sod_nbr = "{order_id}":
    EXPORT sod_nbr sod_line sod_part sod_qty_ord sod_um sod_price sod_site sod_status.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh_db.exec_command(f"cat << 'EOF' > /tmp/query_test4.p\n{p_script}\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b; export DLC; PATH=$PATH:$DLC/bin; export PATH; PROSTARTUP=/usr/dlc101b/japanese.pf; export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_test4.p > /dev/null 2>&1
cat /tmp/order_test4_db.txt 2>/dev/null
"""
stdin, stdout, stderr = ssh_db.exec_command(cmd)
db_res = stdout.read().decode("cp932", errors="replace")
log("=== DB VERIFICATION RESULT ===")
log(db_res)
ssh_db.close()
log_fp.close()
