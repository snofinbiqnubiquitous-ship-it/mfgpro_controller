"""独立に読み戻したQAD登録結果と注文JSONを照合する。通信・DB書込みは行わない。"""

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path


HEADER_FIELDS = ("order_id", "customer_code", "bill_to_code", "ship_to_code", "order_date",
                 "required_date", "due_date", "site", "purchase_order", "remarks", "so_comment")


def normalize_order(data):
    if not isinstance(data, dict):
        raise ValueError("注文はJSONオブジェクトで指定してください")
    header = {}
    for field in HEADER_FIELDS:
        value = data.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field}: 文字列フィールドが必要です（空欄も明示）")
        value = value.replace("\r\n", "\n").strip()
        if field in ("order_id", "customer_code", "bill_to_code", "ship_to_code", "site") and not value:
            raise ValueError(f"{field}: 空欄は照合できません")
        if field in ("order_date", "required_date", "due_date"):
            value = date.fromisoformat(value).isoformat()
        header[field] = value
    rows = data.get("items")
    if not isinstance(rows, list) or not rows:
        raise ValueError("items: 1行以上の明細が必要です")
    quantities = defaultdict(Decimal)
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("product_name"), str) or not row["product_name"].strip():
            raise ValueError(f"items[{index}]: 製品名が必要です")
        numbers = {}
        for field in ("width", "length", "price", "quantity"):
            try:
                number = Decimal(str(row[field]))
            except (KeyError, InvalidOperation, ValueError):
                raise ValueError(f"items[{index}].{field}: 数値が必要です") from None
            if not number.is_finite() or number < 0 or (field != "price" and number == 0):
                raise ValueError(f"items[{index}].{field}: 不正な数値です")
            if number.adjusted() > 20 or number.as_tuple().exponent < -10:
                raise ValueError(f"items[{index}].{field}: 桁数が範囲外です")
            if field == "quantity" and number != number.to_integral_value():
                raise ValueError(f"items[{index}].quantity: 本数は整数が必要です")
            numbers[field] = number
        # 製品・幅・長さ・価格・本数を独立に比較。製品コード側のgroup_order_itemsは使わない。
        site = row.get("site", header["site"])
        if not isinstance(site, str) or not site.strip():
            raise ValueError(f"items[{index}].site: Siteが必要です")
        key = (row["product_name"].strip(), numbers["width"], numbers["length"], numbers["price"], site.strip())
        quantities[key] += numbers["quantity"]
    return header, quantities


def compare_orders(expected, actual):
    expected_header, expected_items = normalize_order(expected)
    actual_header, actual_items = normalize_order(actual)
    differences = []
    if actual.get("committed") is not True:
        differences.append("committed: サーバー側での確定を示すtrueが必要です")
    for field in HEADER_FIELDS:
        if expected_header[field] != actual_header[field]:
            differences.append(f"{field}: expected={expected_header[field]!r}, actual={actual_header[field]!r}")
    for key in sorted(expected_items.keys() | actual_items.keys()):
        left, right = expected_items.get(key, 0), actual_items.get(key, 0)
        if left != right:
            differences.append(f"items{key}: expected quantity={left}, actual quantity={right}")
    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args()
    try:
        expected = json.loads(args.expected.read_text(encoding="utf-8-sig"))
        actual = json.loads(args.actual.read_text(encoding="utf-8-sig"))
        differences = compare_orders(expected, actual)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "mismatch" if differences else "match",
                      "differences": differences}, ensure_ascii=False, indent=2))
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
