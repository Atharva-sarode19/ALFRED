import unittest
from datetime import date

from app.tools.date_math import calculate_age, parse_date
from app.tools.datetime_tool import DateTimeTool
from app.tools.registry import ToolRegistry


class AgeCalculationTests(unittest.TestCase):
    def test_birthday_already_passed_this_year(self):
        self.assertEqual(calculate_age(date(2007, 5, 19), date(2026, 11, 24))["years"], 19)

    def test_birthday_not_yet_reached_this_year(self):
        self.assertEqual(calculate_age(date(2007, 12, 25), date(2026, 11, 24))["years"], 18)

    def test_birthday_is_today(self):
        result = calculate_age(date(2000, 11, 24), date(2026, 11, 24))
        self.assertEqual(result["years"], 26)
        self.assertTrue(result["birthday_today"])
        self.assertEqual(result["days_until_next_birthday"], 0)
        self.assertEqual((result["months"], result["days"]), (0, 0))

    def test_day_before_birthday(self):
        result = calculate_age(date(2000, 11, 25), date(2026, 11, 24))
        self.assertEqual(result["years"], 25)
        self.assertEqual(result["days_until_next_birthday"], 1)
        self.assertFalse(result["birthday_today"])

    def test_same_month_earlier_day_and_later_day(self):
        self.assertEqual(calculate_age(date(2000, 11, 1), date(2026, 11, 24))["years"], 26)
        self.assertEqual(calculate_age(date(2000, 11, 30), date(2026, 11, 24))["years"], 25)

    def test_leap_day_birthday_in_non_leap_year(self):
        born = date(2000, 2, 29)
        self.assertEqual(calculate_age(born, date(2023, 2, 28))["years"], 22)
        self.assertEqual(calculate_age(born, date(2023, 3, 1))["years"], 23)
        self.assertEqual(calculate_age(born, date(2023, 3, 2))["next_birthday"], "2024-02-29")

    def test_leap_day_birthday_in_leap_year(self):
        result = calculate_age(date(2000, 2, 29), date(2024, 2, 29))
        self.assertEqual(result["years"], 24)
        self.assertTrue(result["birthday_today"])

    def test_leap_day_next_birthday_is_march_first_in_common_year(self):
        self.assertEqual(calculate_age(date(2000, 2, 29), date(2025, 1, 10))["next_birthday"], "2025-03-01")

    def test_newborn_and_months_days(self):
        self.assertEqual(calculate_age(date(2026, 11, 24), date(2026, 11, 24))["years"], 0)
        result = calculate_age(date(2007, 5, 19), date(2026, 11, 24))
        self.assertEqual((result["years"], result["months"], result["days"]), (19, 6, 5))

    def test_month_end_days(self):
        result = calculate_age(date(2000, 1, 31), date(2026, 3, 1))
        self.assertEqual((result["years"], result["months"]), (26, 1))
        self.assertGreaterEqual(result["days"], 0)

    def test_many_years_and_months_match_reference(self):
        for birth_year in (1950, 1983, 1999, 2012):
            for month in range(1, 13):
                for today in (date(2026, month, 1), date(2026, month, 15), date(2026, 12, 31)):
                    birth = date(birth_year, 3, 14)
                    expected = today.year - birth.year - ((today.month, today.day) < (3, 14))
                    self.assertEqual(calculate_age(birth, today)["years"], expected)

    def test_future_birth_date_rejected(self):
        with self.assertRaises(ValueError):
            calculate_age(date(2030, 1, 1), date(2026, 11, 24))

    def test_parse_date_formats(self):
        expected = date(2007, 5, 19)
        for text in ("2007-05-19", "19 May 2007", "May 19, 2007", "19th May 2007", "the 19th of May 2007", "19 may 2007"):
            self.assertEqual(parse_date(text), expected, text)
        self.assertIsNone(parse_date("someday"))


class AgeToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(DateTimeTool())

    async def test_age_with_explicit_as_of_date(self):
        result = await self.registry.execute(
            "datetime", {"action": "age", "birth_date": "2007-05-19", "as_of_date": "2026-11-24"}
        )
        self.assertTrue(result.success)
        self.assertEqual(result.data["years"], 19)

    async def test_age_defaults_to_today(self):
        result = await self.registry.execute("datetime", {"action": "age", "birth_date": "2000-01-01", "timezone": "UTC"})
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.data["years"], 25)

    async def test_age_requires_birth_date_and_valid_input(self):
        self.assertFalse((await self.registry.execute("datetime", {"action": "age"})).success)
        bad = await self.registry.execute("datetime", {"action": "age", "birth_date": "not a date"})
        self.assertFalse(bad.success)
        future = await self.registry.execute("datetime", {"action": "age", "birth_date": "2999-01-01"})
        self.assertFalse(future.success)
