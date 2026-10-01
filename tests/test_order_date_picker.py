"""No-network tests for range boundaries and atomic date application."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from order_entry import parse_typed_date, format_order_date
from order_date_picker import visible_interval, OrderDateRangePicker


class DateRangeTests(unittest.TestCase):
    def test_reverse_dates_keep_same_highlight_interval(self):
        self.assertEqual(visible_interval(date(2026, 10, 8), date(2026, 10, 3), 10, 2026),
                         [date(2026, 10, day) for day in range(3, 9)])

    def test_equal_dates_and_cross_month_leap_day(self):
        self.assertEqual(visible_interval(date(2026, 10, 3), date(2026, 10, 3), 10, 2026), [date(2026, 10, 3)])
        self.assertIn(date(2028, 2, 29), visible_interval(date(2028, 2, 28), date(2028, 3, 2), 2, 2028))

    def test_long_interval_only_decorates_visible_cells(self):
        for month, year in ((10, 2026), (12, 9999), (1, 1)):
            self.assertLessEqual(len(visible_interval(date.min, date.max, month, year)), 42)

    def picker(self):
        fields = {name: SimpleNamespace(value=date(2026, 10, 2), variable=Mock(), entry=Mock(), popup=None)
                  for name in OrderDateRangePicker.KEYS}
        picker = OrderDateRangePicker(fields['due_date'], fields['required_date'], {'error': '#EF4444'}, '',
                                      parse_typed_date, format_order_date)
        picker.entries = {name: Mock() for name in picker.KEYS}
        picker.variables = {name: Mock() for name in picker.KEYS}
        picker.variables['due_date'].get.return_value = '2026/10/5'
        picker.variables['required_date'].get.return_value = '2026/10/3'
        picker.anchor = fields['due_date']
        picker.close = Mock()
        return picker, fields

    def test_commit_both_dates_preserves_business_roles(self):
        picker, fields = self.picker()
        picker.commit()
        self.assertEqual(fields['due_date'].value, date(2026, 10, 5))
        self.assertEqual(fields['required_date'].value, date(2026, 10, 3))
        fields['required_date'].variable.set.assert_called_once_with('2026/10/3 (土)')
        picker.close.assert_called_once()

    def test_invalid_second_date_leaves_both_values_unchanged(self):
        picker, fields = self.picker()
        picker.variables['required_date'].get.return_value = '2026/02/30'
        picker.commit()
        self.assertTrue(all(field.value == date(2026, 10, 2) for field in fields.values()))
        self.assertTrue(all(not field.variable.set.called for field in fields.values()))
        picker.close.assert_not_called()
