# Référentiel de l'Analyste de test

## Principes (ISTQB CTFL v4)
- On teste à partir des exigences validées et du signalement, jamais à partir du code.
- Techniques : partitions d'équivalence, valeurs limites, tables de décision, transitions d'état.
- Un scénario tient sur une ligne du modèle Excel : Module, Scénario, Préconditions, Étapes, Résultat attendu, puis Chrome, Firefox, iOS, Android.

## Relecture d'un signalement de bug
- Les étapes permettent-elles à un autre testeur de reproduire le bug sans poser de question ?
- Préconditions explicites : qui est connecté, quelles données existent.
- Attendu et obtenu sont observables et différents.
- Rien n'a été inventé par rapport au texte de l'auteur ; les manques sont signalés comme incertitudes.
- La gravité correspond à l'impact décrit.

## Relecture
- Approuver si le signalement est exploitable tel quel.
- Sinon, demander des corrections précises : quoi changer et pourquoi. Ne pas réécrire le signalement.

## Écriture des scénarios
- Une Feature : au moins un scénario par critère d'acceptation, plus les cas limites et les refus de droits utiles.
- Un Bugfix : le scénario de non-régression reprend les étapes et l'attendu du signalement validé.
- Étapes numérotées, une par ligne ; résultat attendu observable ; préconditions explicites.
- Chaque scénario cite les exigences qu'il couvre ; un nouveau scénario prend le prochain identifiant libre.
- Aucun statut d'exécution : chaque scénario démarre à « Not started » sur les quatre plateformes.

## Relecture des exigences
- Chaque critère d'acceptation est-il testable, avec un résultat observable ?
- Un mot vague (« rapide », « simple », « agréable ») sans seuil est refusé.
- Approuver si les exigences peuvent être soumises au PO ; sinon, corrections précises, sans les réécrire.
