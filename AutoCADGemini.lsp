;;; ============================================================================
;;; AutoCAD Gemini Render - lanceur AutoCAD
;;;
;;; Commandes :
;;;   GEMINI       -> ouvre l'interface (capture + Gemini + rendu)
;;;   AIRENDERINS  -> insere le dernier rendu genere dans le dessin courant
;;;
;;; Si tu deplaces le dossier, mets a jour *AG-ROOT* ci-dessous.
;;; ============================================================================

(vl-load-com)

;; Dossier de l'application (chemin absolu, slashes /)
(setq *AG-ROOT* "C:/Users/PROMOTECH/Downloads/script gemini to 3dsmax/AutoCADGemini")

;; Dossier de travail partage avec l'application
(defun ag:work ( )
  (strcat (getenv "TEMP") "\\AutoCADGemini")
)

;; Retourne le dossier de l'app (via findfile si dispo, sinon *AG-ROOT*)
(defun ag:dir ( / f d )
  (setq f (findfile "AutoCADGemini.lsp"))
  (if f
    (vl-string-translate "\\" "/" (vl-filename-directory f))
    (if (vl-file-directory-p *AG-ROOT*) *AG-ROOT* ""))
)

;; Lance l'application compagnon (exe si present, sinon src\main.py via pythonw)
(defun ag:launch ( / dir exe py cmd )
  (setq dir (ag:dir))
  (setq exe (strcat dir "/AutoCADGemini.exe"))
  (setq py  (strcat dir "/src/main.py"))
  (cond
    ((and (/= dir "") (findfile exe))
     (startapp "cmd.exe" (strcat "/c start \"\" \"" exe "\"")))
    ((and (/= dir "") (findfile py))
     (startapp "cmd.exe" (strcat "/c start \"\" pythonw \"" py "\"")))
    (t (princ (strcat "\nAutoCADGemini : application introuvable dans [" dir "]."))))
  (princ)
)

(defun c:GEMINI ( )
  (princ "\nOuverture de AutoCAD Gemini Render...")
  (ag:launch)
  (princ)
)

;; Insertion de secours depuis AutoCAD (si l'appli n'est pas utilisee)
(defun c:AIRENDERINS ( / img )
  (setq img (strcat (ag:work) "\\render.png"))
  (if (findfile img)
    (progn
      (command "_.-IMAGEATTACH" img "0,0" 1 0)
      (princ "\nRendu insere dans le dessin."))
    (princ "\nAucun rendu trouve. Generez-le d'abord avec GEMINI."))
  (princ)
)

(princ "\n[AutoCAD Gemini Render] charge. Tapez GEMINI pour demarrer.\n")
(princ)
