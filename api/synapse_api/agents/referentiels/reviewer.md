# Référentiel du Reviewer de code

## Checklist de revue
- Le changement fait ce qui est demandé, rien de plus.
- Les cas limites et les erreurs sont traités.
- Pas de secret, de donnée personnelle ni de trace de débogage dans le code ou les messages.
- Les tests prouvent le comportement, pas l'implémentation.
- Le code suit les conventions du projet.

## Relecture d'un plan de Bugfix
- Le plan commence par un test qui reproduit le bug et échoue avant la correction.
- La correction vise la cause, pas seulement le symptôme ; si la cause n'est que probable, c'est dit.
- La non-régression couvre les fonctions voisines.
- Le périmètre reste celui du bug.
- Approuver si le plan peut être soumis au PO ; sinon, corrections précises, sans réécrire le plan.
