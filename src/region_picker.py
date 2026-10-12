"""Selecteur de zone d'ecran : l'utilisateur encadre la zone a capturer a la souris.

Utilise un Toplevel rattache a la fenetre existante (jamais de 2e Tk :
cela faisait planter l'interpreteur). Attente via wait_window, pas de
2e mainloop.

Retourne (x, y, w, h) en coordonnees ecran, ou None si annule.
"""

import tkinter as tk


def select_region(parent):
    sel = {"rect": None, "x0": 0, "y0": 0, "x1": 0, "y1": 0, "id": None}

    top = tk.Toplevel(parent)
    top.title("Selection de zone")
    try:
        top.attributes("-fullscreen", True)
    except Exception:
        try:
            top.geometry("%dx%d+0+0" % (top.winfo_screenwidth(), top.winfo_screenheight()))
        except Exception:
            pass
    try:
        top.attributes("-topmost", True)
    except Exception:
        pass
    try:
        top.attributes("-alpha", 0.35)
    except Exception:
        pass
    top.configure(background="black", cursor="crosshair")

    cv = tk.Canvas(top, background="black", highlightthickness=0, cursor="crosshair")
    cv.pack(fill="both", expand=True)
    cv.create_text(24, 20, anchor="nw", fill="white",
                   text="Encadrez le plan a la souris  |  Entree = valider  |  Echap = annuler",
                   font=("Segoe UI", 13, "bold"))

    def done():
        try:
            top.withdraw()  # masquer d'abord : evite le fantome a la capture
        except Exception:
            pass
        try:
            top.grab_release()
        except Exception:
            pass
        try:
            top.destroy()
        except Exception:
            pass

    def on_press(e):
        sel["x0"], sel["y0"] = e.x, e.y
        sel["x1"], sel["y1"] = e.x, e.y

    def on_drag(e):
        sel["x1"], sel["y1"] = e.x, e.y
        if sel["id"] is not None:
            try:
                cv.delete(sel["id"])
            except Exception:
                pass
        sel["id"] = cv.create_rectangle(sel["x0"], sel["y0"], e.x, e.y,
                                        outline="#ff3333", width=3)

    def on_ok(_e=None):
        w = abs(sel["x1"] - sel["x0"])
        h = abs(sel["y1"] - sel["y0"])
        if w > 10 and h > 10:
            x = min(sel["x0"], sel["x1"])
            y = min(sel["y0"], sel["y1"])
            sel["rect"] = (x, y, w, h)
        done()

    def on_cancel(_e=None):
        sel["rect"] = None
        done()

    cv.bind("<ButtonPress-1>", on_press)
    cv.bind("<B1-Motion>", on_drag)
    top.bind("<Return>", on_ok)
    top.bind("<Escape>", on_cancel)
    try:
        top.focus_force()
    except Exception:
        pass
    try:
        top.grab_set()
    except Exception:
        pass
    try:
        parent.wait_window(top)
    except Exception:
        done()
    return sel["rect"]
