"""
Pont AutoCAD : capture la zone de dessin et reinsere le rendu dans le dessin.
"""
import os
import time

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None


def find_autocad_window():
    if gw is None:
        return None
    wins = [w for w in gw.getWindowsWithTitle("AutoCAD") if w.title]
    wins = [w for w in wins if "AutoCAD" in w.title and "Gemini" not in w.title]
    # priorite au premier dwg
    for w in wins:
        if "dwg" in w.title.lower() or "-" in w.title:
            return w
    return wins[0] if wins else None


def is_autocad_open():
    return find_autocad_window() is not None


def ensure_visible():
    """Remet la fenetre AutoCAD au premier plan (sans capturer)."""
    win = find_autocad_window()
    if win is None:
        return False
    try:
        if win.isMinimized:
            win.restore()
            time.sleep(0.4)
        try:
            win.activate()
        except Exception:
            pass
        return True
    except Exception:
        return False


def capture_plan(out_path, crop=True, region=None, focus=True):
    """Capture le plan.
    - region=(x,y,w,h) : capture exactement la zone selectionnee (prioritaire).
    - sinon : capture la fenetre AutoCAD (avec recadrage optionnel).
    - focus=False : ne touche pas au focus (mode express)."""
    if pyautogui is None:
        return False, "pyautogui manquant."
    try:
        if region is not None:
            x, y, w, h = [int(v) for v in region]
            if w < 10 or h < 10:
                return False, "Zone de selection trop petite."
            img = pyautogui.screenshot(region=(x, y, w, h))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            img.save(out_path)
            return True, out_path
        win = find_autocad_window()
        if win is None:
            return False, "AutoCAD introuvable (aucune fenetre du dessin)."
        if win.isMinimized:
            win.restore()
            time.sleep(0.5)
        if focus:
            try:
                win.activate()
            except Exception:
                pass
            time.sleep(0.8)  # laisse le focus revenir a AutoCAD
        left, top = win.left, win.top
        width, height = win.width, win.height
        if crop:
            top += 90  # ajustable selon ta config
            height -= 150
            width -= 16
        left = max(left, 0); top = max(top, 0)
        width = max(width, 200); height = max(height, 150)
        img = pyautogui.screenshot(region=(left, top, width, height))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        img.save(out_path)
        return True, out_path
    except Exception as e:
        return False, "Erreur de capture: %s" % e


def _acad_com():
    try:
        import pythoncom
        import win32com.client as win32
        pythoncom.CoInitialize()
        return win32.Dispatch("AutoCAD.Application")
    except Exception:
        return None


def insert_render(render_path, scale=None, x=0.0, y=0.0, zoom=False):
    try:
        s = float(scale) if scale else 1.0
    except (TypeError, ValueError):
        s = 1.0
    if s <= 0:
        s = 1.0
    app = _acad_com()
    if app is not None:
        try:
            import pythoncom
            import win32com.client as win32
            doc = app.ActiveDocument
            vt = win32.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (float(x), float(y), 0.0))
            doc.ModelSpace.AddRaster(render_path, vt, s, 0.0)
            if zoom:
                try:
                    doc.Application.ZoomExtents()
                except Exception:
                    pass
            return True, "Rendu insere (COM AddRaster, echelle %s)." % s
        except Exception as e:
            return False, "COM AddRaster echoue: %s" % e
    win = find_autocad_window()
    if win is not None and pyautogui is not None:
        try:
            if win.isMinimized:
                win.restore()
            try:
                win.activate()
            except Exception:
                pass
            time.sleep(0.6)
            import pyperclip
            cmd = "_.-IMAGEATTACH\n%s\n%s,%s\n1\n0\n" % (render_path.replace("\\", "/"), x, y)
            pyperclip.copy(cmd)
            pyautogui.hotkey("ctrl", "v")
            pyautogui.press("enter")
            return True, "Rendu insere (fallback -IMAGEATTACH)."
        except Exception as e:
            return False, "Insertion impossible: %s" % e
    return False, "AutoCAD introuvable et pywin32 indisponible pour insertion."
