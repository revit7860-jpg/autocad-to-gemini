"""Tests unitaires du cache local des rendus."""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from render_cache import RenderCache


class RenderCacheTests(unittest.TestCase):
    def test_key_depends_on_image_bytes_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "plan.png"
            image.write_bytes(b"plan-a")
            first = RenderCache.key_for(str(image), "  vue de dessus  ")
            self.assertEqual(first, RenderCache.key_for(str(image), "vue de dessus"))
            self.assertNotEqual(first, RenderCache.key_for(str(image), "perspective"))
            image.write_bytes(b"plan-b")
            self.assertNotEqual(first, RenderCache.key_for(str(image), "vue de dessus"))

    def test_put_get_and_lru_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = RenderCache(str(Path(tmp) / "cache"), max_entries=2)
            sources = []
            for name in ("a", "b", "c"):
                source = Path(tmp) / name
                source.write_bytes((name * 20).encode())
                sources.append(source)
            keys = ["a" * 64, "b" * 64, "c" * 64]
            cache.put(keys[0], str(sources[0]))
            cache.put(keys[1], str(sources[1]))
            self.assertEqual(Path(cache.get(keys[0])).read_bytes(), sources[0].read_bytes())
            cache.put(keys[2], str(sources[2]))
            self.assertIsNotNone(cache.get(keys[0]))
            self.assertIsNone(cache.get(keys[1]))
            self.assertIsNotNone(cache.get(keys[2]))


if __name__ == "__main__":
    unittest.main()
