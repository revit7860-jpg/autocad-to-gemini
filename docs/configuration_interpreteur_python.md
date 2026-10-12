# Configurer l’interpréteur Python dans AutoCAD

Le lanceur `AutoCADGemini.lsp` cherche d’abord `AutoCADGemini.exe` à côté du fichier LISP. S’il n’existe pas, il lance `src/main.py` avec la valeur de `*AG-PYTHON*`.

## 1. Installer Python et les dépendances

Installez Python 3.10 ou une version ultérieure. Ouvrez un terminal Windows dans le dossier du projet et installez les dépendances avec **le même interpréteur** que vous prévoyez de configurer :

```bat
"C:\Users\VotreNom\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
```

Si vous utilisez un environnement virtuel, activez-le avant cette commande, ou utilisez directement son exécutable, par exemple :

```text
C:/chemin/AutoCADGemini/.venv/Scripts/pythonw.exe
```

La dépendance `pywin32` est utilisée pour l’insertion COM dans AutoCAD ; les autres modules listés dans `requirements.txt` sont requis par le flux de capture et Gemini.

## 2. Configurer le chemin dans AutoLISP

Ouvrez `AutoCADGemini.lsp` dans un éditeur de texte et réglez la variable en tête du fichier. Remplacez le chemin d’exemple par le chemin réel de votre Python :

```lisp
(setq *AG-PYTHON* "C:/Users/VotreNom/AppData/Local/Programs/Python/Python312/pythonw.exe")
```

Utilisez des `/` dans la chaîne AutoLISP. Les espaces dans le chemin sont acceptés : le lanceur place le chemin de l’interpréteur et le chemin du script entre guillemets.

- **`pythonw.exe`** lance l’interface sans fenêtre de console ; c’est le choix normal.
- **`python.exe`** affiche une console et peut aider au diagnostic. Pour l’utiliser, remplacez seulement `pythonw.exe` par `python.exe`.
- **Environnement virtuel** : pointez sur `.venv/Scripts/pythonw.exe` pour être certain d’utiliser les dépendances installées dans cet environnement.

Le chemin doit viser un exécutable, pas le dossier Python. La valeur initiale `pythonw` ne fonctionne que si Python est déjà accessible dans le `PATH` du processus AutoCAD.

## 3. Vérifier le dossier du projet

Le LISP essaie de déterminer son dossier avec `findfile "AutoCADGemini.lsp"`. Chargez le LISP depuis le dossier du projet (commande `APPLOAD`) et gardez la structure suivante :

```text
AutoCADGemini/
├── AutoCADGemini.lsp
└── src/
    └── main.py
```

Si `findfile` ne retrouve pas le LISP, renseignez aussi un chemin absolu dans `*AG-ROOT*` :

```lisp
(setq *AG-ROOT* "C:/chemin/vers/AutoCADGemini")
```

Le chemin racine doit contenir le sous-dossier `src`.

## 4. Tester depuis AutoCAD

1. Enregistrez le fichier LISP.
2. Dans AutoCAD, rechargez-le avec `APPLOAD`.
3. Exécutez `GEMINI`.
4. Si rien ne démarre, remplacez temporairement `pythonw.exe` par `python.exe`, puis relancez `GEMINI` afin de voir les erreurs éventuelles dans la console.

Pour vérifier la version et les dépendances depuis une invite de commandes :

```bat
"C:\chemin\vers\python.exe" --version
"C:\chemin\vers\python.exe" -m pip show selenium pillow pywin32
```

Assurez-vous que le même interpréteur apparaît dans les deux commandes et dans `*AG-PYTHON*` (en choisissant `pythonw.exe` pour le lancement normal).

## 5. Échelle d’insertion du rendu

Dans l’interface Python, le champ **Échelle** est transmis aux deux chemins d’insertion (`AddRaster` COM et `-IMAGEATTACH`). La valeur par défaut est `1.0` ; elle représente le facteur d’échelle appliqué par AutoCAD, et n’effectue pas une conversion automatique entre pixels et unités du dessin. Ajustez-la selon la taille voulue dans votre dessin.

La commande de secours `AIRENDERINS` utilise sa propre valeur AutoLISP :

```lisp
(setq *AG-INSERT-SCALE* 1.0)
```

Cette valeur doit être strictement positive. Elle ne modifie pas le champ Échelle de l’interface Python.

## Remarques

- Gardez les chemins entre guillemets ; les dossiers contenant des espaces sont pris en charge par la commande `start` du LISP.
- Si AutoCAD ne résout pas `pythonw`, utilisez le chemin absolu ci-dessus au lieu de compter sur `PATH`.
- Pour une distribution à plusieurs personnes, un exécutable empaqueté est généralement plus simple à déployer que Python installé séparément.
