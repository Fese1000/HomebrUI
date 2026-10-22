import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import updater


class Versions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.10"), (1, 10))
        self.assertIsNone(updater.parse_version("latest"))
        self.assertIsNone(updater.parse_version("v1.2-beta"))

    def test_compare_numeric_not_text(self):
        self.assertGreater(updater.parse_version("1.10"), updater.parse_version("1.9"))


class Download(unittest.TestCase):
    def test_rejects_foreign_url_and_missing_digest(self):
        for asset in ({"url": "https://evil.example/HomebrUI.dmg", "digest": "sha256:00", "size": 1},
                      {"url": updater.DL_PREFIX + "v1/x.dmg", "digest": None, "size": 1},
                      {"url": updater.DL_PREFIX + "v1/x.dmg", "digest": "md5:00", "size": 1}):
            with self.assertRaises(ValueError):
                updater._download(asset, "/dev/null")

    def test_source_checkout_cannot_install(self):
        ok, why = updater.can_install()
        self.assertFalse(ok)
        self.assertEqual(why, "source")


if __name__ == "__main__":
    unittest.main()
