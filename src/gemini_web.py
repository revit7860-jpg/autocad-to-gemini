"""
Gemini Web automation for AutoCAD Gemini Render.

Ouvre Gemini (https://gemini.google.com) dans Chrome avec un profil persistant,
envoie une image de plan + un prompt architectural, attend la generation puis
recupere l'image de rendu. Adapte du principe de GeminiStudio (3ds Max).

⚠️ Automatiser l'UI web de Gemini peut etre contraire aux CGU Google.
   A utiliser avec un compte dedie.
"""

import os
import time
import glob
import base64
import hashlib
import shutil
import subprocess
import threading

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from render_cache import RenderCache
from image_readiness import wait_image_ready
from result_tracking import images_with_new_signatures

try:
    import undetected_chromedriver as uc
    HAS_UC = True
except Exception:
    HAS_UC = False

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WDM = True
except Exception:
    HAS_WDM = False

GEMINI_URL = "https://gemini.google.com/app"

_JS_LOGIN_STATE = """
if (location.hostname.indexOf('gemini.google.com') < 0) return 'other';
function vis(e){ var r=e.getBoundingClientRect(), st=getComputedStyle(e);
  return r.width>0 && r.height>0 && st.visibility!=='hidden' && st.display!=='none' && st.opacity!=='0'; }
var btns = Array.from(document.querySelectorAll('a,button'));
var signin = btns.find(function(b){ var t=((b.innerText||'')+' '+(b.getAttribute('aria-label')||'')).toLowerCase();
  return (t.indexOf('sign in')>=0 || t.indexOf('se connecter')>=0 || t.indexOf('dang nhap')>=0) && vis(b); });
if (signin) return 'signin';
var editors = document.querySelectorAll("[contenteditable='true']");
for (var i=0;i<editors.length;i++){ if (vis(editors[i])) return 'ok'; }
return 'loading';
"""

# Trouve les images generees par le modele (exclut les images uploadees par l'utilisateur)
_JS_FIND_RESULT_IMAGES = """
var out = [];
var imgs = document.querySelectorAll('img');
imgs.forEach(function(img){
  var inUser = img.closest('user-query, .user-query-container, .query-container, [data-test-id="user-query"], .file-preview-container');
  if (inUser) return;
  var src = img.src || '';
  if (!src) return;
  if (src.indexOf('googleusercontent')>=0 || src.indexOf('blob:')>=0 || src.indexOf('data:image')>=0) {
    var r = img.getBoundingClientRect();
    if (r.width >= 100 && r.height >= 100) out.push(img);
  }
});
return out;
"""

_JS_DOWNLOAD_BTN_FOR = """
var img = arguments[0];
function label(b){ return ((b.getAttribute('aria-label')||'') + ' ' + (b.getAttribute('title')||'') + ' ' +
  (b.getAttribute('mattooltip')||'') + ' ' + (b.getAttribute('data-test-id')||'')).toLowerCase(); }
var node = img;
for (var up=0; up<8 && node; up++){
  node = node.parentElement;
  if (!node) break;
  var cands = node.querySelectorAll('button, [role="button"]');
  for (var i=0;i<cands.length;i++){
    var l = label(cands[i]);
    if (l.indexOf('download')>=0 || l.indexOf('telecharg')>=0 || l.indexOf('télécharger')>=0 || l.indexOf('enregistrer')>=0 || l.indexOf('tai xuong')>=0 || l.indexOf('tải')>=0) return cands[i];
    var ic = cands[i].querySelector('mat-icon, i, svg');
    var it = ic ? ((ic.textContent||'')+' '+(ic.getAttribute('fonticon')||'')).toLowerCase() : '';
    if (it.indexOf('download')>=0 || it.indexOf('télécharger')>=0) return cands[i];
  }
}
return null;
"""

_JS_IMG_TO_B64 = """
var img = arguments[0];
var cb = arguments[1];
try {
  var c = document.createElement('canvas');
  c.width = img.naturalWidth || img.width;
  c.height = img.naturalHeight || img.height;
  c.getContext('2d').drawImage(img, 0, 0);
  cb(c.toDataURL('image/png'));
} catch (e) { cb(''); }
"""


class GeminiWebBot:
    def __init__(self, profile_dir, work_dir, logger=print):
        self.profile_dir = profile_dir
        self.work_dir = work_dir
        self.download_dir = os.path.join(work_dir, "downloads")
        self.render_cache = RenderCache(os.path.join(work_dir, "render_cache"))
        self.log = logger
        self.driver = None
        self._busy = False
        self._lock = threading.Lock()
        self._driver_lock = threading.RLock()  # serialize tous les acces WebDriver
        os.makedirs(self.profile_dir, exist_ok=True)
        os.makedirs(self.download_dir, exist_ok=True)

    # ------------------------------------------------------------------ browser
    def is_browser_open(self):
        # Toute lecture ou mutation de self.driver est protégée par le même verrou.
        with self._driver_lock:
            try:
                if self.driver is None:
                    return False
                _ = self.driver.current_url
                return True
            except Exception:
                self.driver = None
                return False

    def _selenium_driver(self):
        opts = Options()
        opts.add_argument("--user-data-dir=" + self.profile_dir)
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-service-autorun")
        opts.add_argument("--password-store=basic")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        if HAS_WDM:
            service = Service(ChromeDriverManager().install())
        else:
            service = Service()
        return webdriver.Chrome(service=service, options=opts)

    def _uc_driver(self):
        opts = uc.ChromeOptions()
        opts.add_argument("--user-data-dir=" + self.profile_dir)
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-service-autorun")
        opts.add_argument("--password-store=basic")
        opts.add_argument("--start-maximized")
        return uc.Chrome(options=opts)

    def _new_driver(self):
        # Selenium standard d'abord : rapide et versionne avec Chrome installe
        try:
            self.log("Lancement de Chrome (Selenium)...")
            return self._selenium_driver()
        except Exception as e:
            self.log("Selenium echoue, essai undetected-chromedriver: %s" % str(e)[:200])
        if HAS_UC:
            try:
                self.log("Lancement de Chrome (undetected-chromedriver)...")
                return self._uc_driver()
            except Exception as e:
                self.log("undetected-chromedriver echoue aussi: %s" % str(e)[:200])
        raise RuntimeError("Impossible de demarrer Chrome (voir messages ci-dessus).")

    def launch_browser(self):
        # Idempotent et protege : deux ouvertures concurrentes = un seul driver.
        with self._driver_lock:
            if self.is_browser_open():
                self.log("Le navigateur Gemini est deja ouvert.")
                return True
            try:
                self.driver = self._new_driver()
                try:
                    self.driver.execute_cdp_cmd(
                        "Page.setDownloadBehavior",
                        {"behavior": "allow", "downloadPath": self.download_dir},
                    )
                except Exception:
                    pass
                self.driver.get(GEMINI_URL)
                self.log("Gemini ouvert: %s" % GEMINI_URL)
                return True
            except Exception as e:
                self.log("Echec du lancement de Chrome: %s" % e)
                self.driver = None
                return False

    def close_browser(self):
        with self._driver_lock:
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self.log("Navigateur ferme.")

    def get_login_state(self):
        # Appelé périodiquement par Tk : ne jamais bloquer l'interface pendant
        # une génération longue ou le lancement/la fermeture du navigateur.
        if self._busy:
            return "ok"
        if not self._driver_lock.acquire(blocking=False):
            return "loading"
        try:
            if self.driver is None:
                return "closed"
            try:
                _ = self.driver.current_url
            except Exception:
                self.driver = None
                return "closed"
            if self._busy:
                return "ok"
            state = self.driver.execute_script(_JS_LOGIN_STATE)
            return state or "loading"
        except Exception:
            return "loading"
        finally:
            self._driver_lock.release()

    def is_signed_in(self):
        return self.get_login_state() == "ok"

    # ------------------------------------------------------------------ helpers
    def _find_prompt_input(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']")
                for e in els:
                    if e.is_displayed():
                        return e
            except Exception:
                pass
            time.sleep(0.5)
        return None

    def _scan_file_inputs(self):
        """Log de diagnostic : liste les input[type=file] presents."""
        try:
            info = self.driver.execute_script(
                "var out=[];"
                "document.querySelectorAll(\"input[type='file']\").forEach(function(i){"
                " out.push((i.accept||'*')+'|'+(i.disabled?'dis':'en')+'|'+"
                "((i.offsetWidth||i.offsetHeight)?'vis':'hid'));}); return out;")
            self.log("inputs file: %s" % (info if info else "aucun"))
            return info or []
        except Exception as e:
            self.log("scan inputs: %s" % e)
            return []

    def _unhide_file_inputs(self):
        try:
            return self.driver.execute_script(
                "document.querySelectorAll(\"input[type='file']\").forEach(function(i){"
                " i.style.display='block'; i.style.visibility='visible';"
                " i.style.opacity='1'; i.style.position='fixed';"
                " i.style.left='0px'; i.style.top='0px';"
                " i.style.width='20px'; i.style.height='20px';"
                " i.removeAttribute('hidden');});"
                "return document.querySelectorAll(\"input[type='file']\").length;")
        except Exception:
            return 0

    def _is_image_attached(self):
        """Vrai si un apercu d'image est present dans le composer."""
        try:
            return bool(self.driver.execute_script(
                "var ed=null;"
                "document.querySelectorAll(\"[contenteditable='true']\").forEach(function(e){"
                " if(e.offsetWidth||e.offsetHeight) ed=e;});"
                "if(!ed) return false;"
                "var box=ed; for(var u=0;u<20&&box;u++){"
                " var imgs=box.querySelectorAll('img');"
                " for(var i=0;i<imgs.length;i++){var r=imgs[i].getBoundingClientRect();"
                "  if(r.width>30&&r.height>30) return true;}"
                " if(box.querySelector('.file-preview-container,[data-test-id*=\"attach\"],"
                "[data-test-id*=\"file\"],[data-test-id*=\"preview\"],[class*=\"attachment\"],"
                "[class*=\"preview\"]')) return true;"
                " box=box.parentElement;}"
                "return false;"))
        except Exception:
            return False

    def _composer_image_signature(self):
        """Sources des aperçus d’image du compositeur, hors images des anciens tours."""
        try:
            values = self.driver.execute_script(
                "var ed=null;"
                "document.querySelectorAll(\"[contenteditable='true']\").forEach(function(e){"
                " if(e.offsetWidth||e.offsetHeight) ed=e;});"
                "if(!ed) return [];"
                "var box=ed; for(var u=0;u<20&&box;u++){"
                " var imgs=Array.from(box.querySelectorAll('img')).filter(function(i){"
                "  var r=i.getBoundingClientRect(); return r.width>30&&r.height>30;});"
                " if(imgs.length) return imgs.map(function(i){return (i.currentSrc||i.src||'')+'|'+(i.alt||'');});"
                " box=box.parentElement; } return [];"
            ) or []
            return tuple(values)
        except Exception:
            return ()

    def _composer_buttons(self):
        """Boutons a proximite du champ de prompt (plus sur que toute la page)."""
        try:
            return self.driver.execute_script(
                "var ed=null;"
                "document.querySelectorAll(\"[contenteditable='true']\").forEach(function(e){"
                " if(e.offsetWidth||e.offsetHeight) ed=e;});"
                "if(!ed) return [];"
                "var box=ed; for(var u=0;u<10&&box;u++){"
                " var b=box.querySelectorAll('button,[role=\"button\"]');"
                " if(b.length) return Array.prototype.slice.call(b);"
                " box=box.parentElement;}"
                "return [];") or []
        except Exception:
            return []

    def _click_composer_button(self, keywords):
        cands = self._composer_buttons()
        if not cands:
            try:
                cands = self.driver.find_elements(By.CSS_SELECTOR, "button, [role='button']")
            except Exception:
                return None
        seen = []
        for b in cands[:15]:
            try:
                if not (b.is_displayed() and b.is_enabled()):
                    continue
                try:
                    icon = (b.find_element(By.CSS_SELECTOR, "mat-icon").text or "").lower()
                except Exception:
                    icon = ""
                txt = (b.text or "").strip()
                label = ((b.get_attribute("aria-label") or "") + " " +
                         (b.get_attribute("title") or "") + " " +
                         txt + " " + icon).lower()
                seen.append(label[:60])
                # Le "+" n'a souvent aucun libelle : on le reconnait a son texte ou son icone
                if txt == "+" or icon.strip() == "add" or any(k in label for k in keywords):
                    b.click()
                    return label
            except Exception:
                continue
        self.log("boutons composer vus: %s" % (seen if seen else "aucun"))
        return None

    def _try_send_to_inputs(self, image_path, previous_signature):
        self._unhide_file_inputs()
        try:
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        except Exception:
            return False
        for inp in inputs:
            try:
                inp.send_keys(image_path)
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    current_signature = self._composer_image_signature()
                    try:
                        selected_names = self.driver.execute_script(
                            "return Array.from(arguments[0].files || []).map(function(f){return f.name;});",
                            inp,
                        ) or []
                    except Exception:
                        selected_names = []
                    exact_file_selected = os.path.basename(image_path) in selected_names
                    new_preview = current_signature != previous_signature
                    if ((exact_file_selected or new_preview) and self._is_image_attached()):
                        return True
                    time.sleep(0.2)
            except Exception as e:
                self.log("input refuse: %s" % e)
        return False

    def _upload_via_file_input(self, image_path, previous_signature=None):
        """Strategie 1: input direct, sinon menu + / upload, sinon echec."""
        if previous_signature is None:
            previous_signature = self._composer_image_signature()
        self._scan_file_inputs()
        if self._try_send_to_inputs(image_path, previous_signature):
            self.log("Image jointe via input direct.")
            return True

        self.log("Ouverture du menu de piece jointe (+)...")
        opened = self._click_composer_button(
            ("add file", "upload", "attach", "joindre", "ajouter", "fichier",
             "tools", "plus", "image", "photo", "drive", "more",
             "t\u1ea3i", "tai", "\u1ea3nh", "anh", "t\u1ec7p", "tep",
             "importer", "t\u00e9l\u00e9verser", "televerser", "parcourir", "browse"))
        if not opened:
            self.log("Bouton + / piece jointe introuvable.")
            return False
        self.log("menu ouvert via: %s" % opened[:80])
        time.sleep(1.2)
        # Cliquer l'option "Importer / Upload files" du menu deroulant
        try:
            items = self.driver.find_elements(
                By.CSS_SELECTOR, "[role='menuitem'], [role='option'], mat-list-item, li")
            for it in items:
                try:
                    t = ((it.text or "") + " " + (it.get_attribute("aria-label") or "")).lower()
                    if any(k in t for k in ("upload", "importer", "televerser", "parcourir",
                                            "browse", "from computer", "depuis",
                                            "t\u1ea3i", "tai")):
                        if it.is_displayed():
                            it.click()
                            self.log("option menu: %s" % t[:60])
                            time.sleep(1.0)
                            break
                except Exception:
                    continue
        except Exception:
            pass
        self._scan_file_inputs()
        if self._try_send_to_inputs(image_path, previous_signature):
            self.log("Image jointe via le menu.")
            return True
        return False

    def _upload_via_clipboard(self, image_path, previous_signature=None):
        """Strategie 2: image dans le presse-papiers puis Ctrl+V dans le prompt."""
        if previous_signature is None:
            previous_signature = self._composer_image_signature()
        try:
            import win32clipboard
            from PIL import Image
            import io as _io
            img = Image.open(image_path).convert("RGB")
            buf = _io.BytesIO()
            img.save(buf, "BMP")
            dib = buf.getvalue()[14:]  # sans header BMP
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
            finally:
                win32clipboard.CloseClipboard()
        except Exception as e:
            self.log("presse-papiers indisponible: %s" % e)
            return False
        el = self._find_prompt_input()
        if el is None:
            self.log("presse-papiers: champ prompt introuvable.")
            return False
        try:
            el.click()
            time.sleep(0.4)
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                if (self._composer_image_signature() != previous_signature
                        and self._is_image_attached()):
                    self.log("Nouvelle image collee via presse-papiers.")
                    return True
                time.sleep(0.2)
            self.log("collage sans apercu detecte.")
            return False
        except Exception as e:
            self.log("collage echoue: %s" % e)
            return False

    def _type_prompt(self, prompt):
        el = self._find_prompt_input()
        if el is None:
            raise RuntimeError("Champ de prompt introuvable.")
        el.click()
        time.sleep(0.3)
        try:
            el.send_keys(prompt)
        except Exception:
            self.driver.execute_script(
                "arguments[0].innerText=arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                el, prompt,
            )
        time.sleep(0.5)

    def _send(self):
        # Bouton envoyer, sinon Entree
        btns = self.driver.find_elements(By.CSS_SELECTOR, "button, [role='button']")
        for b in btns:
            try:
                label = ((b.get_attribute("aria-label") or "") + " " + (b.get_attribute("title") or "")).lower()
                if any(k in label for k in ("send", "envoyer", "gui", "submit")):
                    if b.is_displayed() and b.is_enabled():
                        b.click()
                        return
            except Exception:
                continue
        el = self._find_prompt_input()
        if el is not None:
            el.send_keys(Keys.ENTER)

    def _snapshot_downloads(self):
        # Chrome telecharge dans download_dir (Page.setDownloadBehavior) : ne
        # scanner QUE ce dossier pour ne pas confondre avec d'autres telechargements.
        files = set()
        for d in (self.download_dir,):
            if os.path.isdir(d):
                for f in glob.glob(os.path.join(d, "*")):
                    files.add(f)
        return files

    def _wait_new_image(self, before, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            for d in (self.download_dir,):
                if not os.path.isdir(d):
                    continue
                for f in glob.glob(os.path.join(d, "*")):
                    if f in before:
                        continue
                    low = f.lower()
                    if low.endswith((".crdownload", ".tmp", ".part")):
                        continue
                    if low.endswith((".png", ".jpg", ".jpeg", ".webp")):
                        # attendre que la taille se stabilise
                        last = -1
                        for _ in range(12):
                            try:
                                size = os.path.getsize(f)
                            except OSError:
                                size = -1
                            if size > 0 and size == last:
                                return f
                            last = size
                            time.sleep(0.2)
        return None

    def _get_result_images(self):
        try:
            return self.driver.execute_script(_JS_FIND_RESULT_IMAGES) or []
        except Exception:
            return []

    def _result_image_signature(self, image):
        """Identifiant stable d’une image résultat, utilisé pour distinguer les tours."""
        try:
            return self.driver.execute_script(
                "return arguments[0].currentSrc || arguments[0].src || '';", image
            ) or ""
        except Exception:
            try:
                return image.get_attribute("src") or ""
            except Exception:
                return ""

    def _is_generating(self):
        """Vrai si Gemini genere encore (bouton stop visible / spinner visible).

        Seuls les elements AFFICHES comptent : un spinner cache dans le DOM
        ne doit pas bloquer les runs suivants. Inclut le libelle francais
        'arreter la reponse' (avec et sans accent)."""
        try:
            return bool(self.driver.execute_script(
                "var btns=document.querySelectorAll('button,[role=\"button\"]');"
                "for(var i=0;i<btns.length;i++){"
                " var t=((btns[i].getAttribute('aria-label')||'')+' '+(btns[i].getAttribute('title')||'')).toLowerCase();"
                " if(t.indexOf('stop gener')>=0||t.indexOf('stop respond')>=0||t.indexOf('arreter')>=0||t.indexOf('arr\\u00eater')>=0||t.indexOf('stop')>=0){"
                "  var r=btns[i].getBoundingClientRect();"
                "  if(r.width>0&&r.height>0) return true;}}"
                "var sp=document.querySelectorAll('mat-progress-spinner,mat-spinner');"
                "for(var j=0;j<sp.length;j++){"
                " var q=sp[j].getBoundingClientRect();"
                " if(q.width>0&&q.height>0) return true;}"
                "return false;"))
        except Exception:
            return False

    # ------------------------------------------------------------------ main
    def _prepare_upload(self, image_path):
        """Reduit/compresse l'image pour accelerer envoi + traitement Gemini."""
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            w, h = img.size
            maxw = 1600
            if w > maxw:
                img = img.resize((maxw, int(h * maxw / w)), Image.LANCZOS)
            image_id = hashlib.sha256(img.tobytes()).hexdigest()[:12]
            up = os.path.join(self.work_dir, "upload_%s.jpg" % image_id)
            img.save(up, "JPEG", quality=88, optimize=True)
            kb = os.path.getsize(up) // 1024
            self.log("Plan prêt pour upload #%s (%dx%d, %d Ko)." % (
                image_id, img.size[0], img.size[1], kb))
            return up
        except Exception as e:
            self.log("Optimisation ignoree: %s" % e)
            return image_path

    def upload_plan_and_generate(self, image_path, prompt, out_path, timeout=420):
        """Exécute une génération exclusive ; refuse une opération déjà active."""
        if not self._driver_lock.acquire(blocking=False):
            return False, "Une opération Gemini est déjà en cours. Réessayez ensuite."
        try:
            return self._upload_plan_and_generate_locked(image_path, prompt, out_path, timeout)
        finally:
            self._driver_lock.release()

    def _upload_plan_and_generate_locked(self, image_path, prompt, out_path, timeout=420):
        """Envoie plan+prompt a Gemini, attend la generation, sauvegarde le rendu."""
        if not os.path.isfile(image_path):
            return False, "Image introuvable: %s" % image_path

        # Un cache hit évite Chrome, l'upload et la génération distante.
        try:
            cache_key = self.render_cache.key_for(image_path, prompt)
            cached = self.render_cache.get(cache_key)
            self.log("Empreinte plan + prompt : %s" % cache_key[:12])
        except OSError as e:
            self.log("Cache local indisponible, génération normale: %s" % e)
            cache_key, cached = None, None
        if cached:
            ok, result = self._copy_result(cached, out_path)
            if ok:
                self.log("Rendu retrouvé dans le cache local : Gemini non sollicité.")
                return True, result
            self.log("Lecture du cache impossible, génération normale: %s" % result)

        if not self.is_browser_open():
            return False, "Navigateur non ouvert. Cliquez 'Ouvrir Gemini'."
        if self.get_login_state() == "signin":
            return False, "Connectez-vous a Google dans la fenetre Gemini, puis relancez."

        # L’extraction rapide peut se terminer avant que Gemini ait fini le texte
        # de la réponse précédente. Ne pas envoyer une nouvelle image au milieu
        # de ce tour, sinon son image tardive pourrait être prise pour le nouveau rendu.
        if self._is_generating():
            self.log("Gemini termine encore la réponse précédente; attente avant le nouveau plan...")
            settle_deadline = time.monotonic() + 60.0
            while self._is_generating() and time.monotonic() < settle_deadline:
                time.sleep(0.3)
            if self._is_generating():
                return False, (
                    "Gemini termine toujours le rendu précédent. Le nouveau plan n’a pas été envoyé; "
                    "attendez la fin de la réponse puis relancez."
                )

        with self._lock:
            self._busy = True
        try:
            before = self._snapshot_downloads()
            self.log("Envoi du plan a Gemini...")
            up_path = self._prepare_upload(image_path)
            composer_before = self._composer_image_signature()
            sent = self._upload_via_file_input(up_path, composer_before)
            if not sent:
                self.log("Input file impossible, essai via presse-papiers (Ctrl+V)...")
                sent = self._upload_via_clipboard(up_path, composer_before)
            if not sent:
                raise RuntimeError(
                    "Impossible de joindre l'image. Dans Chrome : cliquez le '+' "
                    "puis 'Importer des fichiers' (ou collez l'image avec Ctrl+V), "
                    "puis relancez la generation.")
            time.sleep(2.5)

            self.log("Saisie du prompt...")
            self._type_prompt(prompt)
            # Snapshot juste avant l’envoi : une image tardive de l’ancien tour
            # ne doit pas satisfaire le critère de résultat du nouveau tour.
            before_signatures = {
                self._result_image_signature(image)
                for image in self._get_result_images()
            }
            self.log("Envoi du prompt...")
            self._send()

            self.log("Attente de la generation du rendu (jusqu'a ~%d min)..." % (timeout // 60))
            deadline = time.time() + timeout
            img_el = None
            waited = 0
            while time.time() < deadline:
                imgs = self._get_result_images()
                new_imgs = images_with_new_signatures(
                    imgs, before_signatures, self._result_image_signature
                )
                if new_imgs:
                    img_el = new_imgs[-1]
                    break
                time.sleep(1.0)
                waited += 1
                if waited % 60 == 0:
                    self.log("... generation en cours (%d min), Gemini travaille encore." % (waited // 60))

            if img_el is None:
                return False, ("Aucun rendu detecte avant expiration du delai. "
                               "Regardez la reponse dans Chrome : si Gemini a repondu "
                               "par du texte (limite de generation ?), aucun rendu ne viendra.")

            # Ne pas attendre la fin de toute la réponse Gemini : elle peut
            # continuer à écrire du texte longtemps après que le PNG soit prêt.
            self.log("Image apparue, vérification rapide de son chargement...")
            ready, image_state = wait_image_ready(self.driver, img_el, timeout=3.0)
            if not ready or not image_state:
                # Image paresseuse (lazy-load) ou complete=false : on extrait
                # quand meme, le screenshot d'element marche dans tous les cas.
                self.log("Image pas encore stabilisee, extraction quand meme.")
                image_state = {"width": 0, "height": 0}
            imgs = self._get_result_images()
            if imgs:
                img_el = imgs[-1]

            self.log("Image prête (%dx%d). Extraction immédiate..." % (
                image_state["width"], image_state["height"]))
            saved = self._extract_image(img_el, before)
            if not saved:
                return False, "Rendu detecte mais extraction impossible."

            if cache_key:
                try:
                    self.render_cache.put(cache_key, saved)
                    self.log("Rendu mis en cache localement.")
                except OSError as e:
                    self.log("Écriture du cache ignorée: %s" % e)
            return self._copy_result(saved, out_path)
        except Exception as e:
            return False, "Erreur Gemini: %s" % e
        finally:
            with self._lock:
                self._busy = False

    def _copy_result(self, source_path, out_path):
        """Copie le rendu vers le chemin de travail ou un chemin alternatif si verrouillé."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            if os.path.abspath(source_path) == os.path.abspath(out_path):
                return True, out_path
            shutil.copy2(source_path, out_path)
            self.log("Rendu enregistre: %s" % out_path)
            return True, out_path
        except OSError:
            # AutoCAD peut garder le raster de sortie ouvert/verrouillé.
            stamp = "%d_%d" % (int(time.time()), threading.get_ident())
            alt = os.path.join(self.work_dir, "render_%s.png" % stamp)
            try:
                shutil.copy2(source_path, alt)
                self.log("Rendu principal verrouille, rendu sauve sous %s" % os.path.basename(alt))
                return True, alt
            except OSError as e:
                return False, "Copie du rendu impossible: %s" % e

    def _extract_image(self, img_el, before):
        # 1) Canvas -> base64 : instantane, sans telechargement
        try:
            b64 = self.driver.execute_async_script(_JS_IMG_TO_B64, img_el)
            if b64 and "," in b64:
                data = base64.b64decode(b64.split(",", 1)[1])
                if len(data) > 20000:
                    p = os.path.join(self.work_dir, "downloads", "render_%d.png" % int(time.time()))
                    with open(p, "wb") as f:
                        f.write(data)
                    return p
        except Exception as e:
            self.log("Note (canvas): %s" % e)

        # 2) Bouton download + dossier de telechargements
        try:
            btn = self.driver.execute_script(_JS_DOWNLOAD_BTN_FOR, img_el)
            if btn is not None:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img_el)
                    self.driver.execute_script("arguments[0].click();", btn)
                except Exception:
                    ActionChains(self.driver).move_to_element(img_el).click(btn).perform()
                got = self._wait_new_image(before, timeout=20)
                if got:
                    return got
        except Exception as e:
            self.log("Note (download): %s" % e)

        # 3) Screenshot de l'element
        try:
            p = os.path.join(self.work_dir, "downloads", "render_%d.png" % int(time.time()))
            img_el.screenshot(p)
            return p
        except Exception as e:
            self.log("Note (screenshot): %s" % e)
        return None

def kill_old_browsers():
    """Ferme les chromedriver residuels (best effort)."""
    try:
        subprocess.run("taskkill /F /IM chromedriver.exe /T", shell=True,
                       capture_output=True)
    except Exception:
        pass
