# Référentiel de l'Architecte

## Plan d'une Feature
- Partir de la demande et de l'analyse d'impact : écrans, API, modèle de données, droits, tests concernés.
- Chaque changement tient sur une ligne et commence par « + » (ajout), « ~ » (modification) ou « - » (suppression).
- Préférer la plus petite modification qui répond à la demande ; tout ce qui dépasse la demande est signalé à part, pas glissé dans le plan.
- Respecter les conventions de la stack du projet et les décisions d'architecture déjà validées.
- Toute migration de données dit comment revenir en arrière.

## Tests prévus
- Au moins un test qui prouve que la demande est remplie (critère d'acceptation).
- Un E2E seulement pour un parcours critique ; sinon tests d'API ou unitaires.

## Honnêteté du plan
- Ce que tu ne sais pas du projet (volumes, intégrations, règles métier) va dans les incertitudes.
- Ce que tu supposes pour avancer va dans les suppositions ; ce que tu n'as pas pu vérifier, dans « non vérifié ».

## Définition de « terminé »
- Chaque changement est concret, rattaché à un écran, une API ou une donnée.
- Les tests prévus couvrent le critère d'acceptation.
- Aucun changement hors du périmètre de la demande.
