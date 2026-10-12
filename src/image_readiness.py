"""Attente courte de disponibilité/stabilité d’une image dans le DOM Gemini."""
from __future__ import annotations

import time


_IMAGE_STATE_SCRIPT = """
var img = arguments[0];
if (!img || !img.isConnected) return null;
return {
  loaded: !!(img.complete && img.naturalWidth > 0 && img.naturalHeight > 0),
  src: img.currentSrc || img.src || '',
  width: img.naturalWidth || 0,
  height: img.naturalHeight || 0
};
"""


def wait_image_ready(driver, element, timeout=3.0, interval=0.15,
                     stable_samples=2, clock=time.monotonic, sleep=time.sleep):
    """Attend `complete/naturalWidth` et deux observations identiques au plus.

    Retourne (ready, state). À expiration, une image déjà chargée est quand même
    retournée pour ne pas bloquer inutilement l’extraction derrière un spinner
    de réponse Gemini qui peut continuer à afficher du texte.
    """
    deadline = clock() + max(0.0, timeout)
    previous = None
    consecutive = 0
    last_loaded = None

    while True:
        try:
            state = driver.execute_script(_IMAGE_STATE_SCRIPT, element)
        except Exception:
            state = None

        if state and state.get("loaded") and state.get("width", 0) > 0 and state.get("height", 0) > 0:
            signature = (state.get("src", ""), state["width"], state["height"])
            last_loaded = state
            consecutive = consecutive + 1 if signature == previous else 1
            previous = signature
            if consecutive >= max(1, stable_samples):
                return True, state
        else:
            previous = None
            consecutive = 0

        remaining = deadline - clock()
        if remaining <= 0:
            return (last_loaded is not None), last_loaded
        sleep(min(max(0.01, interval), remaining))
