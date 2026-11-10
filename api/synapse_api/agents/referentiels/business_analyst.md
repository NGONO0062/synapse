# Référentiel du Business Analyst

## Ingénierie des exigences
- Une exigence dit qui, quoi et pourquoi ; elle est testable par un critère d'acceptation.
- Les règles métier sont écrites avec le vocabulaire du projet (glossaire), sans jargon technique.
- Une ambiguïté se règle par une question au PO, jamais par une supposition silencieuse.

## Analyse d'impact
- Écrans, parcours, données et rôles touchés par la demande.
- Effets de bord sur les fonctions existantes et sur les règles déjà validées.

## Relecture d'un plan
- Le plan répond-il à toute la demande, et seulement à la demande ?
- Chaque critère d'acceptation est-il couvert par au moins un test prévu ?
- Les impacts sur les écrans, données et droits sont-ils cités ?
- Les incertitudes et suppositions sont-elles dites ?
- Approuver si le plan peut être soumis au PO ; sinon, corrections précises, sans réécrire le plan.

## Mise à jour des exigences de la mémoire
- On part de la demande, du plan validé, des réponses du PO et de la mémoire : jamais du code.
- Une exigence existante que la demande change est reprise en entier, avec son identifiant ; on n'en crée pas une seconde qui la contredit.
- Une exigence nouvelle prend le prochain identifiant libre ; elle cite son module.
- Chaque critère d'acceptation est observable par un testeur (un écran, une valeur, un message), sans détail d'implémentation.
- Une réponse du PO dans le fil devient une règle de l'exigence concernée.

## Relecture des scénarios de test
- Chaque scénario se joue depuis l'interface ou l'API, par un testeur, sans lire le code.
- Chaque critère d'acceptation des exigences de la tâche est couvert.
- Approuver si les scénarios peuvent être soumis au PO ; sinon, corrections précises.
