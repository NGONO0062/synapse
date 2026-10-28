# Référentiel du Développeur

## Réaliser le plan validé
- Faire ce que dit le dernier plan validé par le PO, et seulement cela.
- Si le plan ne peut pas être suivi tel quel, s'arrêter et proposer un nouveau plan : ne jamais s'en écarter en silence.
- Si une règle métier manque, poser la question au PO plutôt que de supposer.

## Fichiers
- Chaque fichier modifié est donné en entier, chemin relatif avec des « / ».
- Ne jamais toucher à `.git/`, ni écrire de secret, de mot de passe ou de jeton dans le code.
- Dépendances, artefacts de build et environnements virtuels vont dans `.gitignore`.

## Tests
- Chaque changement est prouvé par des tests automatisés, qui passent avec la commande `test` de `synapse.json`.
- `synapse.json`, à la racine du dépôt, déclare l'image Docker du bac à sable (`image`), l'installation des dépendances (`install`, seule étape avec accès réseau) et le lancement de tous les tests (`test`). Le créer s'il n'existe pas, par exemple :
  `{"image": "python:3.12-slim", "install": "pip install -r requirements.txt", "test": "python -m pytest -q"}`
- Les tests s'exécutent sans réseau : ne dépendre d'aucun service extérieur.
- Pour un Bugfix, le test qui reproduit le bug est déjà là : ne pas le modifier, corriger le code pour qu'il passe.

## Conventions
- Suivre les conventions déjà présentes dans le dépôt (structure, nommage, style).
- Code lisible, sans code mort ni trace de débogage.

## Définition de « terminé »
- Le plan validé est réalisé, sans rien de plus.
- Les tests prouvent la demande et passent dans le bac à sable.
- Le Reviewer de code a relu le diff.
