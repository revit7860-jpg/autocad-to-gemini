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

;; Dossier de l'application : resolu via findfile (voir ag:dir).
;; Repli manuel si findfile echoue : renseignez votre chemin ici (slashes /).
(setq *AG-ROOT* "")
;; Interpreteur Python : "pythonw" (PATH), ou chemin absolu entre guillemets,
;; ex. "C:/Python312/pythonw.exe". Priorite a AutoCADGemini.exe si present.
(setq *AG-PYTHON* "pythonw")
;; Facteur d'insertion utilisé par la commande de secours AIRENDERINS.
(setq *AG-INSERT-SCALE* 1.0)

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
     (startapp "cmd.exe" (strcat "/c start \"\" \"" *AG-PYTHON* "\" \"" py "\"")))
    (t (princ (strcat "\nAutoCADGemini : application introuvable dans [" dir "]."
                      "\nVerifiez *AG-ROOT* / *AG-PYTHON* en tete du LISP."))))
  (princ)
)

(defun c:GEMINI ( )
  (princ "\nOuverture de AutoCAD Gemini Render...")
  (ag:launch)
  (princ)
)

;; Insertion de secours depuis AutoCAD (si l'appli n'est pas utilisee)
(defun c:AIRENDERINS ( / img scale )
  (setq img (strcat (ag:work) "\\render.png"))
  (setq scale (if (and (numberp *AG-INSERT-SCALE*) (> *AG-INSERT-SCALE* 0.0))
                *AG-INSERT-SCALE* 1.0))
  (if (findfile img)
    (progn
      (command "_.-IMAGEATTACH" img "0,0" scale 0)
      (princ (strcat "\nRendu insere dans le dessin (echelle " (rtos scale 2 4) ").")))
    (princ "\nAucun rendu trouve. Generez-le d'abord avec GEMINI."))
  (princ)
)

(princ "\n[AutoCAD Gemini Render] charge. Tapez GEMINI pour demarrer.\n")
(princ)
