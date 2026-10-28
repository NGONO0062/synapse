# Référentiel du Débogueur

## Procédure de reproduction
- Un bug n'existe que s'il se reproduit : environnement, données de départ, étapes exactes, résultat obtenu.
- Les étapes sont numérotées, une action par étape, du point de départ (qui est connecté, sur quel écran) jusqu'au constat.
- Le résultat attendu vient des exigences validées ou de ce que dit l'auteur, jamais du code.
- Le résultat obtenu décrit ce que l'on voit, sans interprétation de la cause.

## Reformulation d'un signalement écrit en langage naturel
- Reprendre seulement ce que dit l'auteur. Ce qui manque (appareil, données, environnement) va dans les incertitudes ; ce qui est déduit va dans les suppositions.
- Titre court (moins de 80 caractères), qui décrit le symptôme et pas la cause supposée.
- Gravité : BLOQUANT si un parcours essentiel est impossible ou si des données sont perdues ou fausses sans contournement ; MAJEUR si le résultat est faux mais contournable ; MINEUR pour l'affichage, le libellé ou le confort.
- Environnement : STAGING par défaut, PREPROD seulement si l'auteur le dit.
- Quand l'auteur demande une correction, l'appliquer telle quelle et ne rien changer d'autre.

## Plan de correction d'un Bugfix
- Toujours commencer par le test qui reproduit le bug et échoue avant la correction. Ce test rejoint la non-régression.
- Puis la cause probable, la correction minimale, et les tests de non-régression autour.
- Ne pas élargir le périmètre : un autre défaut repéré devient une suggestion, pas une partie du plan.

## Écrire le test qui reproduit le bug
- Avant toute correction, écrire dans le dépôt le test automatisé qui reproduit le bug. Il doit échouer tant que le bug est là.
- Ne pas corriger le bug à cette étape.
- Le test se lance avec la commande `test` de `synapse.json` ; créer ce fichier s'il n'existe pas (voir le référentiel du Développeur).

## Définition de « terminé »
- Étapes reproductibles par quelqu'un qui ne connaît pas le bug.
- Attendu et obtenu différents et vérifiables.
- Plan de correction : test en échec nommé, correction, non-régression.
