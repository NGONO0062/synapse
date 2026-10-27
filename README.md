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
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn synapse_api.main:app --reload      # http://localhost:8000/docs

# 3. Front
cd web
npm install
cp .env.example .env.local                               # puis générer SESSION_SECRET (commande dans le fichier)
npm run dev                                              # http://localhost:3200
```

Keycloak (http://localhost:8080) importe le royaume `synapse` : rôles `PO`, `TESTEUR`, `ADMIN`, thème de connexion Synapse, comptes de démo `aline` et `brice`. Le royaume n'est importé qu'au premier démarrage ; après une modification de `synapse-realm.json`, supprimer le royaume dans la console ou repartir de volumes neufs (`docker compose down -v`).

Ouvrir http://localhost:3200 : sans session, on arrive sur la connexion Keycloak, puis sur l'accueil.

## Simuler les agents (en attendant l'orchestrateur)

Les casquettes arrivent au lot 3. D'ici là, un simulateur joue leur rôle sur une tâche, en passant par les mêmes règles du cycle de vie. Ses messages sont marqués « [Simulation] ».

```bash
cd api
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 plan        # propose un plan (tâche en To do)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 question    # pose une question (In progress)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 qa-failure  # échec QA (3 échecs : remontée au PO)
.venv/Scripts/python -m synapse_api.dev.simulate FEAT-001 result      # livre le résultat (passe en Review)
# --project "Nom du projet" si le code existe dans plusieurs projets
```

Parcours type : créer une demande → Prioriser → `plan` → Valider le plan → `result` → Valider le résultat.

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
| 2b · Bugfix et testeur | Panneau droit du fil Bugfix (diff, tests), écran du testeur (signaler un bug) | À faire |
| 3 · Orchestration | LangGraph, sous-graphes par casquette, passerelle LiteLLM, bac à sable | À faire |
