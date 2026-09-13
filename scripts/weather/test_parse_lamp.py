import unittest
from parse_lamp import parse


class LampParserTests(unittest.TestCase):
    def test_parses_station_cycle_and_numeric_categorical_fields(self):
        text = """ KNYC   GFS LAMP GUIDANCE   9/12/2026  2000 UTC
 UTC  21 22
 TMP   70 71
 SKY   BKN CLR
"""
        rows = parse(text, "raw", "hash", "2026-09-12T20:05:00Z")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["valid_time_utc"], "2026-09-12T21:00:00Z")
        self.assertEqual(rows[0]["value"], 70.0)
        self.assertEqual(rows[2]["value"], "BKN")
        self.assertEqual(rows[0]["raw_sha256"], "hash")


if __name__ == "__main__": unittest.main()
