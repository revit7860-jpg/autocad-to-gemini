"""Tests du passage du facteur d'insertion jusqu'à la commande AutoCAD."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "autocad_bridge_under_test", PROJECT / "src" / "autocad_bridge.py"
)
acad = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acad)


class FakeWindow:
    isMinimized = False

    def activate(self):
        return None


class FakePyAutoGUI:
    def hotkey(self, *args):
        return None

    def press(self, *args):
        return None


class InsertScaleTests(unittest.TestCase):
    def setUp(self):
        self.clipboard = []
        self.pyperclip = types.SimpleNamespace(copy=self.clipboard.append)
        self.patches = [
            mock.patch.object(acad, "_acad_com", return_value=None),
            mock.patch.object(acad, "find_autocad_window", return_value=FakeWindow()),
            mock.patch.object(acad, "pyautogui", FakePyAutoGUI()),
            mock.patch.dict(sys.modules, {"pyperclip": self.pyperclip}),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_scale_is_sent_to_imageattach(self):
        ok, message = acad.insert_render("C:/work/render.png", scale=2.5)
        self.assertTrue(ok, message)
        self.assertEqual(len(self.clipboard), 1)
        self.assertIn("\n2.5\n0\n", self.clipboard[0])

    def test_invalid_scales_are_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), "not-a-number"):
            with self.subTest(value=value):
                ok, message = acad.insert_render("C:/work/render.png", scale=value)
                self.assertFalse(ok)
                self.assertIn("Echelle invalide", message)


if __name__ == "__main__":
    unittest.main()
