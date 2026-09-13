import unittest

from run_sample import STEPS


class RunSampleTest(unittest.TestCase):
    def test_placeholder_arguments_are_allowed(self):
        solar = dict(STEPS)["solar"]
        self.assertIn(None, solar)
        self.assertTrue(all(isinstance(x, (str, type(None))) for x in solar))

    def test_nearby_collection_precedes_parse(self):
        names = [name for name, _ in STEPS]
        self.assertLess(names.index("collect_nearby_asos"), names.index("parse_nearby_asos"))


if __name__ == "__main__":
    unittest.main()
