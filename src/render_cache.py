"""Cache local des rendus Gemini, indexé par image source et prompt."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


CACHE_SCHEMA = "gemini-web-render-cache-v1"


class RenderCache:
    """Cache déterministe local ; chaque entrée représente une image source + prompt."""

    def __init__(self, cache_dir: str, max_entries: int = 40):
        self.cache_dir = Path(cache_dir)
        self.max_entries = max(1, int(max_entries))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key_for(image_path: str, prompt: str) -> str:
        digest = hashlib.sha256()
        digest.update(CACHE_SCHEMA.encode("utf-8"))
        digest.update(b"\0")
        digest.update((prompt or "").strip().encode("utf-8"))
        digest.update(b"\0")
        with open(image_path, "rb") as image:
            for chunk in iter(lambda: image.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def get(self, key: str) -> str | None:
        path = self.cache_dir / (key + ".render")
        try:
            if path.is_file() and path.stat().st_size > 0:
                os.utime(path, None)  # LRU approximatif
                return str(path)
        except OSError:
            return None
        return None

    def put(self, key: str, source_path: str) -> str:
        """Écrit atomiquement une entrée pour qu'un arrêt ne laisse pas de cache tronqué."""
        destination = self.cache_dir / (key + ".render")
        fd, temp_path = tempfile.mkstemp(prefix=key + ".", suffix=".tmp", dir=self.cache_dir)
        os.close(fd)
        try:
            shutil.copyfile(source_path, temp_path)
            os.replace(temp_path, destination)
            self._prune()
            return str(destination)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _prune(self) -> None:
        entries = []
        for path in self.cache_dir.glob("*.render"):
            try:
                entries.append((path.stat().st_mtime, path))
            except OSError:
                continue
        entries.sort(key=lambda item: item[0], reverse=True)
        for _, path in entries[self.max_entries:]:
            try:
                path.unlink()
            except OSError:
                # Une entrée utilisée ou verrouillée est conservée jusqu'au prochain nettoyage.
                pass
