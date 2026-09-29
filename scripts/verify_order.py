"""ネットワーク・GUIなしの回帰試験と、未解決の受入条件を実行する。"""

import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGRESSION = [
    "tests.test_order_consistency", "tests.test_order_replay", "tests.test_order_result_comparison",
    "tests.test_order_entry.OrderDataTests", "tests.test_order_entry.ControlTapTests",
    "tests.test_order_entry.ShortcutModifierTests",
    "tests.test_step6_order_automation.Step6GroupingTests",
    "tests.test_step6_order_automation.ScreenTextCleaningTests",
    "tests.test_step6_order_automation.AutomationControllerExecutionTests",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", action="store_true", help="未解決の安全条件も実行。失敗時は終了コード1")
    parser.add_argument("--report", type=Path, help="結果JSONの保存先（例 verification-output/result.json）")
    args = parser.parse_args()
    names = REGRESSION + (["tests.order_acceptance_cases"] if args.acceptance else [])
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    successful = result.wasSuccessful() and not result.skipped and not result.expectedFailures
    report = dict(
        mode="regression_and_acceptance" if args.acceptance else "regression_only",
        successful=successful, tests=result.testsRun,
        failures=[{"test": test.id(), "detail": trace} for test, trace in result.failures],
        errors=[{"test": test.id(), "detail": trace} for test, trace in result.errors],
        skipped=[{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        expected_failures=[test.id() for test, _ in result.expectedFailures],
        live_server_verified=False,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("実サーバー登録結果は未検証です。回帰試験の成功だけでは運用受入の合格になりません。")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
