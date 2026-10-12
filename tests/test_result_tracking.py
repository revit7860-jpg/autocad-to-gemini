"""Tests de prévention contre la réutilisation d’un ancien rendu Gemini."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from result_tracking import images_with_new_signatures


class Image:
    def __init__(self, src):
        self.src = src


class ResultTrackingTests(unittest.TestCase):
    def test_only_images_with_new_sources_are_candidates(self):
        old = Image("blob:previous-plan-render")
        fresh = Image("blob:new-plan-render")
        self.assertEqual(
            images_with_new_signatures(
                [old, fresh], {"blob:previous-plan-render"}, lambda image: image.src
            ),
            [fresh],
        )

    def test_empty_or_unchanged_sources_are_not_candidates(self):
        blank = Image("")
        old = Image("blob:previous")
        self.assertEqual(
            images_with_new_signatures(
                [blank, old], {"blob:previous"}, lambda image: image.src
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
