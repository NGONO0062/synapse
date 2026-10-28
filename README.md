# Synapse

Une équipe d'agents IA conçoit, développe, teste et déploie des applications ; l'humain valide. Voir `CLAUDE.md` et `docs/Synapse_dossier_developpement.pdf`.

## Démarrer en local

```bash
# 1. Services (Postgres+pgvector, Keycloak, MinIO, LiteLLM)
cp infra/.env.example infra/.env   # remplir les mots de passe et les clés
docker compose -f infra/docker-compose.yml up -d
(cd infra && sh keycloak/set-demo-passwords.sh)   # comptes aline (PO) et brice (TESTEUR), mot de passe DEMO_USER_PASSWORD

# 2. API
cd api
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip sous Linux/macOS
echo "SYNAPSE_DATABASE_URL=postgresql+psycopg://synapse:<POSTGRES_PASSWORD>@localhost:5432/synapse" > .env
echo "SYNAPSE_LITELLM_API_KEY=<LITELLM_MASTER_KEY>" >> .env   # clé de la passerelle, celle de infra/.env
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn synapse_api.main:app --reload      # http://localhost:8000/docs
.venv/Scripts/python -m synapse_api.agents.worker        # orchestrateur : les casquettes (autre terminal)

# 3. Front
cd web
npm install
cp .env.example .env.local                               # puis générer SESSION_SECRET (commande dans le fichier)
npm run dev                                              # http://localhost:3200
```

Keycloak (http://localhost:8080) importe le royaume `synapse` : rôles `PO`, `TESTEUR`, `ADMIN`, thème de connexion Synapse, comptes de démo `aline` et `brice`. Le royaume n'est importé qu'au premier démarrage ; après une modification de `synapse-realm.json`, supprimer le royaume dans la console ou repartir de volumes neufs (`docker compose down -v`).

Ouvrir http://localhost:3200 : sans session, on arrive sur la connexion Keycloak, puis sur l'accueil.

## Orchestrateur et casquettes

Le worker (`python -m synapse_api.agents.worker`, `--once` pour un seul tour) lit le cycle de vie et fait travailler la bonne casquette, par la passerelle LiteLLM, avec le modèle choisi sur la tâche :

| Ce qui est dû | Rédige | Relit avant l'humain |
| --- | --- | --- |
| Reformuler un bug écrit en langage naturel | Débogueur | Analyste de test |
| Plan d'une Feature | Architecte | Business Analyst |
| Plan d'un Bugfix (test en échec d'abord) | Débogueur | Reviewer de code |
| Plan d'une Doc | Rédacteur technique | Business Analyst |

Chaque casquette charge son référentiel (`api/synapse_api/agents/referentiels/`), dont la version est journalisée avec la proposition, vérifie sa définition de « terminé », puis se fait relire. Après 3 brouillons, la proposition part quand même, avec les points non résolus en avertissement. L'état des graphes LangGraph est sauvegardé dans Postgres : un travail interrompu reprend là où il s'est arrêté.

Il faut une clé de fournisseur dans `infra/.env` (par exemple `ANTHROPIC_API_KEY`) et le conteneur `litellm` démarré.

## Simuler les agents

Sans clé de fournisseur, ou pour l'exécution (lot 3b), un simulateur joue le rôle des casquettes sur une tâche, en passant par les mêmes règles du cycle de vie. Ses messages sont marqués « [Simulation] ». Ne pas le lancer pour `report` ou `plan` pendant que le worker tourne : le worker les fait déjà.

```bash
cd api
.venv/Scripts/python -m synapse_api.dev.simulate BUG-001 report       # reformule un bug écrit en langage naturel (Backlog)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 plan        # propose un plan (tâche en To do)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 question    # pose une question (In progress)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 qa-failure  # échec QA (3 échecs : remontée au PO)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 result      # livre le résultat (passe en Review)
# --project "Nom du projet" si le code existe dans plusieurs projets
```

Parcours type : créer une demande → Prioriser → `plan` → Valider le plan → `result` → Valider le résultat.

Un bug peut être signalé en quelques mots (mode par défaut de l'écran de signalement, ou Bugfix tapé par le PO dans la barre de saisie). Il reste au Backlog jusqu'à ce que son auteur valide la reformulation. Parcours : le testeur décrit le bug → `report` → le testeur valide la reformulation, ou la fait corriger avec un commentaire puis `report` à nouveau → le PO priorise → suite du parcours Bugfix.

Pour un Bugfix, le plan porte le test qui reproduit le bug, et le résultat ouvre un livrable (diff et contrôles) dans le panneau droit. Parcours : le testeur signale le bug (formulaire du projet) → le PO priorise → `plan` → Valider le plan → `result` → le PO valide dans le panneau → le testeur confirme la correction.

## Vérifier

```bash
cd api && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check .
cd web && npm run typecheck && npm run lint && npm run build
```

## État d'avancement

| Lot | Contenu | État |
| --- | --- | --- |
| 0 · Fondations | Monorepo, cycle de vie des tâches, API projets/tâches/journal, auth OIDC, migration initiale, design system, écran de connexion | Fait |
| 1 · Identité | Thème de connexion Keycloak, connexion OIDC (BFF, PKCE), session chiffrée, renouvellement des jetons, garde des routes, déconnexion, accueil appelant l'API | Fait |
| 2a · Projets et tâches | Accueil (décisions en attente, projets), nouveau projet, barre latérale par statut, fil de tâche (plans, résultats, questions, décisions), barre de saisie, simulateur d'agent | Fait |
| 2b · Bugfix et testeur | Signalement structuré d'un bug (écran du testeur), test qui reproduit le bug dans le plan, panneau du livrable (diff, contrôles) avec la décision, confirmation du testeur | Fait |
| 2c · Bug en langage naturel | Signalement en quelques mots (mode par défaut), reformulation par une casquette, validation ou correction par l'auteur avant la priorisation | Fait |
| 3a · Orchestrateur | Worker LangGraph (état dans Postgres), passerelle LiteLLM, un sous-graphe par casquette, référentiels versionnés, définition de « terminé », relecture par une autre casquette ; reformulation des bugs et plans | Fait |
| 3b · Exécution | Bac à sable (un conteneur par tâche), dépôt Git, Développeur, Reviewer, QA, livrable réel | À faire |
| 3c · Traçabilité et coûts | Consommation par projet et par modèle, cas de référence rejoués | À faire |
