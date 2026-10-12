"""Interface Tkinter : plan AutoCAD -> rendu Gemini -> retour dans AutoCAD."""

import os
import json
import math
import time
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

import autocad_bridge as acad
import region_picker as picker
from gemini_web import GeminiWebBot

BG_DARK = "#1e1e24"
BG_CARD = "#2b2b36"
FG = "#f0f0f5"
FG_DIM = "#a0a0b0"
ACCENT = "#0078d4"
GREEN = "#107c41"
RED = "#d13438"


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _asset(name):
    p = os.path.join(app_dir(), name)
    return p if os.path.exists(p) else os.path.join(os.path.dirname(app_dir()), name)


def work_dir():
    t = os.environ.get("TEMP", os.path.expanduser("~"))
    d = os.path.join(t, "AutoCADGemini")
    os.makedirs(d, exist_ok=True)
    return d


def profile_dir():
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    d = os.path.join(base, "AutoCADGemini", "chrome_profile")
    os.makedirs(d, exist_ok=True)
    return d


class RenderApp:
    def __init__(self, root):
        self.root = root
        self.work = work_dir()
        self.plan_path = os.path.join(self.work, "plan.png")
        self.render_path = os.path.join(self.work, "render.png")

        self.bot = GeminiWebBot(profile_dir(), self.work, logger=self.log_main)
        self.presets = self._load_presets()
        self._busy = False
        self._closing = False
        self.last_region = None
        self.var_manual = tk.BooleanVar(value=False)
        self.var_insert_scale = tk.StringVar(value="1.0")
        self._photo_plan = None
        self._photo_render = None

        root.title("AutoCAD \u2194 Gemini Render")
        root.geometry("1080x760")
        root.configure(bg=BG_DARK)
        try:
            root.iconbitmap(_asset("app_icon.ico"))
        except Exception:
            pass

        self._build_ui()
        self.log("Pret. Cliquez RENDU EXPRESS (Gemini se pre-charge en arriere-plan).")
        try:
            root.protocol("WM_DELETE_WINDOW", self.on_close)
        except Exception:
            pass
        self._monitor()
        self._warmup_browser()

    def on_close(self):
        """Attend la fin des opérations Selenium puis ferme Tk sans tuer le processus."""
        if self._closing:
            return
        self._closing = True
        self._set_busy(True)
        self.log("Fermeture en cours : attente de la fin des opérations navigateur...")

        def shutdown():
            try:
                self.bot.close_browser()  # attend le verrou si une génération est active
            except Exception as e:
                self.log_main("Fermeture du navigateur : %s" % e)
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

        threading.Thread(target=shutdown, name="autocadgemini-shutdown", daemon=False).start()

    def _warmup_browser(self):
        """Pre-ouvre Chrome/Gemini en tache de fond pour supprimer l'etape 2."""
        def run():
            try:
                if not self.bot.is_browser_open():
                    self.log_main("Pre-chargement de Gemini en arriere-plan...")
                    if self.bot.launch_browser():
                        try:
                            acad.ensure_visible()
                        except Exception:
                            pass
            except Exception as e:
                self.log_main("Pre-chargement impossible: %s" % e)
        threading.Thread(target=run, daemon=True).start()

    def _bring_to_front(self):
        """Restaure la fenetre ET la force au premier plan (topmost temporaire)."""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.attributes("-topmost", True)
            self.root.after(2000, self._drop_topmost)
        except Exception:
            pass

    def _drop_topmost(self):
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

    # ------------------------------------------------------------------ presets
    def _load_presets(self):
        for p in (_asset("presets.json"), os.path.join(app_dir(), "presets.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return {"Rendu realiste": "Transforme ce plan d'architecte en rendu 3D photorealiste vu de dessus."}

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_DARK, foreground=FG, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=BG_DARK, foreground=FG, font=("Segoe UI", 14, "bold"))
        style.configure("Sub.TLabel", background=BG_DARK, foreground=FG_DIM, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG_DARK, foreground=FG, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)

        head = ttk.Frame(self.root); head.pack(fill="x", padx=14, pady=(12, 4))
        ttk.Label(head, text="AutoCAD \u2194 Gemini", style="Header.TLabel").pack(side="left")
        ttk.Label(head, text="   Plan \u2192 rendu realiste, sans quitter AutoCAD", style="Sub.TLabel").pack(side="left")

        status = ttk.Frame(self.root); status.pack(fill="x", padx=14)
        self.lbl_acad = ttk.Label(status, text="AutoCAD: ?", style="Status.TLabel", foreground=FG_DIM)
        self.lbl_acad.pack(side="left")
        self.lbl_gem = ttk.Label(status, text="   Gemini: ?", style="Status.TLabel", foreground=FG_DIM)
        self.lbl_gem.pack(side="left")

        # prompt
        pf = ttk.Frame(self.root); pf.pack(fill="x", padx=14, pady=(8, 4))
        ttk.Label(pf, text="Type de rendu :").grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(pf, values=list(self.presets.keys()), state="readonly", width=44)
        self.combo.grid(row=0, column=1, sticky="w", padx=6)
        self.combo.current(0)
        self.combo.bind("<<ComboboxSelected>>", self._on_preset)
        ttk.Label(pf, text="Prompt :").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.txt_prompt = tk.Text(pf, height=4, bg="#121216", fg=FG, insertbackground=FG,
                                  relief="flat", wrap="word", font=("Segoe UI", 9))
        self.txt_prompt.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        pf.columnconfigure(1, weight=1)
        self._on_preset()

        # buttons
        bf = ttk.Frame(self.root); bf.pack(fill="x", padx=14, pady=8)
        self.btn_express = ttk.Button(bf, text="RENDU EXPRESS (1 clic)", command=self.do_express)
        self.btn_express.pack(side="left", padx=(0, 6))
        self.btn_capture = ttk.Button(bf, text="1. Capturer", command=self.do_capture)
        self.btn_capture.pack(side="left", padx=6)
        self.btn_open = ttk.Button(bf, text="2. Ouvrir Gemini", command=self.do_open)
        self.btn_open.pack(side="left", padx=6)
        self.btn_gen = ttk.Button(bf, text="3. Generer", command=self.do_generate)
        self.btn_gen.pack(side="left", padx=6)
        self.btn_ins = ttk.Button(bf, text="Inserer", command=self.do_insert)
        self.btn_ins.pack(side="left", padx=6)
        ttk.Label(bf, text="Échelle :").pack(side="left", padx=(8, 2))
        self.entry_insert_scale = ttk.Entry(bf, textvariable=self.var_insert_scale, width=7)
        self.entry_insert_scale.pack(side="left", padx=2)
        ttk.Checkbutton(bf, text="Selection manuelle", variable=self.var_manual).pack(side="left", padx=6)
        ttk.Button(bf, text="Dossier de travail", command=self.open_folder).pack(side="right")

        # previews
        pv = ttk.Frame(self.root); pv.pack(fill="both", expand=True, padx=14, pady=(4, 8))
        pv.columnconfigure(0, weight=1); pv.columnconfigure(1, weight=1)
        pv.rowconfigure(1, weight=1)

        ttk.Label(pv, text="Plan / Image d'entree").grid(row=0, column=0, sticky="w")
        ttk.Label(pv, text="Rendu Gemini").grid(row=0, column=1, sticky="w")
        self.can_plan = tk.Label(pv, bg="#18181f", fg=FG_DIM, text="[ aucun plan capturé ]")
        self.can_plan.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=4)
        self.can_render = tk.Label(pv, bg="#18181f", fg=FG_DIM, text="[ aucun rendu généré ]")
        self.can_render.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=4)

        # log
        ttk.Label(self.root, text="Journal :").pack(anchor="w", padx=14)
        self.txt_log = tk.Text(self.root, height=8, bg="#121216", fg="#00ffcc",
                               relief="flat", font=("Consolas", 9))
        self.txt_log.pack(fill="both", padx=14, pady=(0, 12))

    def _on_preset(self, event=None):
        name = self.combo.get()
        if name in self.presets:
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", self.presets[name])

    # ------------------------------------------------------------------ utils
    def log(self, msg):
        ts = time.strftime("[%H:%M:%S] ")
        self.txt_log.insert("end", ts + str(msg) + "\n")
        self.txt_log.see("end")

    def log_main(self, msg):
        # appele depuis un thread -> repasser sur le thread Tk
        self.root.after(0, lambda: self.log(msg))

    def _set_busy(self, busy):
        self._busy = bool(busy) or self._closing
        state = "disabled" if self._busy else "normal"
        for b in (self.btn_capture, self.btn_open, self.btn_gen, self.btn_ins, self.btn_express):
            b.config(state=state)
        self.entry_insert_scale.config(state="disabled" if busy else "normal")

    def _get_insert_scale(self):
        """Lit et valide l'échelle avant tout travail d'insertion."""
        try:
            scale = float(self.var_insert_scale.get().strip().replace(",", "."))
        except (TypeError, ValueError):
            messagebox.showwarning("Échelle invalide", "Saisissez un nombre strictement positif.")
            return None
        if not math.isfinite(scale) or scale <= 0:
            messagebox.showwarning("Échelle invalide", "Saisissez un nombre strictement positif.")
            return None
        return scale

    def _show_image(self, path, attr):
        if Image is None or not os.path.isfile(path):
            return
        try:
            img = Image.open(path)
            img.thumbnail((480, 380))
            photo = ImageTk.PhotoImage(img)
            setattr(self, attr, photo)
            widget = self.can_plan if attr == "_photo_plan" else self.can_render
            widget.config(image=photo, text="")
        except Exception as e:
            self.log("Apercu impossible: %s" % e)

    def open_folder(self):
        try:
            os.startfile(self.work)
        except Exception as e:
            self.log("Ouverture dossier impossible: %s" % e)

    # ------------------------------------------------------------------ actions
    def do_capture(self):
        if self.var_manual.get():
            # L'utilisateur encadre lui-meme la zone, en restant visuellement sur AutoCAD
            self.log("Encadrez la zone du plan a la souris (Entree = valider, Echap = annuler)...")
            self.root.withdraw()
            try:
                acad.ensure_visible()
                time.sleep(0.3)
                rect = picker.select_region(self.root)
            except Exception as e:
                self.log("Selecteur impossible: %s" % e)
                rect = None
            time.sleep(0.4)  # laisser l'overlay disparaitre de l'ecran
            if not rect:
                self.log("Capture annulee.")
                self._bring_to_front()
                return
            self.last_region = rect
            # Capturer AVANT de faire revenir la fenetre (sinon elle est dans l'image)
            ok, res = acad.capture_plan(self.plan_path, region=rect)
            self._bring_to_front()
        else:
            self.log("Capture du plan AutoCAD...")
            ok, res = acad.capture_plan(self.plan_path)
        if ok:
            self.log("Plan capture: %s" % res)
            self._show_image(self.plan_path, "_photo_plan")
        else:
            self.log("Erreur capture: %s" % res)

    def do_express(self):
        """Tout en un clic : capture -> Gemini -> insertion, sans quitter AutoCAD."""
        if self._busy:
            return
        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Prompt vide", "Saisissez un prompt.")
            return
        scale = self._get_insert_scale()
        if scale is None:
            return
        # Etape 1 (thread principal) : choix de la zone
        rect = self.last_region
        if self.var_manual.get() or not rect:
            self.log("Encadrez la zone du plan a la souris (Entree = valider)...")
            self.root.withdraw()
            try:
                acad.ensure_visible()
                time.sleep(0.3)
                rect = picker.select_region(self.root)
            except Exception as e:
                self.log("Selecteur impossible: %s" % e)
                rect = None
            time.sleep(0.4)  # laisser l'overlay disparaitre de l'ecran
            if not rect:
                self.log("Rendu express annule.")
                self._bring_to_front()
                return
            self.last_region = rect
        self._set_busy(True)
        try:
            self.root.iconify()  # l'utilisateur reste sur AutoCAD
        except Exception:
            pass
        threading.Thread(target=lambda: self._express_run(rect, prompt, scale), daemon=True).start()

    def _express_run(self, rect, prompt, scale):
        try:
            ok, res = acad.capture_plan(self.plan_path, region=rect, focus=False)
            if not ok:
                self.log_main("Capture impossible: %s" % res)
                return
            self.root.after(0, lambda: self._show_image(self.plan_path, "_photo_plan"))
            if not self.bot.is_browser_open():
                self.log_main("Ouverture de Gemini...")
                if not self.bot.launch_browser():
                    self.log_main("Ouverture Gemini impossible.")
                    return
            self.log_main("Generation du rendu (restez sur AutoCAD)...")
            ok, res = self.bot.upload_plan_and_generate(self.plan_path, prompt, self.render_path)
            if not ok:
                self.log_main("Echec: %s" % res)
                return
            self.root.after(0, lambda: self._show_image(self.render_path, "_photo_render"))
            ok2, msg2 = acad.insert_render(self.render_path, scale=scale)
            self.log_main(msg2)
            self.log_main("Rendu express termine : le rendu est dans votre dessin.")
        finally:
            self.root.after(0, self._express_done)

    def _express_done(self):
        self._set_busy(False)
        try:
            self.root.iconify()
        except Exception:
            pass
        try:
            acad.ensure_visible()
        except Exception:
            pass

    def do_open(self):
        if self._busy:
            self.log("Operation en cours, patientez...")
            return
        self._set_busy(True)
        def run():
            ok = self.bot.launch_browser()
            self.log_main("Gemini ouvert: %s" % self.bot.GEMINI_URL)
            if not ok:
                self.log_main("Ouverture Gemini impossible.")
            try:
                acad.ensure_visible()
            except Exception:
                pass
            self.root.after(0, lambda: self._set_busy(False))
        threading.Thread(target=run, daemon=True).start()

    def do_generate(self):
        if self._busy:
            self.log("Operation en cours, patientez...")
            return
        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not os.path.isfile(self.plan_path):
            messagebox.showwarning("Plan manquant", "Capturez d'abord le plan AutoCAD.")
            return
        if not prompt:
            messagebox.showwarning("Prompt vide", "Saisissez un prompt.")
            return
        scale = self._get_insert_scale()
        if scale is None:
            return
        self._set_busy(True)
        self.log("Generation du rendu aupres de Gemini...")
        def run():
            ok, res = self.bot.upload_plan_and_generate(self.plan_path, prompt, self.render_path)
            self.root.after(0, lambda: self._on_gen_done(ok, res, scale))
        threading.Thread(target=run, daemon=True).start()

    def _on_gen_done(self, ok, res, scale):
        self._set_busy(False)
        if ok:
            self.log("Rendu genere: %s" % res)
            self._show_image(self.render_path, "_photo_render")
            try:
                ok2, msg2 = acad.insert_render(self.render_path, scale=scale)
                self.log(msg2)
            except Exception as e:
                self.log("Insertion impossible: %s" % e)
            try:
                acad.ensure_visible()
            except Exception:
                pass
        else:
            self.log("Echec: %s" % res)

    def do_insert(self):
        if not os.path.isfile(self.render_path):
            messagebox.showwarning("Rendu manquant", "Generez d'abord un rendu.")
            return
        scale = self._get_insert_scale()
        if scale is None:
            return
        ok, msg = acad.insert_render(self.render_path, scale=scale)
        self.log(msg)

    # ------------------------------------------------------------------ monitor
    def _monitor(self):
        def tick():
            acad_open = acad.is_autocad_open()
            self.lbl_acad.config(
                text="AutoCAD: connecte" if acad_open else "AutoCAD: hors ligne",
                foreground=(GREEN if acad_open else RED))
            state = self.bot.get_login_state()
            label = {
                "ok": ("Gemini: pret", GREEN),
                "signin": ("Gemini: connexion requise", "#ffcc33"),
                "loading": ("Gemini: chargement...", FG_DIM),
                "closed": ("Gemini: ferme", RED),
                "other": ("Gemini: page hors Gemini", FG_DIM),
            }.get(state, ("Gemini: ?", FG_DIM))
            self.lbl_gem.config(text="   " + label[0], foreground=label[1])
        try:
            tick()
        except Exception as e:
            self.log("monitor: %s" % e)
        self.root.after(2000, self._monitor)
