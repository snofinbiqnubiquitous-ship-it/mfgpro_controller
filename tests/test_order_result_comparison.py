import copy
import unittest
from scripts.compare_order_result import compare_orders


class ReadbackComparisonTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(order_id="SO123456", customer_code="TESTC", ship_to_code="TESTD",
                             bill_to_code="TESTC", order_date="2026-09-29", site="CB2",
                             required_date="2026-10-09", due_date="2026-10-07",
                             purchase_order="TEST-PO", remarks="", so_comment="1行目\n2行目",
                             items=[dict(product_name="TEST", width="1000", length="500",
                                         price="100.00", quantity=3)])
        self.actual = copy.deepcopy(self.expected)
        self.actual["committed"] = True

    def test_equal_values_with_different_decimal_representation_and_roll_rows(self):
        self.actual["items"][0].update(price="100", width="1000.0", quantity=1)
        self.actual["items"].append(dict(self.actual["items"][0], quantity=2))
        self.assertEqual(compare_orders(self.expected, self.actual), [])

    def test_every_header_difference_is_detected(self):
        for field in ("order_id", "customer_code", "bill_to_code", "ship_to_code", "site",
                      "purchase_order", "remarks", "so_comment", "order_date", "required_date", "due_date"):
            with self.subTest(field=field):
                actual = copy.deepcopy(self.actual)
                actual[field] = "2026-10-10" if field.endswith("date") else "DIFFERENT"
                self.assertTrue(any(line.startswith(field + ":") for line in compare_orders(self.expected, actual)))

    def test_duplicate_missing_or_changed_detail_is_detected(self):
        for field, value in (("quantity", 6), ("width", "500"), ("length", "1000"),
                             ("price", "101"), ("product_name", "OTHER"), ("site", "OTHER")):
            with self.subTest(field=field):
                actual = copy.deepcopy(self.actual)
                actual["items"][0][field] = value
                self.assertTrue(compare_orders(self.expected, actual))
        self.actual["items"].append(copy.deepcopy(self.actual["items"][0]))
        self.assertTrue(compare_orders(self.expected, self.actual))

    def test_missing_fields_and_invalid_values_cannot_pass(self):
        for field in ("order_id", "so_comment", "items"):
            with self.subTest(field=field):
                actual = copy.deepcopy(self.actual)
                del actual[field]
                with self.assertRaises(ValueError):
                    compare_orders(self.expected, actual)
        for value in ("NaN", "Infinity", "-1", "1.5"):
            with self.subTest(quantity=value):
                actual = copy.deepcopy(self.actual)
                actual["items"][0]["quantity"] = value
                with self.assertRaises(ValueError):
                    compare_orders(self.expected, actual)

    def test_unconfirmed_commit_cannot_pass(self):
        for value in (False, None, "true", 1):
            self.actual["committed"] = value
            self.assertTrue(compare_orders(self.expected, self.actual))
