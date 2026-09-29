import base64
import json
import logging
import os
import re
import socket
import sys
import time
from datetime import date
from pathlib import Path

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
sys.path.insert(0, str(repo_dir))

import paramiko
import pyte
from terminal_core import COLS, ROWS, KEY_SEQUENCES

# --- ログ設定 ---
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("LIVE_ORDER")

log_path = repo_dir / "scratch" / "live_order_execution.log"
log_screens = []

# --- 接続設定 ---
with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

host = cfg["host"]
port = cfg.get("port", 22)
user = cfg["user"]
password = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

payload = {
  "customer_name": "株式会社タカラ",
  "ship_to": "株式会社タカラ (デフォルト)",
  "purchase_order": "test",
  "customer_code": "20000900",
  "ship_to_code": "20000904",  # 候補 A: アクティブな 20000904
  "address": "神奈川県 横浜市青葉区\n荏田北1-4-13",
  "remarks": "test",
  "so_comment": "",
  "required_date": "2026-09-29",
  "due_date": "2026-09-30",
  "items": [
    {
      "product_name": "BW0100D",
      "width": "200",
      "length": "100",
      "quantity": 1,
      "price": "150"
    }
  ]
}

def dump_screen(screen, title="SCREEN"):
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
    return "\n".join(lines)

def get_clean_screen_text(screen):
    lines = []
    for y in range(24):
        chars = [screen.buffer[y][x].data or " " for x in range(80)]
        lines.append("".join(chars).rstrip())
    return "\n".join(lines)

def run_live_execution():
    logger.info("=== QAD 99.7.1.1 実機注文入力検証 (完全自動化) 開始 ===")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    logger.info(f"SSH接続試行中 ({host}:{port}, user={user})...")
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

    def wait_predicate(pred, timeout=12.0, desc=""):
        start = time.time()
        while time.time() - start < timeout:
            feed(0.1)
            txt = get_clean_screen_text(screen)
            txt_lower = txt.lower()

            if pred(txt, txt_lower):
                return True

            # 途中での space 要求検知
            if "press space" in txt_lower or "space bar" in txt_lower:
                logger.info(f"[{desc}] 途中の 'Press space bar to continue' を検知。Spaceキー送信")
                send_keys(b" ", wait_after=0.4)
                continue

            # エラー表示の検知
            if "** error **" in txt_lower or "value should be > 0" in txt_lower or "error:" in txt_lower:
                logger.error(f"[{desc}] 画面内にエラーを検知しました！: {txt}")
                return False

        logger.warning(f"[{desc}] 待機タイムアウト ({timeout}秒)")
        return False

    assigned_order_id = "UNKNOWN"

    try:
        # 初期化 ＆ ログイン
        feed(1.5)
        logger.info("自動ログイン中 (2 -> 1 -> Enter x 2)...")
        send_keys(b"2\r", 0.8)
        send_keys(b"1\r", 0.8)
        send_keys(b"\r\r", 1.0)

        # メインメニュー待機
        logger.info("メインメニュー (mfmenu) 到達待機中...")
        for _ in range(15):
            feed(0.4)
            txt = get_clean_screen_text(screen).lower()
            if "mfmenu" in txt and "main menu" in txt:
                if "please confirm exit" in txt:
                    send_keys(b"n\r", 0.5)
                    continue
                logger.info("メインメニュー到着確認！")
                break
            if "press space" in txt or "continue" in txt:
                send_keys(b" ", 0.5)
                continue
            time.sleep(0.3)

        log_screens.append(dump_screen(screen, "01_MAIN_MENU"))

        # =========================================================================
        # STEP 1: 99.7.1.1 遷移 ＆ Order番号自動採番
        # =========================================================================
        logger.info(">> [STEP 1] 99.7.1.1 受注登録画面へ遷移中...")
        send_keys(b"99.7.1.1\r", 1.5)

        ok = wait_predicate(lambda t, tl: "order:" in tl and "sales order maintenance" in tl, timeout=10, desc="Step 1 Order画面")
        log_screens.append(dump_screen(screen, "02_STEP1_ORDER_PROMPT"))
        if not ok:
            raise RuntimeError("Step 1: Order入力画面への遷移に失敗しました")

        logger.info(">> [STEP 1] Order 欄で空のまま <Enter> 送信 (最新番号の自動採番)...")
        send_keys(b"\r", 1.2)

        # 採番完了後、Sold-To 欄 (Row 3, Col 29) へ移動するのを待機
        ok = wait_predicate(lambda t, tl: "sold-to" in tl and ("order date:" in tl or "line pricing:" in tl), timeout=10, desc="Step 1 Sold-To着地")
        log_screens.append(dump_screen(screen, "03_STEP1_AFTER_AUTO_ORDER"))
        if not ok:
            raise RuntimeError("Step 1: Order自動採番後のヘッダー画面到達に失敗しました")

        # Order ID の抽出
        header_txt = get_clean_screen_text(screen)
        order_id_match = re.search(r'(?:sales\s+order|order):\s*([a-z0-9]+)', header_txt, re.IGNORECASE)
        assigned_order_id = order_id_match.group(1) if order_id_match else "UNKNOWN"
        logger.info(f"★ [STEP 1 成功] 自動採番された Order ID: 【{assigned_order_id}】")

        # =========================================================================
        # STEP 2: 受注ヘッダー順次フィールド入力
        # =========================================================================
        logger.info(f">> [STEP 2] 受注ヘッダー順次フィールド入力開始 (Order ID: {assigned_order_id})...")
        c_code = payload["customer_code"]
        s_code = payload["ship_to_code"]
        today_qad = date.today().strftime("%m/%d/%y")
        req_d = date.fromisoformat(payload["required_date"]).strftime("%m/%d/%y")
        due_d = date.fromisoformat(payload["due_date"]).strftime("%m/%d/%y")
        po_val = payload["purchase_order"]
        rem_val = payload["remarks"]

        # 1. Sold-To
        logger.info(f"   Field 1: Sold-To '{c_code}' 送信")
        send_keys(c_code.encode("ascii") + b"\r", wait_after=1.2)
        txt = get_clean_screen_text(screen).lower()
        if "space" in txt or "continue" in txt or "category=" in txt:
            logger.info("   Sold-To後のスペース要求検知。Space送信")
            send_keys(b" ", wait_after=0.8)

        # 2. Bill-To
        logger.info(f"   Field 2: Bill-To '{c_code}' 送信")
        send_keys(c_code.encode("ascii") + b"\r", wait_after=0.6)

        # 3. Ship-To
        logger.info(f"   Field 3: Ship-To '{s_code}' 送信")
        send_keys(s_code.encode("ascii") + b"\r", wait_after=0.8)

        # 4. Order Date
        logger.info(f"   Field 4: Order Date (当日日付保持) <Enter> 送信")
        send_keys(b"\r", wait_after=0.4)

        # 5. Required Date
        logger.info(f"   Field 5: Required Date '{req_d}' 送信")
        send_keys(req_d.encode("ascii") + b"\r", wait_after=0.4)

        # 6. Promise Date
        logger.info(f"   Field 6: Promise Date (スキップ) <Enter> 送信")
        send_keys(b"\r", wait_after=0.4)

        # 7. Due Date
        logger.info(f"   Field 7: Due Date '{due_d}' 送信")
        send_keys(due_d.encode("ascii") + b"\r", wait_after=0.4)

        # 8. Perform Date
        logger.info(f"   Field 8: Perform Date (スキップ) <Enter> 送信")
        send_keys(b"\r", wait_after=0.4)

        # 9. Pricing Date
        logger.info(f"   Field 9: Pricing Date (スキップ) <Enter> 送信")
        send_keys(b"\r", wait_after=0.4)

        # 10. Purchase Order
        logger.info(f"   Field 10: Purchase Order '{po_val}' 送信")
        send_keys(po_val.encode("ascii") + b"\r", wait_after=0.4)

        # 11. Remarks
        logger.info(f"   Field 11: Remarks '{rem_val}' 送信")
        send_keys(rem_val.encode("ascii") + b"\r", wait_after=0.8)

        log_screens.append(dump_screen(screen, "04_STEP2_COMPLETED_HEADER"))

        # ヘッダー確定 F1 送信
        logger.info(">> [STEP 2] ヘッダー確定 <F1> 送信...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=1.2)

        # space 要求チェック
        txt = get_clean_screen_text(screen).lower()
        if "press space" in txt or "space bar" in txt:
            logger.info(">> [STEP 2] スペース要求検知。Space送信")
            send_keys(b" ", wait_after=0.8)

        log_screens.append(dump_screen(screen, "05_STEP2_CONFIRMED"))

        # =========================================================================
        # STEP 3: Tax Information ポップアップ
        # =========================================================================
        logger.info(">> [STEP 3] Tax Information ポップアップ待機中...")
        ok = wait_predicate(lambda t, tl: "tax usage:" in tl or "tax environment:" in tl or "salesperson 1:" in tl or "transaction comments" in tl or "sales order line" in tl, timeout=8, desc="Step 3 Tax枠")
        log_screens.append(dump_screen(screen, "06_STEP3_TAX_POPUP"))

        txt = get_clean_screen_text(screen).lower()
        if "tax usage:" in txt or "tax environment:" in txt:
            logger.info(">> [STEP 3] Tax ポップアップ検知。<F1> でスキップ送信")
            send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # =========================================================================
        # STEP 4: Salesperson / Freight 等 追加画面
        # =========================================================================
        logger.info(">> [STEP 4] Salesperson / Freight 追加画面待機中...")
        ok = wait_predicate(lambda t, tl: "salesperson 1:" in tl or "freight list:" in tl or "transaction comments" in tl or "sales order line" in tl, timeout=8, desc="Step 4 Salesperson")
        log_screens.append(dump_screen(screen, "07_STEP4_SALESPERSON"))

        txt = get_clean_screen_text(screen).lower()
        if "salesperson 1:" in txt or "freight list:" in txt:
            logger.info(">> [STEP 4] Salesperson 画面検知。<F1> でスキップ送信")
            send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # =========================================================================
        # STEP 5: 特記事項 (Transaction Comments)
        # =========================================================================
        logger.info(">> [STEP 5] Transaction Comments 画面待機中...")
        ok = wait_predicate(lambda t, tl: "transaction comments" in tl or ("sales order line" in tl and "transaction comments" not in tl), timeout=8, desc="Step 5 Comments")
        log_screens.append(dump_screen(screen, "08_STEP5_COMMENTS"))

        txt = get_clean_screen_text(screen).lower()
        if "transaction comments" in txt:
            logger.info(">> [STEP 5] 特記事項なし。<F4> を送信して明細画面へ進みます")
            send_keys(KEY_SEQUENCES["F4"], wait_after=1.2)
        else:
            logger.info(">> [STEP 5] コメント画面はスキップされ、直接明細画面に到達しました")

        # =========================================================================
        # STEP 6: 受注明細行入力 (Line Items)
        # =========================================================================
        logger.info(">> [STEP 6] 受注明細行画面 (6.1.0 Sales Order Line) 待機中...")
        ok = wait_predicate(lambda t, tl: "sales order line" in tl and "transaction comments" not in tl, timeout=10, desc="Step 6.1.0 メインメニュー")
        log_screens.append(dump_screen(screen, "09_STEP6_LINE_MAIN"))
        if not ok:
            raise RuntimeError("Step 6.1.0: 明細メイン画面到達に失敗しました")

        # 6.1.0 Ln 自動採番
        logger.info(">> [STEP 6.1.0] Ln 欄で空のまま <Enter> 送信 (Line 1 自動採番)...")
        send_keys(b"\r", wait_after=0.8)

        # 6.1.1 Create WO ポップアップ
        logger.info(">> [STEP 6.1.1] Create WO ポップアップ待機中...")
        ok = wait_predicate(lambda t, tl: "create wo:" in tl or "rework:" in tl, timeout=8, desc="Step 6.1.1 Create WO")
        log_screens.append(dump_screen(screen, "10_STEP6_CREATE_WO"))
        if ok:
            logger.info(">> [STEP 6.1.1] Create WO 検知。<F1> でスキップ送信")
            send_keys(KEY_SEQUENCES["F1"], wait_after=0.8)

        # 6.1.3 Item Number 入力
        logger.info(">> [STEP 6.1.3] Item Number 入力欄待機中...")
        ok = wait_predicate(lambda t, tl: "create wo:" not in tl and ("sales order line" in tl or "item number" in tl or "5=delete" in tl), timeout=8, desc="Step 6.1.3 Item Number")
        log_screens.append(dump_screen(screen, "11_STEP6_ITEM_NUMBER"))
        
        prod_name = payload["items"][0]["product_name"]
        logger.info(f">> [STEP 6.1.3] 品番 '{prod_name}' + <F1> 送信...")
        send_keys(prod_name.encode("ascii"), wait_after=0.2)
        send_keys(KEY_SEQUENCES["F1"], wait_after=0.8)

        # 6.1.3 Site ポップアップ入力
        logger.info(">> [STEP 6.1.3] Site ポップアップ枠待機中...")
        ok = wait_predicate(lambda t, tl: bool(re.search(r"[|│]\s*site\s*[|│]", tl) or re.search(r"item\s*numbe.*site", tl) or ("site" in tl and "ln item number" not in tl)), timeout=8, desc="Step 6.1.3 Site")
        log_screens.append(dump_screen(screen, "12_STEP6_SITE_POPUP"))
        
        logger.info(">> [STEP 6.1.3] Site 'CB2' + <F1> 送信...")
        send_keys(b"CB2", wait_after=0.2)
        send_keys(KEY_SEQUENCES["F1"], wait_after=0.8)

        # 6.1.4 Qty Ordered UM スキップ
        logger.info(">> [STEP 6.1.4] Qty Ordered UM スキップ待機中...")
        ok = wait_predicate(lambda t, tl: not (re.search(r"[|│]\s*site\s*[|│]", tl) or re.search(r"item\s*numbe.*site", tl)) and ("avail. to allocate" in tl or "on hand:" in tl or "item width(mm):" in tl or "qty ordered um" in tl), timeout=8, desc="Step 6.1.4 Qty")
        log_screens.append(dump_screen(screen, "13_STEP6_QTY_ORDERED"))

        txt = get_clean_screen_text(screen).lower()
        if "item width(mm):" not in txt and "total qty (m2)" not in txt:
            logger.info(">> [STEP 6.1.4] Qty Ordered UM 欄を検知。<F1> 送信 (平米数自動計算スキップ)")
            send_keys(KEY_SEQUENCES["F1"], wait_after=0.8)

        # 6.1.4 No1 スリット設定画面 (Item Width)
        logger.info(">> [STEP 6.1.4 No1] スリット設定画面 (Item Width) 待機中...")
        ok = wait_predicate(lambda t, tl: "item width(mm):" in tl or "total qty (m2)" in tl, timeout=8, desc="Step 6.1.4 SL一覧")
        log_screens.append(dump_screen(screen, "14_STEP6_SLIT_MENU"))

        # 6.1.4-SL1 サブライン取得 F1 -> Enter (SL 1) -> Enter (Run 1) -> Len(m) へ
        logger.info(">> [STEP 6.1.4-SL1] <F1> 送信 (サブライン SL 1 開始)...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=0.8)
        logger.info(">> [STEP 6.1.4-SL1] <Enter> 1回目 (SL 1 確定)...")
        send_keys(b"\r", wait_after=0.4)
        logger.info(">> [STEP 6.1.4-SL1] <Enter> 2回目 (Run 1 確定 -> Len(m) 着地)...")
        send_keys(b"\r", wait_after=0.6)

        log_screens.append(dump_screen(screen, "15_STEP6_LEN_PROMPT"))

        # 6.2.0 Len(m) 長さ入力 -> Enter でロール明細ポップアップ自動オープン
        len_val = str(payload["items"][0]["length"])
        logger.info(f">> [STEP 6.2.0] Len(m) 欄に長さ '{len_val}' + <Enter> 送信...")
        send_keys(len_val.encode("ascii") + b"\r", wait_after=1.0)

        # ロール明細ポップアップ待機
        ok = wait_predicate(lambda t, tl: "rolls width(mm)" in tl or "ser t" in tl or "tot qty(m2)" in tl, timeout=8, desc="Step 6.2.1 ロール明細")
        log_screens.append(dump_screen(screen, "16_STEP6_ROLL_POPUP"))

        # 6.2.1 ロール明細: Ser 欄で Enter (Ser 1 / T 'C' 自動採番 -> Rolls へ移動)
        logger.info(">> [STEP 6.2.1] Ser 欄で <Enter> 送信 (Ser 1 採番 -> Rolls 欄へ移動)...")
        send_keys(b"\r", wait_after=0.6)

        # Rolls 入力 (本数 1 + Enter -> Width へ移動)
        qty_val = str(payload["items"][0]["quantity"])
        logger.info(f">> [STEP 6.2.1] Rolls 欄に本数 '{qty_val}' + <Enter> 送信...")
        send_keys(qty_val.encode("ascii") + b"\r", wait_after=0.6)

        # Width 入力 (幅 200 + Enter -> 次行 Ser へ移動)
        width_val = str(payload["items"][0]["width"])
        logger.info(f">> [STEP 6.2.1] Width 欄に幅 '{width_val}' + <Enter> 送信...")
        send_keys(width_val.encode("ascii") + b"\r", wait_after=0.8)
        log_screens.append(dump_screen(screen, "17_STEP6_AFTER_ROLL_WIDTH"))

        # ロール入力終了 -> F4
        logger.info(">> [STEP 6.2.1] 次行Serがアクティブの状態で <F4> 送信 (ロール入力完了)...")
        send_keys(KEY_SEQUENCES["F4"], wait_after=0.8)

        # Please confirm update -> F1 ('yes')
        logger.info(">> [STEP 6.2.1] 'Please confirm update' 待機中...")
        ok = wait_predicate(lambda t, tl: "please confirm update" in tl, timeout=8, desc="Step 6.2.1 Confirm")
        log_screens.append(dump_screen(screen, "18_STEP6_CONFIRM_UPDATE1"))
        
        logger.info(">> [STEP 6.2.1] 'yes' 確定のため <F1> 送信...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # SL一覧へ復帰確認
        logger.info(">> [STEP 6.1.4] SL一覧画面への復帰待機中...")
        ok = wait_predicate(lambda t, tl: "item width(mm):" in tl and "rolls width(mm)" not in tl and "please confirm update" not in tl, timeout=8, desc="Step 6.1.4 復帰")
        log_screens.append(dump_screen(screen, "19_STEP6_SL_BACK"))

        # 全長さ完了 -> SL一覧画面で F4
        logger.info(">> [STEP 6.1.4] 当該品番の全スリット完了のため SL一覧で <F4> 送信...")
        send_keys(KEY_SEQUENCES["F4"], wait_after=0.8)

        # Please confirm update -> Enter または F1
        logger.info(">> [STEP 6.1.4] 全明細 'Please confirm update' 待機中...")
        ok = wait_predicate(lambda t, tl: "please confirm update" in tl, timeout=8, desc="Step 6.1.4 Confirm2")
        log_screens.append(dump_screen(screen, "20_STEP6_CONFIRM_UPDATE2"))

        logger.info(">> [STEP 6.1.4] 'yes' 確定のため <Enter> 送信...")
        send_keys(b"\r", wait_after=1.0)

        # 6.2.3 Pricing Date 画面スキップ
        logger.info(">> [STEP 6.2.3] Pricing Date 画面待機中...")
        ok = wait_predicate(lambda t, tl: "pricing date:" in tl and ("sales order line" in tl or "credit terms int:" in tl), timeout=8, desc="Step 6.2.3 Pricing Date")
        log_screens.append(dump_screen(screen, "21_STEP6_PRICING_DATE"))
        
        logger.info(">> [STEP 6.2.3] Pricing Date スキップのため <F1> 送信...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # 6.2.4 値段入力画面 (List Price スキップ -> Price に単価入力)
        logger.info(">> [STEP 6.2.4] 値段入力画面待機中...")
        ok = wait_predicate(lambda t, tl: ("sales order line" in tl or "list price" in tl or "ln item number" in tl) and "pricing date:" not in tl and "tax usage:" not in tl, timeout=8, desc="Step 6.2.4 値段画面")
        log_screens.append(dump_screen(screen, "22_STEP6_PRICE_SCREEN"))

        logger.info(">> [STEP 6.2.4] List Price スキップのため <F1> 送信 (Price欄へ移動)...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=0.6)

        price_val = str(payload["items"][0]["price"])
        logger.info(f">> [STEP 6.2.4] Price 欄に単価 '{price_val}' + <F1> 送信...")
        send_keys(price_val.encode("ascii"), wait_after=0.2)
        send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)
        log_screens.append(dump_screen(screen, "23_STEP6_AFTER_PRICE_INPUT"))

        # 6.2.5 Tax ポップアップスキップ
        logger.info(">> [STEP 6.2.5] Tax ポップアップ待機中...")
        ok = wait_predicate(lambda t, tl: "tax usage:" in tl or "tax environment:" in tl or "tax class:" in tl or "transaction comments" in tl, timeout=8, desc="Step 6.2.5 Tax")
        log_screens.append(dump_screen(screen, "24_STEP6_TAX_POPUP"))
        
        txt = get_clean_screen_text(screen).lower()
        if "tax usage:" in txt or "tax environment:" in txt:
            logger.info(">> [STEP 6.2.5] Tax スキップのため <F1> 送信...")
            send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # 6.2.5 コメント画面スキップ
        logger.info(">> [STEP 6.2.5] Transaction Comments 画面待機中...")
        ok = wait_predicate(lambda t, tl: "transaction comments" in tl or ("sales order line" in tl and "tax usage:" not in tl), timeout=8, desc="Step 6.2.5 Comments")
        log_screens.append(dump_screen(screen, "25_STEP6_LINE_COMMENTS"))

        txt = get_clean_screen_text(screen).lower()
        if "transaction comments" in txt:
            logger.info(">> [STEP 6.2.5] 明細コメント スキップのため <F1> 送信...")
            send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        # 6.1.0 メインメニュー復帰
        logger.info(">> [STEP 6.1.0] メインメニュー (Sales Order Line) 復帰待機中...")
        ok = wait_predicate(lambda t, tl: ("sales order line" in tl or "ln item number" in tl) and "transaction comments" not in tl, timeout=8, desc="Step 6.1.0 復帰")
        log_screens.append(dump_screen(screen, "26_STEP6_LINE_MAIN_BACK"))

        # =========================================================================
        # STEP 6.3.0: 最終合計画面遷移 ＆ 注文確定
        # =========================================================================
        logger.info(">> [STEP 6.3.0] 全明細完了。最終合計画面へ進むため <F4> 送信...")
        send_keys(KEY_SEQUENCES["F4"], wait_after=1.0)

        # F4 で合計画面に進まなかった場合、F2 x 2 も試行 (ユーザー指示: F2を2回か押すと次の画面に進みます)
        txt = get_clean_screen_text(screen).lower()
        if not ("line total:" in txt or "total tax:" in txt or "enter data or press f4" in txt):
            logger.info(">> [STEP 6.3.0] F4未到達のため <F2> 2回を試行...")
            send_keys(KEY_SEQUENCES["F2"], wait_after=0.4)
            send_keys(KEY_SEQUENCES["F2"], wait_after=1.0)

        logger.info(">> [STEP 6.3.0] 最終合計画面 (Order Totals) 待機中...")
        ok = wait_predicate(lambda t, tl: "line total:" in tl or "total tax:" in tl or "enter data or press f4" in tl, timeout=8, desc="Step 6.3.0 最終合計")
        log_screens.append(dump_screen(screen, "27_STEP630_TOTALS"))

        # F1 x 1回目
        logger.info(">> [STEP 6.3.0] 注文確定 1回目 <F1> 送信...")
        send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        txt = get_clean_screen_text(screen).lower()
        if "press space" not in txt and "space bar" not in txt and "mfmenu" not in txt:
            logger.info(">> [STEP 6.3.0] 注文確定 2回目 <F1> 送信 (最終保存)...")
            send_keys(KEY_SEQUENCES["F1"], wait_after=1.0)

        log_screens.append(dump_screen(screen, "28_STEP630_AFTER_F1"))

        # Press space bar to continue 待機
        logger.info(">> [STEP 6.3.0] 'Press space bar to continue' 待機中...")
        ok = wait_predicate(lambda t, tl: "press space" in tl or "space bar" in tl or "mfmenu" in tl or "main menu" in tl, timeout=8, desc="Step 6.3.0 Space待機")

        txt = get_clean_screen_text(screen).lower()
        if "press space" in txt or "space bar" in txt:
            logger.info(">> [STEP 6.3.0] スペースキー ' ' (改行なし) を送信...")
            send_keys(b" ", wait_after=1.0)

        # メインメニュー復帰
        logger.info(">> [STEP 6.3.0] メインメニュー (mfmenu) 復帰待機中...")
        ok = wait_predicate(lambda t, tl: "mfmenu" in tl or "main menu" in tl or "sales order maintenance" not in tl, timeout=8, desc="Step 6.3.0 mfmenu復帰")
        log_screens.append(dump_screen(screen, "29_STEP630_FINAL_MENU"))

        logger.info(f"✅ 全工程正常完了！ 採番された Order ID: 【{assigned_order_id}】")

        shell.close()
        ssh.close()

        # ログ出力保存
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(log_screens))
        logger.info(f"全画面ログ保存完了: {log_path}")

        return assigned_order_id

    except Exception as e:
        logger.error(f"実行中エラー検知: {e}")
        try:
            logger.info("緊急安全脱出シーケンス: F4 x 6 送信中...")
            for _ in range(6):
                send_keys(KEY_SEQUENCES["F4"], wait_after=0.3)
            log_screens.append(dump_screen(screen, "99_ERROR_EMERGENCY_EXIT"))
        except Exception:
            pass

        try:
            shell.close()
            ssh.close()
        except Exception:
            pass

        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(log_screens))

        raise e

if __name__ == "__main__":
    try:
        assigned_id = run_live_execution()
        print(f"\n=======================================================")
        print(f" SUCCESS: ASSIGNED ORDER ID = {assigned_id}")
        print(f"=======================================================\n")
    except Exception as e:
        print(f"\n=======================================================")
        print(f" ERROR: {e}")
        print(f" Log saved to: {log_path}")
        print(f"=======================================================\n")
        sys.exit(1)
