import tempfile
import unittest
from pathlib import Path
from order_history import OrderHistory, render_order, validate_template, display_width


class OrderHistoryTests(unittest.TestCase):
    def payload(self):
        return dict(customer_name="顧客A", ship_to="工場B", required_date="2026-10-02", due_date="2026-10-01",
                    remarks="${価格}", items=[dict(product_name="製品A", width="200", length="600", quantity=2, price="150"),
                                              dict(product_name="製品B", width="300", length="400", quantity=1, price="120")])

    def test_default_multiple_rows_and_japanese_date(self):
        self.assertEqual(render_order(self.payload(), "SO123"),
            "顧客A\nSO123\n製品A  200 x 600 x 2 @150\n製品B  300 x 400 x 1 @120\n2026年10月2日 (金) 工場B着 で手配しました。")

    def test_custom_template_alias_and_literal_payload(self):
        self.assertEqual(render_order(self.payload(), "SO123", "${処理した注文のOrder ID}\n${Remarks}\n${Require Date}\n${巾}"),
                         "SO123\n${価格}\n2026年10月2日 (金)\n200\n300")
        for template in ("", "${誤字}", "${顧客名"):
            with self.assertRaises(ValueError):
                validate_template(template)

    def test_persistence_snapshot_and_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.sqlite3"
            payload = self.payload()
            OrderHistory(path).append(payload, "SO123")
            payload["items"][0]["quantity"] = 99
            store = OrderHistory(path)
            order_id, saved = store.get(store.page()[0][0])
            self.assertEqual(order_id, "SO123")
            self.assertEqual(saved["items"][0]["quantity"], 2)
            for i in range(101):
                store.append(payload, str(i))
            self.assertEqual(len(store.page()), 100)
            self.assertEqual(len(store.page(100)), 2)
            self.assertEqual(store.page()[0][2], "100")
            self.assertEqual(len(store.page(limit=None)), 102)

    def test_fallback_ship_to_and_customer_name_from_address_or_code(self):
        demo_payload = {
            "customer_code": "20000600",
            "ship_to_code": "20000601",
            "address": "960-8201\nTOPPANインフォメディア(株)福島工場\n福島県福島市岡島字宮田30-2\n\n\n024-536-6111",
            "required_date": "2026-10-04",
            "items": [{"product_name": "BW0100D", "width": "200", "length": "600", "quantity": 1, "price": "200"}]
        }
        rendered = render_order(demo_payload, "SO199729")
        self.assertIn("TOPPANインフォメディア株式会社", rendered)
        self.assertIn("TOPPANインフォメディア(株)福島工場着 で手配しました。", rendered)

    def test_duplicate_product_name_suppression_on_consecutive_lines(self):
        payload = {
            "customer_name": "顧客A",
            "ship_to": "工場B",
            "required_date": "2026-10-02",
            "items": [
                {"product_name": "製品A", "width": "200", "length": "600", "quantity": 2, "price": "150"},
                {"product_name": "製品A", "width": "300", "length": "600", "quantity": 1, "price": "150"},
                {"product_name": "製品B", "width": "400", "length": "500", "quantity": 3, "price": "200"},
                {"product_name": "製品B", "width": "500", "length": "500", "quantity": 1, "price": "200"},
                {"product_name": "製品A", "width": "200", "length": "600", "quantity": 1, "price": "150"},
            ]
        }
        rendered = render_order(payload, "SO123")
        expected_lines = [
            "顧客A",
            "SO123",
            "製品A  200 x 600 x 2 @150",
            "       300 x 600 x 1 @150",
            "製品B  400 x 500 x 3 @200",
            "       500 x 500 x 1 @200",
            "製品A  200 x 600 x 1 @150",
            "2026年10月2日 (金) 工場B着 で手配しました。"
        ]
        self.assertEqual(rendered, "\n".join(expected_lines))

    def test_item_code_and_due_date_template(self):
        template = "${ItemCode}\n${Due date}"
        rendered = render_order(self.payload(), "SO123", template)
        self.assertEqual(rendered, "製品A\n製品B\n2026年10月1日 (木)")

    def test_duplicate_item_code_suppression(self):
        payload = {
            "customer_name": "顧客A",
            "items": [
                {"product_name": "BW0100D", "width": "200"},
                {"product_name": "BW0100D", "width": "300"},
                {"product_name": "BW0200", "width": "400"},
            ]
        }
        rendered = render_order(payload, "SO1", "${ItemCode} ${幅}")
        self.assertEqual(rendered, "BW0100D 200\n        300\nBW0200 400")
        lines = rendered.splitlines()
        self.assertEqual(display_width(lines[0].split("200")[0]),
                         display_width(lines[1].split("300")[0]))

    def test_duplicate_product_display_uses_measured_tab_stops(self):
        payload = dict(items=[dict(product_name="BW0100D", width="200"),
                              dict(product_name="BW0100D", width="300")])
        stops = {}
        measure = lambda text: sum(9 if char == "W" else 5 for char in text)
        rendered = render_order(payload, "SO1", "品目: ${ItemCode}  ${幅}",
                                measure=measure, tabstops=stops)
        self.assertEqual(rendered, "品目: BW0100D  200\n品目: \t300")
        self.assertEqual(stops, {2: [measure("品目: BW0100D  ")]})

