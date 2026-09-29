import base64
import json
import os
from pathlib import Path
import re
import sys
import time

import paramiko
import pyte

# ==============================================================================
# 設定読み込み
# ==============================================================================
repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

host = cfg["host"]
port = cfg.get("port", 22)
user = cfg["user"]
password = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

COLS, ROWS = 132, 24
screen = pyte.Screen(COLS, ROWS)
screen.use_utf8 = False
stream = pyte.Stream(screen)

KEY_SEQUENCES = {
    "F1": b"\x1bOP",
    "F2": b"\x1bOQ",
    "F3": b"\x1bOR",
    "F4": b"\x1bOS",
    "Enter": b"\r",
    "Space": b" ",
    "Up": b"\x1b[A",
    "Down": b"\x1b[B",
    "Right": b"\x1b[C",
    "Left": b"\x1b[D",
}

# ==============================================================================
# テスト用 Payload
# ==============================================================================
payload = {
    "customer_name": "株式会社タカラ",
    "ship_to": "株式会社カクエイ",
    "purchase_order": "test2",
    "customer_code": "20000900",
    "ship_to_code": "20000911",
    "address": "179-0075\n株式会社カクエイ\n東京都練馬区高松6-36-12\n\n\n03-3904-2581",
    "remarks": "test2",
    "so_comment": "テスト用です",
    "required_date": "2026-09-30",
    "due_date": "2026-10-01",
    "items": [
        {
            "product_name": "BW0100D",
            "width": "250",
            "length": "600",
            "quantity": 1,
            "price": "130"
        }
    ]
}

# ログファイル準備
log_path = repo_dir / "scratch" / "order_test6_execution.log"
log_fp = open(log_path, "w", encoding="utf-8")

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    out = f"[{ts}] {msg}"
    print(out, flush=True)
    log_fp.write(out + "\n")
    log_fp.flush()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port=port, username=user, password=password, timeout=12)
shell = ssh.invoke_shell(term="vt100", width=COLS, height=ROWS)
shell.settimeout(0.1)

def feed(duration=0.5):
    start = time.time()
    while time.time() - start < duration:
        try:
            chunk = shell.recv(4096)
            if chunk:
                try:
                    text_chunk = chunk.decode("cp932", errors="replace")
                except Exception:
                    text_chunk = chunk.decode("utf-8", errors="replace")
                stream.feed(text_chunk)
        except Exception:
            pass
        time.sleep(0.05)

def send_keys(data, delay=0.5):
    if isinstance(data, str):
        data = data.encode("cp932")
    shell.sendall(data)
    feed(delay)

def get_text():
    lines = []
    for r in range(ROWS):
        line_chars = [screen.buffer[r][c].data for c in range(80)]
        lines.append("".join(line_chars).rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

def dump_screen(tag=""):
    cur = screen.cursor
    border = "=" * 80
    lines = [f"{border}", f" {tag} (Cursor: row={cur.y+1}, col={cur.x+1})", f"{border}"]
    for r in range(ROWS):
        line_chars = [screen.buffer[r][c].data for c in range(80)]
        lines.append(f"{r+1:2d} | " + "".join(line_chars))
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
log("STARTING TEST 6: Single Product (BW0100D) with SO Comment ('テスト用です')")
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
# 3. Step 1 Order 採番 (Enter) - 単一ID厳守
# ==============================================================================
log("Step 1: Pressing Enter to acquire new Order ID (strictly once)...")
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
send_keys(b"\r", 0.2)           # Order Date
send_keys(b"09/30/26\r", 0.2)   # Req Date
send_keys(b"\r", 0.2)           # Promise Date
send_keys(b"10/01/26\r", 0.2)   # Due Date
send_keys(b"\r", 0.2)           # Perform Date
send_keys(b"\r", 0.2)           # Pricing Date
send_keys(b"test2\r", 0.2)      # PO
send_keys(b"test2\r", 0.4)      # Remarks

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

# ==============================================================================
# 5. Step 5 特記事項 (Transaction Comments)
# ==============================================================================
if not wait_for_pattern(lambda t, tl: "transaction comments" in tl or "sales order line" in tl, "Transaction Comments"):
    log("ERROR: Did not reach Transaction Comments or Sales Order Line!")
    sys.exit(1)

txt = get_text().lower()
if "transaction comments" in txt:
    log("Step 5: Transaction Comments screen detected!")
    dump_screen("08_STEP5_COMMENTS_INITIAL")
    
    so_comm = payload.get("so_comment", "").strip()
    if so_comm:
        log(f"Step 5: Inputting SO Comment: '{so_comm}'")
        cur_before = screen.cursor
        log(f"Step 5: Cursor before F1: row={cur_before.y+1}, col={cur_before.x+1}")
        
        # F1 を送信してコメント入力欄へ
        log("Step 5: Sending F1 to enter comment lines editor...")
        send_keys(KEY_SEQUENCES["F1"], 0.8)
        dump_screen("09_STEP5_AFTER_F1")
        cur_after_f1 = screen.cursor
        log(f"Step 5: Cursor after F1: row={cur_after_f1.y+1}, col={cur_after_f1.x+1}")
        
        # コメント本文を1行ずつ送信
        for c_line in so_comm.splitlines():
            log(f"Step 5: Typing line: '{c_line}' + Enter...")
            send_keys(c_line.encode("cp932") + b"\r", 0.6)
            dump_screen(f"10_STEP5_TYPED_{c_line[:10]}")
        
        # コメント本文確定: F1
        log("Step 5: Confirming comment body with F1...")
        send_keys(KEY_SEQUENCES["F1"], 0.8)
        dump_screen("11_STEP5_AFTER_COMMENT_F1")
        
        # 'Print On Quote:' が画面下に出ていれば F1 で確定
        txt_after_comm = get_text().lower()
        if "print on quote" in txt_after_comm:
            log("Step 5: 'Print On Quote:' detected, confirming with F1...")
            send_keys(KEY_SEQUENCES["F1"], 0.8)
            dump_screen("12_STEP5_AFTER_PRINT_QUOTE_F1")
        
        # 最初の入力欄に復帰した状態で F4 を押して明細画面へ
        log("Step 5: Sending F4 to exit comments and proceed to Line Items...")
        send_keys(KEY_SEQUENCES["F4"], 1.0)
        dump_screen("13_STEP5_AFTER_F4_EXIT")
    else:
        log("Step 5: No SO Comment, pressing F4 to advance...")
        send_keys(KEY_SEQUENCES["F4"], 1.0)
        dump_screen("13_STEP5_AFTER_F4_EXIT")

# ==============================================================================
# 6. Step 6 明細入力 (BW0100D, 130円, 600m x 250mm x 1本 = 150 M2)
# ==============================================================================
if not wait_for_pattern(lambda t, tl: "sales order line" in tl and "transaction comments" not in tl, "Line Items Screen"):
    log("ERROR: Did not reach Sales Order Line screen after Step 5!")
    # もし画面に何らかのメッセージがあればダンプ
    dump_screen("ERROR_NOT_REACHED_LINE_ITEMS")
    sys.exit(1)

log("\n================================================================================")
log("Entering Line 1: BW0100D, Price 130, Length 600m x Width 250mm x 1 roll")
log("================================================================================")

# Ln 1 採番 (Enter)
log("Line 1: Pressing Enter to acquire Ln 1...")
send_keys(b"\r", 0.8)
dump_screen("14_LINE1_AFTER_LN_ENTER")

# Create WO popup -> F1
txt = get_text().lower()
if "create wo:" in txt:
    log("Line 1: Create WO popup detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("15_LINE1_AFTER_CREATE_WO")

# Item Number: BW0100D + F1
log("Line 1: Inputting Item Number 'BW0100D' + F1...")
send_keys(b"BW0100D", 0.2)
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("16_LINE1_AFTER_ITEM_INPUT")

# Site: CB2 + F1
txt = get_text().lower()
if "site" in txt:
    log("Line 1: Inputting Site CB2 + F1...")
    send_keys(b"CB2", 0.2)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("17_LINE1_AFTER_SITE_INPUT")

# Qty Ordered UM -> F1
txt = get_text().lower()
if "item width(mm):" not in txt:
    log("Line 1: Skipping Qty Ordered UM with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("18_LINE1_AFTER_QTY_ORDERED")

# SL 1 入力: F1 -> \r -> \r -> Len 600
log("Line 1 [SL 1]: Opening Len(m) prompt...")
send_keys(KEY_SEQUENCES["F1"], 0.6)
send_keys(b"\r", 0.4)
send_keys(b"\r", 0.6)
dump_screen("19_LINE1_SL1_LEN_PROMPT")

log("Line 1 [SL 1]: Inputting Length '600' + Enter...")
send_keys(b"600\r", 0.8)
dump_screen("20_LINE1_SL1_ROLL_POPUP")

# ロール入力: Ser(\r) -> Rolls(1\r) -> Width(250\r)
log("Line 1 [SL 1 Roll 1]: Ser -> Enter, Rolls -> 1, Width -> 250")
send_keys(b"\r", 0.5)
send_keys(b"1\r", 0.5)
send_keys(b"250\r", 0.8)
dump_screen("21_LINE1_SL1_R1_DONE")

# 当該長さのロール完了: F4 -> Please confirm update -> F1
log("Line 1 [SL 1]: Finishing rolls with F4...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    log("Line 1 [SL 1]: Confirm update (Rolls) with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("22_LINE1_SL1_ROLLS_CONFIRMED")

# 当該品番の全SL終了: F4 -> Please confirm update -> F1
log("Line 1: Finishing ALL SL with F4...")
send_keys(KEY_SEQUENCES["F4"], 0.8)
if "confirm update" in get_text().lower():
    log("Line 1: Confirm update (ALL SL) with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("23_LINE1_AFTER_ALL_SL_CONFIRM")

# Orig Order Qty -> F1 (if present)
txt = get_text().lower()
if "orig order qty:" in txt:
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Pricing Date popup -> F1 (if present)
txt = get_text().lower()
if "pricing date:" in txt:
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# List Price -> F1
log("Line 1: Advancing past List Price with F1...")
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("24_LINE1_PRICE_PROMPT")

# Price: 130 + F1
log("Line 1: Inputting Price '130' + Enter -> F1...")
send_keys(b"130\r", 0.6)
send_keys(KEY_SEQUENCES["F1"], 0.8)
dump_screen("25_LINE1_AFTER_PRICE")

# Line Tax popup -> F1
txt = get_text().lower()
if "tax usage" in txt:
    log("Line 1: Line Tax popup detected, confirming with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

# Line Comments -> F4
txt = get_text().lower()
if "transaction comments" in txt:
    log("Line 1: Line Comments detected, skipping with F4...")
    send_keys(KEY_SEQUENCES["F4"], 0.8)
dump_screen("26_LINE1_AFTER_LINE_COMMENTS")

# Reason Code ポップアップ (70, 28, 28)
txt = get_text().lower()
if "reason code" in txt:
    log("Line 1: Reason Code popup detected! Inputting 70, 28, 28...")
    send_keys(b"70\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(b"28\r", 0.4)
    send_keys(KEY_SEQUENCES["F1"], 0.8)
    dump_screen("27_LINE1_AFTER_REASON_CODE")

# ==============================================================================
# 7. 明細脱出シーケンス（次行 Create WO 解除 -> Ln -> Step 6.3.0 合計画面）
# ==============================================================================
txt = get_text().lower()
if "create wo:" in txt:
    log(">>> Create WO popup detected on Line 2, dismissing with F1...")
    send_keys(KEY_SEQUENCES["F1"], 0.8)

log("Navigating to Step 6.3.0 Totals screen...")
for attempt in range(6):
    txt = get_text().lower()
    if "line total:" in txt or "total tax:" in txt or "enter data or press f4" in txt:
        log(">>> Reached Step 6.3.0 Totals screen successfully!")
        break
    log(f">>> Sending F4 (stage {attempt + 1})...")
    send_keys(KEY_SEQUENCES["F4"], 0.8)

dump_screen("28_STEP630_TOTALS_SCREEN")

if not wait_for_pattern(lambda t, tl: "line total:" in tl or "total tax:" in tl or "enter data or press f4" in tl, "Totals Screen", timeout=8.0):
    log("ERROR: Did not reach Step 6.3.0 Totals screen!")
    sys.exit(1)

# ==============================================================================
# 8. Step 6.3.0 最終コミット処理
# ==============================================================================
log("Step 6.3.0: On Totals Screen. Sending F1 to advance to Frame 2+...")
send_keys(KEY_SEQUENCES["F1"], 1.0)
dump_screen("29_STEP630_FRAME_2PLUS")

log("Step 6.3.0: Sending F4 to commit and trigger hold/credit check...")
send_keys(KEY_SEQUENCES["F4"], 1.2)
dump_screen("30_STEP630_AFTER_F4_COMMIT")

# Space プロンプト（Credit check / Overdue warnings）の解除
for i in range(1, 6):
    txt = get_text().lower()
    if "press space" in txt or "space bar" in txt:
        log(f">>> Space prompt {i} detected! Sending Space...")
        send_keys(b" ", 1.0)
        dump_screen(f"31_STEP630_AFTER_SPACE_{i}")
    else:
        break

# 最終確定・初期画面へ戻る: F4
log("Step 6.3.0: Sending final F4 to complete order and return to initial screen...")
send_keys(KEY_SEQUENCES["F4"], 1.5)
dump_screen("32_STEP630_INITIAL_SCREEN")

log("================================================================================")
log(f"*** ORDER {order_id} CREATION & COMMIT FLOW COMPLETED SUCCESSFULLY! ***")
log("================================================================================")

# 終了クリーンアップ
for _ in range(3):
    send_keys(KEY_SEQUENCES["F4"], 0.4)

shell.close()
ssh.close()

# ==============================================================================
# 9. DB直接検証
# ==============================================================================
log("Querying database to verify commit...")
ssh_db = paramiko.SSHClient()
ssh_db.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_db.connect(host, port=port, username=user, password=password, timeout=12)

p_script = f"""
OUTPUT TO "/tmp/order_test6_db.txt".
PUT UNFORMATTED "=== SO_MSTR ===" SKIP.
FOR EACH so_mstr NO-LOCK WHERE so_nbr = "{order_id}":
    EXPORT so_nbr so_cust so_ship so_ord_date so_req_date so_due_date so_po so_stat so_taxable so_tax_env so_cmtindx.
    IF so_cmtindx > 0 THEN DO:
        PUT UNFORMATTED "=== CMT_DET ===" SKIP.
        FOR EACH cmt_det NO-LOCK WHERE cmt_indx = so_cmtindx BY cmt_seq:
            EXPORT cmt_seq cmt_type cmt_cmmt.
        END.
    END.
END.
PUT UNFORMATTED "=== SOD_DET ===" SKIP.
FOR EACH sod_det NO-LOCK WHERE sod_nbr = "{order_id}":
    EXPORT sod_nbr sod_line sod_part sod_qty_ord sod_um sod_price sod_site sod_status.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh_db.exec_command(f"cat << 'EOF' > /tmp/query_test6.p\n{p_script}\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b; export DLC; PATH=$PATH:$DLC/bin; export PATH; PROSTARTUP=/usr/dlc101b/japanese.pf; export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_test6.p > /dev/null 2>&1
cat /tmp/order_test6_db.txt 2>/dev/null
"""
stdin, stdout, stderr = ssh_db.exec_command(cmd)
db_res = stdout.read().decode("cp932", errors="replace")
log("=== DB VERIFICATION RESULT ===")
log(db_res)
ssh_db.close()
log_fp.close()
