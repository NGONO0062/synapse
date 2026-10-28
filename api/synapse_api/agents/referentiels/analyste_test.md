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
