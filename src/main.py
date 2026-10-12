"""
Point d'entree de AutoCAD Gemini Render.

Un verrou sur un port localhost empeche d'ouvrir plusieurs instances.
Lance ensuite l'interface Tk.
"""

import os
import sys
import socket
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import RenderApp  # noqa: E402

LOCK_PORT = 50573


def acquire_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def _focus_existing():
    """Ramene la fenetre existante au premier plan (best effort)."""
    try:
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle("Gemini Render")
        if wins:
            w = wins[0]
            if w.isMinimized:
                w.restore()
            w.activate()
            return
    except Exception:
        pass
    try:
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(
            "AutoCAD Gemini Render",
            "L'outil est deja ouvert.\n"
            "Cherchez sa fenetre avec Alt+Tab.")
        r.destroy()
    except Exception:
        pass


def main():
    lock = acquire_lock()
    if lock is None:
        # Une instance tourne deja : la ramener au premier plan.
        print("AutoCAD Gemini Render est deja ouvert.")
        _focus_existing()
        return

    root = tk.Tk()
    try:
        # Passer devant AutoCAD au demarrage, puis redevenir normale
        root.lift()
        root.attributes("-topmost", True)
        root.after(2000, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    RenderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
