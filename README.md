# Synapse

Une équipe d'agents IA conçoit, développe, teste et déploie des applications ; l'humain valide. Voir `CLAUDE.md` et `docs/Synapse_dossier_developpement.pdf`.

## Démarrer en local

```bash
# 1. Services (Postgres+pgvector, Keycloak, MinIO, LiteLLM)
cp infra/.env.example infra/.env   # remplir les mots de passe et les clés
docker compose -f infra/docker-compose.yml up -d

# 2. API
cd api
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip sous Linux/macOS
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn synapse_api.main:app --reload      # http://localhost:8000/docs

# 3. Front
cd web
npm install
npm run dev                                              # http://localhost:3000
```

Keycloak (http://localhost:8080) importe le royaume `synapse` avec les rôles `PO`, `TESTEUR`, `ADMIN` et deux comptes de démo, `aline` (PO) et `brice` (TESTEUR), **sans mot de passe** : en définir un dans la console d'administration.

## Vérifier

```bash
cd api && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check .
cd web && npm run typecheck && npm run lint && npm run build
```

## État d'avancement

| Lot | Contenu | État |
| --- | --- | --- |
| 0 · Fondations | Monorepo, cycle de vie des tâches, API projets/tâches/journal, auth OIDC, migration initiale, design system, écran de connexion | Fait |
| 1 · Identité | Connexion Keycloak côté front, session, garde des routes | À faire |
| 2 · Projets et tâches | Accueil, nouveau projet, barre latérale par statut, fil de tâche | À faire |
| 3 · Orchestration | LangGraph, sous-graphes par casquette, passerelle LiteLLM, bac à sable | À faire |
