"""Benchmark manuel de l'insertion et du rafraîchissement raster via AutoCAD COM.

À lancer sous Windows avec AutoCAD installé. Crée un document temporaire, mesure
AddRaster et ZoomExtents+Regen pour plusieurs résolutions, puis ferme ce document
sans enregistrer. Ce test mesure un proxy COM/regen de l'affichage, pas la latence
physique du moniteur ni une génération Gemini.
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

try:
    import pythoncom
    import win32com.client as win32
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit(
        "Dépendance manquante. Lancez ce script sous Windows avec AutoCAD, "
        "pywin32 et Pillow installés. Détail: %s" % exc
    )


RESOLUTIONS = ((1024, 768), (1920, 1080), (2560, 1440), (3840, 2160))


def make_test_image(path: Path, width: int, height: int) -> None:
    """Fabrique un plan schématique riche en lignes, sans dépendance à des plans réels."""
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    margin = max(20, min(width, height) // 20)
    thick = max(2, min(width, height) // 300)
    x0, y0, x1, y1 = margin, margin, width - margin, height - margin
    draw.rectangle((x0, y0, x1, y1), outline="black", width=thick * 3)
    # Cloisons et ouvertures schématiques afin de tester un dessin dense.
    for i in range(1, 8):
        x = x0 + (x1 - x0) * i // 8
        draw.line((x, y0, x, y1), fill="#303030", width=thick)
    for i in range(1, 5):
        y = y0 + (y1 - y0) * i // 5
        draw.line((x0, y, x1, y), fill="#303030", width=thick)
    for i in range(24):
        x = x0 + (x1 - x0) * i // 24
        draw.line((x, y0, min(x + width // 18, x1), min(y0 + height // 14, y1)),
                  fill="#777777", width=max(1, thick // 2))
    image.save(path, format="PNG", optimize=False)


def run_benchmark(repeats: int, csv_path: Path) -> list[dict]:
    pythoncom.CoInitialize()
    app = win32.Dispatch("AutoCAD.Application")
    app.Visible = True
    doc = None
    results = []
    try:
        doc = app.Documents.Add()
        print("Document temporaire créé : %s" % doc.Name)
        with tempfile.TemporaryDirectory(prefix="acad_render_bench_") as tmp:
            temp_dir = Path(tmp)
            for width, height in RESOLUTIONS:
                image_path = temp_dir / ("plan_%dx%d.png" % (width, height))
                make_test_image(image_path, width, height)
                add_ms, refresh_ms, total_ms = [], [], []
                for iteration in range(1, repeats + 1):
                    started = time.perf_counter()
                    raster = doc.ModelSpace.AddRaster(
                        str(image_path),
                        win32.VARIANT(
                            pythoncom.VT_ARRAY | pythoncom.VT_R8,
                            (0.0, 0.0, 0.0),
                        ),
                        1.0,
                        0.0,
                    )
                    added = time.perf_counter()
                    # Forcer l'étendue et la régénération pour inclure le rafraîchissement
                    # demandé à AutoCAD après l'attachement du raster.
                    try:
                        doc.Application.ZoomExtents()
                    except Exception:
                        pass
                    doc.Regen(1)  # acAllViewports
                    try:
                        app.Update()
                    except Exception:
                        pass
                    pythoncom.PumpWaitingMessages()
                    refreshed = time.perf_counter()

                    add_ms.append((added - started) * 1000)
                    refresh_ms.append((refreshed - added) * 1000)
                    total_ms.append((refreshed - started) * 1000)
                    print("%dx%d essai %d/%d : AddRaster %.0f ms, rafraîchissement %.0f ms, total %.0f ms"
                          % (width, height, iteration, repeats, add_ms[-1],
                             refresh_ms[-1], total_ms[-1]))
                    try:
                        raster.Delete()
                        doc.Regen(1)
                    except Exception:
                        pass

                results.append({
                    "width": width,
                    "height": height,
                    "repeats": repeats,
                    "add_raster_mean_ms": round(statistics.mean(add_ms), 2),
                    "refresh_mean_ms": round(statistics.mean(refresh_ms), 2),
                    "total_mean_ms": round(statistics.mean(total_ms), 2),
                    "total_min_ms": round(min(total_ms), 2),
                    "total_max_ms": round(max(total_ms), 2),
                })
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(output, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print("\nRésumé (moyenne) :")
        for row in results:
            print("{width}x{height}: AddRaster {add_raster_mean_ms} ms, refresh {refresh_mean_ms} ms, total {total_mean_ms} ms".format(**row))
        print("CSV : %s" % csv_path.resolve())
        return results
    finally:
        if doc is not None:
            try:
                doc.Close(False)  # document créé par le script, sans sauvegarder
            except Exception:
                pass
        pythoncom.CoUninitialize()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, help="Nombre de mesures par résolution (défaut : 3).")
    parser.add_argument("--csv", default="autocad_display_benchmark.csv", help="Chemin du rapport CSV.")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats doit être au moins égal à 1")
    if sys.platform != "win32":
        raise SystemExit("Ce benchmark nécessite Windows et AutoCAD COM.")
    run_benchmark(args.repeats, Path(args.csv))


if __name__ == "__main__":
    main()
