# AutoCAD Gemini Render

Outil compagnon pour **AutoCAD** : capture le plan (ou la vue) courant, l'envoie a
**Gemini** pour obtenir un **rendu realiste**, puis reinjecte le rendu dans le
dessin — sans quitter AutoCAD.

Meme principe que l'outil 3ds Max (`GeminiStudio`), adapte a AutoCAD.

## Principe

```
[AutoCAD]  capture zone de dessin  ->  plan.png
      |                                      |
      |  (bouton GEMINI)                     v
      +---------------------->  [App Python]  --(Selenium)-->  Gemini Web
                                     ^                               |
                                     |         render.png  <---------+
                                     v
                              IMAGEATTACH  ->  rendu dans le dessin AutoCAD
```

## Contenu

| Fichier | Role |
|---|---|
| `AutoCADGemini.lsp` | Lanceur AutoCAD : commandes `GEMINI` et `AIRENDERINS` |
| `src/main.py` | Point d'entree (verrou single-instance) |
| `src/gui.py` | Interface (capture / Gemini / rendu / insertion) |
| `src/autocad_bridge.py` | Capture fenetre AutoCAD + insertion du rendu |
| `src/gemini_web.py` | Automatisation Gemini (Selenium) |
| `presets.json` | Prompts de rendu predefinis |
| `requirements.txt` | Dependances Python |

## Installation

1. Python 3.10+ puis :
   ```
   pip install -r requirements.txt
   ```
   (Chrome doit etre installe.)
2. Charger `AutoCADGemini.lsp` dans AutoCAD : commande `APPLOAD`, ou l'ajouter
   a la suite de demarrage.
3. Tapez **GEMINI** dans AutoCAD (ou creez un bouton via CUI).

## Utilisation

1. Ouvrez votre plan dans AutoCAD, cadrez la vue a rendre.
2. Dans l'outil : **1. Capturer le plan**.
3. **2. Ouvrir Gemini** — connectez-vous une fois a Google (session memorisee).
4. Choisissez un type de rendu + ajustez le prompt, puis **3. Generer le rendu**.
5. **Inserer dans AutoCAD** pour poser le rendu dans le dessin
   (ou commande `AIRENDERINS`).
   L'aperçu est préparé en arrière-plan avec un redimensionnement rapide et
   l'insertion AutoCAD ne bloque plus l'interface.

## Dossiers

- Travail : `%TEMP%\AutoCADGemini\` (`plan.png`, `render.png`, `downloads\`)
- Profil Chrome : `%APPDATA%\AutoCADGemini\chrome_profile\`

## Points d'attention

- **CGU Google** : automatiser l'UI de Gemini peut etre contraire aux conditions
  d'utilisation. Utilisez de preference un **compte dedie**.
- **Capture** : le screenshot de la fenetre inclut ce qui est visible a l'ecran
  (evitez les menus ouverts). Une option de plot vectoriel (PNG propre) pourra
  etre ajoutee ulterieurement.
- **Insertion du rendu** : via COM (`AddRaster`) si `pywin32` est present, sinon
  via la commande `-IMAGEATTACH` (pilote clavier). Selon la version d'AutoCAD,
  l'une des deux methodes peut mieux fonctionner.
- Code fourni **tel quel**, non teste sur toutes les versions d'AutoCAD.

## Ameliorations possibles

- Capture vectorielle nette via `PLOT` vers `PublishToWeb PNG.pc3`.
- Affichage du rendu dans une **palette** AutoCAD (au lieu d'une image attachee).
- Variante sans navigateur via l'**API Gemini image** (cle API, plus fiable).
