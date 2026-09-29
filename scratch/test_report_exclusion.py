import unittest
import sys, os
from pathlib import Path

repo_dir = r"c:\Users\0138018\.antigravity\mfgpro_controller"
sys.path.insert(0, repo_dir)

# 自作モダンターミナル.pyw は __main__ で Tk を起動するため、クラスのみを安全にテストできるようにモックを用意
import re

def check_screen_is_report(screen_text: str, order_panel_visible: bool = False, is_automating: bool = False) -> bool:
    """自作モダンターミナル.pyw の _check_is_report_output と同一ロジックをスタンドアロンで検証"""
    if order_panel_visible or is_automating:
        return False

    lines = screen_text.splitlines()
    if len(lines) < 3:
        return False

    full_lower = screen_text.lower()

    maintenance_keywords = [
        "maintenance", "99.7.1.1", "99.7.1", "sales order", "purchase order",
        "sosomt.p", "sordmt.p", "pomt.p", "poodmt.p", "item width(mm)",
        "sales order line", "sold-to:", "bill-to:", "ship-to:", "order date:",
        "required date:", "due date:", "rolls width(mm)", "sl run", "exact:yes",
        "tot qty(m2)", "transaction comments", "print on quote:", "category=",
        "enter data or press f4", "ln item number", "qty ordered um", "create wo:",
        "pricing date:", "list price", "tax usage:"
    ]
    if any(k in full_lower for k in maintenance_keywords):
        return False

    if re.search(r'\b\w*mt\.p\b', full_lower):
        return False

    is_input_prompt_screen = (
        "output:" in full_lower or "output :" in full_lower
        or "batch id:" in full_lower or "batch id :" in full_lower
        or "enter data or press f4" in full_lower
        or ("from:" in full_lower and "to:" in full_lower)
        or "f1=go" in full_lower
        or "f4=end" in full_lower
    )
    if is_input_prompt_screen:
        return False

    sep_row_idx = -1
    sep_pattern = re.compile(r'[-─]{2,}\s+[-─]{2,}')
    for idx, line in enumerate(lines):
        clean = line.replace("│", " ").strip()
        if any(c in line for c in ("┌", "┐", "└", "┘", "├", "┤")):
            continue
        stripped = line.strip()
        if stripped.startswith("│") and stripped.endswith("│"):
            continue
        if sep_pattern.search(clean) or clean.count("---") >= 2 or (clean.startswith("---") and len(clean) >= 15):
            sep_row_idx = idx
            break

    if sep_row_idx == -1:
        return False

    is_report_header = (
        any(h in full_lower for h in ["page:", "page :", "report", "inquiry", "browse", "listing", "register"])
        or "end of report" in full_lower
    )

    has_prompt = (
        any(p in full_lower for p in ["press space", "space to continue", "space bar", "more...", "-- more --", "end of report", "return to exit"])
        or any(p in screen_text for p in ["スペース", "ｽﾍﾟｰｽ", "継続", "続行", "終了するには", "レポート終了"])
    )

    if has_prompt and (is_report_header or sep_row_idx != -1):
        return True

    if is_report_header and sep_row_idx >= 1 and sep_row_idx < len(lines) - 1:
        data_lines = [l for l in lines[sep_row_idx + 1:] if l.strip() and not l.strip().startswith("│")]
        if len(data_lines) >= 1:
            return True

    return False


# テスト対象のQAD 99.7.1.1 画面群
SCREEN_610 = """xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26
┌──────────────────────────────────────────────────────────────────────────────┐
│ Sales Order: SO199302 Sold-To: 20019500 Ln Format S/M: Single                │
└──────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────── Sales Order Line ──────────────────────────────┐
│ Ln Item Number        Qty Ordered UM     List Price Discount           Price │
│─── ────────────────── ─────────── ── ────────────── ──────── ─────────────── │
│  1 OZS200                   105.0 M2         320.00      0.0          320.00 │
└──────────────────────────────────────────────────────────────────────────────┘
F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"""

SCREEN_614_SLIT = """xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26
┌──────────Item Width(mm):1530 Exact:yes TOTAL QTY (M2) 105──────────┐
│ SL Run     Len(m) Exact Cum Width(mm) Cum Tot Qty(M2)              │
│─── ─── ────────── ───── ───────────── ───────────────              │
│  1   1     600.00 yes            0.00            0.00              │
└────────────────────────────────────────────────────────────────────┘
F1=Go 2=Hlp 3=Ins 4=End 6=Mnu 7=Rcl 8=Clr 9=Prev 10=Next 11=Buf"""

SCREEN_621_ROLL = """xxsosomt.p b+            99┌────────────────────────────────────┐     09/28/26
┌──────────────────────────│Ser T    Rolls Width(mm) Tot Qty(M2)│──────────────┐
│ Sales Order: SO199302 Sol│─── ─ ──────── ───────── ───────────│              │
└──────────────────────────│                                    │──────────────┘"""

SCREEN_630_TOTALS = """xxsosomt.p b+            99.7.1.1 Sales Order Maintenance             09/28/26
┌──────────────────────────────────────────────────────────────────────────────┐
│ Order: SO199302  Sold-To: 20019500  Bill To: 20019500  Ship-To: 20019583     │
└──────────────────────────────────────────────────────────────────────────────┘
Enter data or press F4 to end."""

# 正当なレポート画面 (3.6.1 在庫照会等)
SCREEN_VALID_REPORT = """xxinbr.p                 3.6.1 Item Inventory Report                  09/28/26
Page: 1                                                               Date: 09/28/26
Item Number          Site Loc   Qty On Hand   Qty Allocated  Qty Available
-------------------  ---- ----  ------------  -------------  -------------
15666                CB2  RAW       10500.00           0.00       10500.00
15667                CB2  RAW         200.00           0.00         200.00
Press space bar to continue."""

class TestReportExclusion(unittest.TestCase):
    def test_99_7_1_1_screens_strictly_excluded(self):
        self.assertFalse(check_screen_is_report(SCREEN_610), "6.1.0 画面がレポートと誤判定されてはならない")
        self.assertFalse(check_screen_is_report(SCREEN_614_SLIT), "スリット設定画面がレポートと誤判定されてはならない")
        self.assertFalse(check_screen_is_report(SCREEN_621_ROLL), "ロール設定画面がレポートと誤判定されてはならない")
        self.assertFalse(check_screen_is_report(SCREEN_630_TOTALS), "最終合計画面がレポートと誤判定されてはならない")

    def test_sidebar_open_excludes_everything(self):
        self.assertFalse(check_screen_is_report(SCREEN_VALID_REPORT, order_panel_visible=True), "注文サイドバー表示中はレポート検知してはならない")

    def test_valid_report_still_detected(self):
        self.assertTrue(check_screen_is_report(SCREEN_VALID_REPORT), "正当なレポート画面は検出されなければならない")

if __name__ == "__main__":
    unittest.main()
