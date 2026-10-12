# Cache local et optimisation du temps de réponse

## Ce que fait actuellement l’application

La version actuelle pilote **Gemini Web dans Chrome avec Selenium** ; elle ne passe pas directement par l’API Gemini. Le délai observé comprend donc le chargement de la page, le téléversement du plan, l’attente du modèle, puis la récupération du fichier. Les réglages d’une API (choix de modèle, requête API, région/service) ne s’appliquent pas directement à cette intégration Web.

Pour accélérer réellement la génération distante, les pistes structurantes sont :

1. **Migrer vers l’API Gemini officielle** si l’usage, le modèle et les conditions applicables le permettent. Cela supprimerait les coûts de navigateur, les heuristiques DOM et les étapes d’upload/clics Selenium ; le temps de génération du modèle et du réseau restera présent.
2. Comparer les modèles disponibles selon la latence et la qualité voulue plutôt que demander systématiquement la qualité maximale.
3. Envoyer une image d’entrée correctement cadrée et seulement assez grande pour préserver les détails nécessaires. Éviter les marges, fenêtres et zones UI inutiles ; le code compresse déjà l’image préparée pour le transfert.
4. Réutiliser une session déjà ouverte et éviter une nouvelle génération si l’entrée et la consigne sont identiques. Le cache local décrit ci-dessous couvre ce dernier cas.
5. Mesurer séparément upload, attente de génération, extraction et affichage, au lieu d’optimiser à l’aveugle.

### Après apparition de l’image

Le flux ne doit pas attendre que Gemini termine aussi le texte qui accompagne le rendu. Il vérifie maintenant que l’image DOM a fini de charger et que son URL/dimensions sont stables sur deux observations, avec une limite de 3 secondes. Dès qu’elle est disponible, il lance l’extraction même si le bouton « stop » ou un indicateur de génération est encore visible. L’ancien contrôle pouvait retarder l’extraction de près de 30 secondes.

Comme Gemini peut encore finaliser le texte après l’extraction rapide, une nouvelle demande attend maintenant la fin du tour précédent (au plus 60 s ; sinon elle est refusée sans envoi). Le résultat est choisi selon une source d’image absente de l’instantané pris juste avant l’envoi, plutôt que par simple décompte. En mode express, la zone est consommée une seule fois afin d’éviter de reprendre le même recadrage après avoir changé de plan.

Une migration API nécessiterait une implémentation dédiée, une clé gérée hors du code source (par exemple variable d’environnement ou stockage de secrets local) et le choix explicite du modèle. Le cache actuel est volontairement indépendant du fournisseur et reste utilisable si le moteur de génération change.

## Cache local des rendus

Le cache se trouve dans `%TEMP%\AutoCADGemini\render_cache` sous Windows. La clé est le SHA-256 du **contenu exact du plan**, du prompt (espaces de début/fin retirés) et de la version du schéma du cache.

- **Cache hit :** le rendu est copié vers le chemin de travail ; Chrome, Selenium et Gemini ne sont pas sollicités. Cela réduit la répétition à une opération disque.
- **Cache miss :** le flux normal est exécuté ; le résultat est ajouté atomiquement au cache après extraction.
- Le cache garde au plus **40 rendus**, avec élagage approximatif LRU.
- Le cache est local à l’utilisateur et n’envoie pas de données supplémentaires.
- Les entrées peuvent devenir moins pertinentes si le service change : supprimez le dossier `render_cache` pour repartir de zéro. Si la sémantique du traitement change, incrémentez `CACHE_SCHEMA` dans `src/render_cache.py`.

Le cache réutilise volontairement le rendu précédent pour exactement le même plan et la même consigne. Pour demander une nouvelle variation, modifiez légèrement le prompt ou effacez l’entrée correspondante/le dossier de cache.

## Benchmark d’affichage dans AutoCAD (Windows)

Script : `scripts/benchmark_autocad_display.py`. Il se connecte à AutoCAD via COM, crée un dessin temporaire, génère des plans synthétiques de 1024×768 à 3840×2160, mesure séparément `AddRaster` et `ZoomExtents + Regen + Update`, puis ferme le dessin temporaire sans l’enregistrer. Les données sont exportées dans un CSV.

Dans PowerShell ou CMD, depuis le dossier du projet :

```bat
python scripts\benchmark_autocad_display.py --repeats 3 --csv autocad_display_benchmark.csv
```

Pré-requis : Windows, AutoCAD installé et démarré, `pywin32` et Pillow disponibles dans l’interpréteur utilisé. Évitez d’utiliser AutoCAD pendant le test. Le script ajoute un nouveau dessin temporaire et le ferme sans sauvegarde ; il n’ajoute pas d’entités au dessin préexistant.

**Interprétation :** les mesures COM et regen sont un indicateur reproductible du coût d’insertion/rafraîchissement, mais ne mesurent pas le temps exact de peinture des pixels par le pilote graphique ou l’écran. Comparez les résultats sur le même poste, la même version d’AutoCAD, le même GPU, le même zoom et les mêmes paramètres d’affichage. Le temps de réseau/Gemini n’est pas inclus.
