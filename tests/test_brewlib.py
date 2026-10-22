import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brewlib


class RemovalClosure(unittest.TestCase):
    deps = {"app": ["lib", "util"], "lib": ["base"], "util": ["base"], "base": [], "other": ["base"]}

    def test_removes_unneeded_chain(self):
        r = brewlib.removal_closure(["app"], {**self.deps, "other": []}, {"app", "other"})
        self.assertEqual(r["also"], ["base", "lib", "util"])
        self.assertEqual(r["blocked"], {})

    def test_keeps_shared_dependency(self):
        r = brewlib.removal_closure(["app"], self.deps, {"app", "other"})
        self.assertEqual(r["also"], ["lib", "util"])  # base wird noch von other gebraucht

    def test_keeps_user_installed(self):
        r = brewlib.removal_closure(["app"], self.deps, {"app", "other", "lib"})
        self.assertEqual(r["also"], ["util"])

    def test_blocked(self):
        r = brewlib.removal_closure(["lib"], self.deps, {"app", "other"})
        self.assertEqual(r["blocked"], {"lib": ["app"]})


class Brewfile(unittest.TestCase):
    text = 'tap "user/tap"\nbrew "wget"\nbrew "user/tap/tool"\ncask "firefox"\nmas "X", id: 1\n# brew "no"\n'

    def test_parse(self):
        p = brewlib.parse_brewfile(self.text)
        self.assertEqual(p["brew"], ["wget", "user/tap/tool"])
        self.assertEqual(p["cask"], ["firefox"])
        self.assertEqual(p["tap"], ["user/tap"])
        self.assertEqual(p["mas"], ["X"])

    def test_diff(self):
        p = brewlib.parse_brewfile(self.text)
        d = brewlib.diff_brewfile(p, {"wget", "jq", "libx"}, {"vlc"}, {"homebrew/core"}, requested={"wget", "jq"})
        self.assertEqual(d["missing"]["brew"], ["user/tap/tool"])
        self.assertEqual(d["missing"]["cask"], ["firefox"])
        self.assertEqual(d["extra"]["brew"], ["jq"])  # libx ist nur Abhängigkeit
        self.assertEqual(d["extra"]["cask"], ["vlc"])
        self.assertEqual(d["unsupported"], 1)

    def test_make_roundtrip(self):
        items = [{"kind": "formula", "name": "wget", "full_name": "wget", "on_request": True},
                 {"kind": "formula", "name": "dep", "full_name": "dep", "on_request": False},
                 {"kind": "cask", "name": "firefox", "full_name": "firefox", "on_request": True}]
        p = brewlib.parse_brewfile(brewlib.make_brewfile(items, ["a/b"]))
        self.assertEqual(p, {"tap": ["a/b"], "brew": ["wget"], "cask": ["firefox"]})


class Names(unittest.TestCase):
    def test_valid(self):
        for n in ("wget", "node@20", "user/tap/tool", "python@3.13", "a+b"):
            self.assertTrue(brewlib.valid_name(n), n)

    def test_invalid(self):
        for n in ("", "-rf", "a b", "a;b", "../x", "a//b", "a/b/c/d", "$(x)", None, "--force"):
            self.assertFalse(brewlib.valid_name(n), n)


if __name__ == "__main__":
    unittest.main()
